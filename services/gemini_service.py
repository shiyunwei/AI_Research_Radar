# services/gemini_service.py
# 負責呼叫 Gemini：理解研究主題、擴展英文關鍵字
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_THINKING_LEVEL
import json
import re
import time

class GeminiError(Exception):
    """Gemini 相關錯誤，訊息可直接顯示給使用者。"""


# ---------- 回傳格式定義（Python 端會用它驗證 Gemini 的輸出）----------
class KeywordResult(BaseModel):
    topic_en: str               # 研究主題的英文表達
    topic_summary_zh: str       # 對主題的中文理解（一兩句）
    keywords: list[str]         # 核心英文關鍵字
    synonyms: list[str]         # 同義詞或替代說法
    related_concepts: list[str] # 相關研究概念
    search_queries: list[str]   # 適合直接拿去搜尋學術資料庫的英文搜尋詞


def _get_client():
    if not GEMINI_API_KEY:
        raise GeminiError("找不到 GEMINI_API_KEY，請檢查 .env 設定。")
    return genai.Client(api_key=GEMINI_API_KEY)


RETRY_CODES = (500, 503, 504)  # 伺服器暫時性錯誤，值得重試
MAX_ATTEMPTS = 2               # 每個模型最多嘗試次數（SDK 本身也會做內部重試）

LAST_CALL_INFO = {}  # 最近一次呼叫的診斷資訊（模型、秒數、token 數）


class GeminiBusyError(GeminiError):
    """伺服器忙碌或額度用完，用來觸發備用模型。"""
    def __init__(self, message, quota=False):
        super().__init__(message)
        self.quota = quota


def _build_config(schema):
    """建立呼叫設定。有設定 GEMINI_THINKING_LEVEL 時才加入思考等級。"""
    kwargs = dict(response_mime_type="application/json", response_schema=schema)
    if GEMINI_THINKING_LEVEL:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
    return types.GenerateContentConfig(**kwargs)


def _generate_with_retry(client, model, prompt, schema):
    """用指定模型呼叫 Gemini，遇到伺服器忙碌會重試；仍失敗則丟出 GeminiBusyError。"""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=model, contents=prompt, config=_build_config(schema),
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            msg = str(getattr(e, "message", e))[:200]
            if code in RETRY_CODES:
                if attempt < MAX_ATTEMPTS:
                    time.sleep(5 * attempt)
                    continue
                raise GeminiBusyError(f"模型 {model} 伺服器忙碌（{code}）。")
            if code == 429:
                raise GeminiBusyError(f"模型 {model} 使用額度已達上限（429）。", quota=True)
            if code == 404:
                raise GeminiError(f"找不到模型 {model}，請確認 .env 的模型名稱。")
            if code in (401, 403):
                raise GeminiError("Gemini 金鑰無效或沒有權限，請確認 .env 的 GEMINI_API_KEY。")
            if code == 400:
                raise GeminiError(f"Gemini 拒絕了這次請求（400）：{msg}。"
                                  "若訊息與 thinking 有關，請檢查 .env 的 GEMINI_THINKING_LEVEL。")
            raise GeminiError(f"Gemini 回傳錯誤（{code}）：{msg}")
        except Exception as e:
            raise GeminiError("無法連線到 Gemini：" + re.sub(r"AIza[0-9A-Za-z_-]{20,}", "***", str(e))[:200])


def call_gemini_json(prompt, schema):
    """通用函式：送出提示詞，要求 JSON 格式回覆，並用 schema 驗證後回傳物件。
    主要模型忙碌時，會自動改用備用模型（若有設定）。"""
    client = _get_client()

    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)

    start = time.time()
    response, used_model = None, None
    for i, model in enumerate(models):
        try:
            response = _generate_with_retry(client, model, prompt, schema)
            used_model = model
            break
        except GeminiBusyError as e:
            if i == len(models) - 1:  # 所有模型都不可用
                if e.quota:
                    raise GeminiError("Gemini 使用額度或速率已達上限，請等一分鐘後再試；"
                                      "若持續發生，可能是今日額度已用完，請明天再試。")
                raise GeminiError("Gemini 伺服器目前忙碌，請稍後再試。")
            # 否則換下一個模型繼續嘗試

    # 記錄診斷資訊
    usage = getattr(response, "usage_metadata", None)
    LAST_CALL_INFO.clear()
    LAST_CALL_INFO.update({
        "model": used_model,
        "thinking_level": GEMINI_THINKING_LEVEL or "預設",
        "seconds": round(time.time() - start, 1),
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "thinking_tokens": getattr(usage, "thoughts_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
    })

    # 優先使用 SDK 解析好的物件；若是 None，再嘗試從文字手動解析
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    text = getattr(response, "text", None)
    if not text:
        raise GeminiError("Gemini 沒有回傳內容（可能被安全機制阻擋或輸出被截斷），請換個說法再試。")
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        raise GeminiError("Gemini 回傳的格式不符合預期，請再試一次。")


def _clean_list(items, limit):
    """去除空白與重複（不分大小寫），並限制數量。"""
    seen, result = set(), []
    for item in items or []:
        item = item.strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
    return result[:limit]


def expand_keywords(topic):
    """把使用者輸入的研究主題擴展成英文學術關鍵字。"""
    topic = (topic or "").strip()
    if not topic:
        raise GeminiError("請先輸入研究主題。")

    prompt = f"""你是學術文獻檢索專家。使用者想探索以下研究主題：

「{topic}」

請完成以下工作：
1. topic_en：把主題轉成自然的英文學術表達。
2. topic_summary_zh：用一兩句繁體中文說明你對這個主題的理解。
3. keywords：5 到 8 個核心英文關鍵字（學術論文常用的詞）。
4. synonyms：3 到 6 個同義詞或替代說法。
5. related_concepts：3 到 6 個相關的研究概念。
6. search_queries：3 到 5 組適合直接用於學術資料庫搜尋的英文搜尋詞，每組由 2 到 5 個單字組成，各組角度要有差異。

規則：只提供關鍵字與搜尋詞，不要提及或編造任何論文、作者或研究結果。所有英文欄位請使用英文。"""

    result = call_gemini_json(prompt, KeywordResult)

    # Python 端再次整理，確保資料乾淨
    result.keywords = _clean_list(result.keywords, 8)
    result.synonyms = _clean_list(result.synonyms, 6)
    result.related_concepts = _clean_list(result.related_concepts, 6)
    result.search_queries = _clean_list(result.search_queries, 5)
    if not result.search_queries:
        raise GeminiError("Gemini 沒有產生可用的搜尋詞，請換個說法再試。")
    return result

# ===================== Phase 4：論文研究主題分類（追加在檔案最底下）=====================
class Category(BaseModel):
    name: str                    # 分類名稱（繁體中文）
    description: str             # 分類內容說明
    research_questions: list[str]  # 此分類的論文主要探討的研究問題
    paper_ids: list[str]         # 論文代號（P1、P2…），不是標題


class ClassificationResult(BaseModel):
    categories: list[Category]


MAX_PAPERS_FOR_AI = 60  # 一次最多交給 Gemini 分類的論文數
ABSTRACT_CHAR_LIMIT = 700  # 每篇摘要最多送出的字數，避免內容過長


def _build_paper_block(df):
    """把論文整理成給 Gemini 的文字，並建立 代號 -> OpenAlex ID 的對照表。"""
    blocks, id_map = [], {}
    for i, row in enumerate(df.itertuples(), start=1):
        pid = f"P{i}"
        id_map[pid] = row.openalex_id
        if row.has_abstract:
            abstract = row.abstract[:ABSTRACT_CHAR_LIMIT]
        else:
            abstract = "（無摘要，僅有標題，請勿推測其內容）"
        blocks.append(f"[{pid}] 標題：{row.title}\n年份：{row.year}\n摘要：{abstract}")
    return "\n\n".join(blocks), id_map


def classify_papers(df, topic):
    """把論文分成 3~6 個研究分類。
    回傳 (加上 category 欄位的 DataFrame, 分類清單, 驗證統計)。"""
    if df is None or len(df) < 5:
        raise GeminiError("論文數量太少（至少需要 5 篇）才能進行分類，請放寬搜尋條件。")

    df = df.head(MAX_PAPERS_FOR_AI).copy()
    paper_text, id_map = _build_paper_block(df)

    prompt = f"""你是學術研究分析助理。使用者的研究主題是：「{topic}」

以下是從 OpenAlex 取得的 {len(df)} 篇論文（標題、年份、摘要）。請依據這些論文的內容，歸納成 3 到 6 個主要研究分類。

規則：
1. 分類必須以下列論文的實際內容為依據，不要使用任何預設的固定分類。
2. 每篇論文只歸入一個最適合的分類，並且每篇都要被歸類。
3. paper_ids 只能填入下列清單中出現的代號（如 P1、P2），不可自行創造代號，也不可寫出標題。
4. 標示「無摘要」的論文，只能根據標題判斷，不可推測其研究內容。
5. name 使用繁體中文，簡短明確。
6. description：用 2 到 3 句繁體中文說明這個分類的論文實際在探討什麼，不要加入論文中沒有出現的內容。
7. research_questions：列出 2 到 3 個此分類論文主要探討的研究問題，必須能從該分類的論文標題或摘要中看出。

論文清單：

{paper_text}"""

    result = call_gemini_json(prompt, ClassificationResult)

    # ---------- Python 端驗證 ----------
    valid_ids = set(id_map.keys())
    assigned = set()
    invalid_dropped = 0
    duplicate_dropped = 0
    categories = []

    for cat in result.categories:
        clean_ids = []
        for pid in cat.paper_ids:
            pid = pid.strip().upper()
            if pid not in valid_ids:
                invalid_dropped += 1      # Gemini 編造的代號
            elif pid in assigned:
                duplicate_dropped += 1    # 已經被前面的分類使用
            else:
                assigned.add(pid)
                clean_ids.append(pid)
        if clean_ids:  # 沒有任何有效論文的分類直接捨棄
            categories.append({
                "name": cat.name.strip(),
                "description": cat.description.strip(),
                "research_questions": [q.strip() for q in cat.research_questions if q.strip()],
                "paper_ids": [id_map[p] for p in clean_ids],  # 轉回真正的 OpenAlex ID
            })

    unassigned = [pid for pid in id_map if pid not in assigned]
    if unassigned:
        categories.append({
            "name": "未分類",
            "description": "AI 未能明確歸類的論文，建議使用者自行閱讀判斷。",
            "research_questions": [],
            "paper_ids": [id_map[p] for p in unassigned],
        })

    if not any(c["name"] != "未分類" for c in categories):
        raise GeminiError("AI 沒有產生有效的分類，請再試一次。")

    # 加上 category 欄位，並統計每個分類中「只靠標題判斷」的論文數
    id_to_category = {oid: c["name"] for c in categories for oid in c["paper_ids"]}
    df["category"] = df["openalex_id"].map(id_to_category)
    abstract_flag = df.set_index("openalex_id")["has_abstract"].to_dict()
    for c in categories:
        c["n_papers"] = len(c["paper_ids"])
        c["n_title_only"] = sum(1 for oid in c["paper_ids"] if not abstract_flag[oid])

    stats = {
        "papers_sent": len(df),
        "invalid_ids_dropped": invalid_dropped,
        "duplicate_assignments_dropped": duplicate_dropped,
        "unassigned": len(unassigned),
    }
    return df, categories, stats

# ===================== Phase 5：趨勢解釋（追加在檔案最底下）=====================
class TrendInterpretation(BaseModel):
    inferences: list[str]   # AI 的推論（不是數據事實）
    limitations: list[str]  # 這份分析的限制


_NUM = r"\d+(?:\.\d+)?"

FIELD_NAME_ZH = {
    "full_db_year_counts": "資料庫中符合搜尋詞的論文年度數量",
    "sample_year_counts": "樣本年度數量",
    "category_year_counts": "各分類年度數量",
    "category_counts": "各分類論文數",
}

def interpret_trends(facts, categories, topic):
    """讓 Gemini 根據 Python 算出的數據，提出趨勢推論。
    回傳 {"inferences": [{"text", "unverified_numbers"}], "limitations": [...]}"""
    facts_json = json.dumps(facts, ensure_ascii=False, indent=1)
    cat_text = "\n".join(
        f"- {c['name']}：{c['description']}" for c in categories if c["name"] != "未分類"
    )

    prompt = f"""你是學術研究趨勢分析助理。使用者的研究主題是：「{topic}」

下面是由程式根據 OpenAlex 實際資料統計出的數據（JSON），以及各研究分類的說明。

【統計數據】
{facts_json}

【研究分類】
{cat_text}

請根據以上資料，提出對研究趨勢的解讀：
1. inferences：3 到 5 則「推論」，使用繁體中文，語氣保留彈性（例如「可能」、「或許」、「從樣本來看」）。
2. limitations：2 到 3 則這份分析的限制。

嚴格規則：
- 只能使用上面統計數據中已經出現的數字；不可自行計算百分比、成長率或平均值，不可編造任何數字。
- 這些是推論而非事實，不可寫成確定的結論，也不可說明因果關係。
- sample_year_counts 與 category_counts 來自「依相關度排序後取得的前 {facts['sample_size']} 篇」，不是隨機樣本，不能代表整個領域。
- full_db_year_counts（若有）才是資料庫中符合搜尋詞的論文年度數量，但仍受搜尋詞與資料庫收錄範圍限制。
- {facts['current_year']} 年尚未結束，不可把該年度數量較少解讀為研究減少。
- 不可因為某主題沒有出現在資料中，就說該主題沒有人研究過。
- 文字中不可出現程式欄位名稱（如 full_db_year_counts、category_counts），請用中文描述，例如「資料庫中符合搜尋詞的論文」、「樣本中的論文」。"""

    result = call_gemini_json(prompt, TrendInterpretation)

    # Python 端檢查：找出 AI 文字中，不在我們提供的數據裡的數字
    allowed = set(re.findall(_NUM, facts_json))
    inferences = []
    for text in result.inferences[:6]:
        text = text.strip()

        for field, zh in FIELD_NAME_ZH.items():
            text = text.replace(field, zh)        
        if text:
            unverified = sorted({n for n in re.findall(_NUM, text) if n not in allowed})
            inferences.append({"text": text, "unverified_numbers": unverified})
    limitations = [t.strip() for t in result.limitations if t.strip()][:4]
    if not inferences:
        raise GeminiError("AI 沒有產生可用的趨勢解讀，請再試一次。")
    return {"inferences": inferences, "limitations": limitations}

# ===================== Phase 6：研究問題與潛在研究方向（追加在檔案最底下）=====================
class Finding(BaseModel):
    statement: str
    paper_ids: list[str]


class Direction(BaseModel):
    name: str
    description: str
    research_questions: list[str]
    paper_ids: list[str]
    methods: list[str]
    feasibility: str
    undergrad_suitable: bool


class ExplorationResult(BaseModel):
    supported_findings: list[Finding]   # A：文獻已支持的發現
    reasoned_inferences: list[Finding]  # B：根據文獻的合理推論
    open_questions: list[Finding]       # 尚待釐清的問題
    directions: list[Direction]         # C：AI 提出的待驗證研究構想


EXPLORE_ABSTRACT_LIMIT = 500
OVERCLAIM_PHRASES = ["尚無研究", "尚未有研究", "沒有人研究", "無人研究", "從未被研究", "學術界尚未", "首次",
                     "普遍", "證實", "證明", "導致", "一致顯示"]

def _build_exploration_block(df):
    """整理給 Gemini 的論文清單（含分類），並建立 代號 -> OpenAlex ID 對照表。"""
    blocks, id_map = [], {}
    for i, row in enumerate(df.itertuples(), start=1):
        pid = f"P{i}"
        id_map[pid] = row.openalex_id
        abstract = (row.abstract[:EXPLORE_ABSTRACT_LIMIT] if row.has_abstract
                    else "（無摘要，僅有標題，請勿推測其內容）")
        cat = getattr(row, "category", None)
        if not isinstance(cat, str) or not cat:
            cat = "未分類"
        blocks.append(f"[{pid}] 分類：{cat}\n標題：{row.title}\n年份：{row.year}\n摘要：{abstract}")
    return "\n\n".join(blocks), id_map


def _resolve_ids(raw_ids, id_map, counter):
    """把 Gemini 回傳的代號轉成真正的 OpenAlex ID，不存在的代號丟棄並計數。"""
    clean, seen = [], set()
    for pid in raw_ids or []:
        pid = str(pid).strip().upper()
        if pid not in id_map:
            counter["invalid"] += 1
        elif pid not in seen:
            seen.add(pid)
            clean.append(id_map[pid])
    return clean


def _make_flags(text, oa_ids, has_abs, need_support):
    flags = []
    if need_support and not oa_ids:
        flags.append("沒有有效對應文獻，需自行查證")
    elif oa_ids and not any(has_abs.get(o) for o in oa_ids):
        flags.append("對應文獻均無摘要，僅依標題判斷")
    over = [p for p in OVERCLAIM_PHRASES if p in text]
    if over:
        flags.append("用詞可能過度斷言（" + "、".join(over) + "），請自行查證")
    return flags


def explore_research_directions(df, categories, topic):
    """根據論文與分類，產生 A 已支持發現 / B 合理推論 / 待釐清問題 / C 待驗證研究方向。"""
    if df is None or len(df) < 5:
        raise GeminiError("論文數量太少（至少需要 5 篇）才能進行研究方向探索。")

    df = df.head(MAX_PAPERS_FOR_AI)
    paper_text, id_map = _build_exploration_block(df)
    has_abs = df.set_index("openalex_id")["has_abstract"].to_dict()
    cat_text = "\n".join(f"- {c['name']}：{c['description']}" for c in categories if c["name"] != "未分類")

    prompt = f"""你是學術研究方向顧問，正在協助大學生探索研究題目。使用者的研究主題是：「{topic}」

以下是從 OpenAlex 取得的 {len(df)} 篇論文（含 AI 先前歸納的分類），以及各分類的說明。

【研究分類】
{cat_text}

【論文清單】
{paper_text}

請輸出四個部分，每一則都要在 paper_ids 填入支持它的論文代號（如 P3、P12）：

1. supported_findings（4 到 6 則）：文獻「已經明確呈現」的發現或主要研究問題，必須是論文標題或摘要中看得到的內容，並附上對應論文代號（至少 1 篇）。
2. reasoned_inferences（3 到 5 則）：綜合多篇論文後的合理推論，例如不同研究的共同點、差異或可能的原因。語氣要保留彈性（「可能」、「或許」）。
3. open_questions（3 到 5 則）：在這批論文中看起來還不夠清楚、值得進一步釐清的問題。
4. directions（4 到 5 個，其中至少 2 個 undergrad_suitable 為 true）：AI 提出的待驗證研究構想。每個包含 name、description、research_questions（2 到 3 個）、paper_ids（相關論文）、methods（2 到 3 種適合的研究方法，例如問卷調查、半結構式訪談、準實驗設計、內容分析）、feasibility（可行性與需要注意的限制，說明資料取得、樣本、倫理或時間等現實條件）、undergrad_suitable（是否適合大學生在一學期內完成）。

嚴格規則：
- paper_ids 只能使用上面出現的代號，不可自行創造，不可寫出論文標題。
- 標示「無摘要」的論文只能根據標題判斷，不可推測其研究內容。
- 全部使用繁體中文。
- 這些只是依據這批論文所做的整理與構想，不是已發表的研究結果，不可把構想寫成已被證實的事實。
- 不可因為某主題沒有出現在這批論文中，就說該主題「尚未被研究」或「沒有人研究」；請改用「在這批論文中較少看到」這類說法。
- 不可編造任何論文、作者、年份、數字或研究結果。"""

    result = call_gemini_json(prompt, ExplorationResult)

    counter = {"invalid": 0, "downgraded": 0}
    supported, inferences, open_qs, directions = [], [], [], []

    for f in result.supported_findings:
        text = f.statement.strip()
        if not text:
            continue
        ids = _resolve_ids(f.paper_ids, id_map, counter)
        if ids:
            supported.append({"text": text, "paper_ids": ids,
                              "flags": _make_flags(text, ids, has_abs, False)})
        else:  # 標示為「已支持」卻沒有有效文獻：降級為推論
            counter["downgraded"] += 1
            flags = ["原標示為文獻已支持，但沒有有效對應文獻，已降級為推論"] + _make_flags(text, ids, has_abs, False)
            inferences.append({"text": text, "paper_ids": [], "flags": flags})

    for f in result.reasoned_inferences:
        text = f.statement.strip()
        if text:
            ids = _resolve_ids(f.paper_ids, id_map, counter)
            inferences.append({"text": text, "paper_ids": ids,
                               "flags": _make_flags(text, ids, has_abs, False)})

    for f in result.open_questions:
        text = f.statement.strip()
        if text:
            ids = _resolve_ids(f.paper_ids, id_map, counter)
            open_qs.append({"text": text, "paper_ids": ids,
                            "flags": _make_flags(text, ids, has_abs, False)})

    for d in result.directions:
        name = d.name.strip()
        if not name:
            continue
        ids = _resolve_ids(d.paper_ids, id_map, counter)
        full_text = name + d.description + d.feasibility
        directions.append({
            "name": name,
            "description": d.description.strip(),
            "research_questions": [q.strip() for q in d.research_questions if q.strip()],
            "methods": [m.strip() for m in d.methods if m.strip()],
            "feasibility": d.feasibility.strip(),
            "undergrad_suitable": bool(d.undergrad_suitable),
            "paper_ids": ids,
            "flags": _make_flags(full_text, ids, has_abs, True),
        })

    if not directions and not supported:
        raise GeminiError("AI 沒有產生可用的內容，請再試一次。")

    stats = {"papers_sent": len(df), "invalid_ids_dropped": counter["invalid"],
             "downgraded_to_inference": counter["downgraded"]}
    return {"supported": supported, "inferences": inferences,
            "open_questions": open_qs, "directions": directions}, stats