# services/openalex_service.py
# 負責向 OpenAlex 取得真實論文資料，並整理成 DataFrame
import math
import requests
import pandas as pd
from config import OPENALEX_API_KEY, OPENALEX_BASE_URL
import re

COLUMNS = [
    "openalex_id", "title", "authors", "year", "abstract", "has_abstract",
    "doi", "openalex_url", "source_url", "cited_by_count",
    "is_oa", "oa_url", "primary_topic", "topics",
]


class OpenAlexError(Exception):
    """OpenAlex 相關錯誤，訊息可直接顯示給使用者。"""

def _safe(e):
    """把例外訊息中的 API 金鑰遮蔽掉，避免在畫面或紀錄中洩漏。"""
    return re.sub(r"api_key=[^&\s'\"]+", "api_key=***", str(e))[:200]


def rebuild_abstract(inverted_index):
    """把 OpenAlex 的倒排索引 {單字: [位置,...]} 還原成一段文字。沒有摘要則回傳空字串。"""
    if not inverted_index:
        return ""
    pairs = []
    for word, positions in inverted_index.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort()
    return " ".join(word for _, word in pairs)


def parse_work(work):
    """把一筆 OpenAlex 原始資料轉成我們需要的欄位。缺少的欄位一律給安全的預設值。"""
    authors = [
        a.get("author", {}).get("display_name")
        for a in (work.get("authorships") or [])
    ]
    authors = [a for a in authors if a]

    topics = [t.get("display_name") for t in (work.get("topics") or [])]
    topics = [t for t in topics if t]

    primary_topic = (work.get("primary_topic") or {}).get("display_name")
    open_access = work.get("open_access") or {}
    primary_location = work.get("primary_location") or {}
    abstract = rebuild_abstract(work.get("abstract_inverted_index"))

    return {
        "openalex_id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "authors": "; ".join(authors),
        "year": work.get("publication_year"),
        "abstract": abstract,
        "has_abstract": bool(abstract),
        "doi": work.get("doi"),
        "openalex_url": work.get("id"),
        "source_url": primary_location.get("landing_page_url") or work.get("doi"),
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": bool(open_access.get("is_oa")),
        "oa_url": open_access.get("oa_url"),
        "primary_topic": primary_topic,
        "topics": "; ".join(topics),
    }


def fetch_works(query, year_from=None, year_to=None, max_results=50, only_with_abstract=False):
    """呼叫 OpenAlex /works 搜尋論文，回傳 (原始資料清單, 符合條件總數)。"""
    if not OPENALEX_API_KEY:
        raise OpenAlexError("找不到 OPENALEX_API_KEY，請檢查 .env 設定。")

    filters = []
    if year_from and year_to:
        filters.append(f"publication_year:{year_from}-{year_to}")
    elif year_from:
        filters.append(f"publication_year:{year_from}-")
    elif year_to:
        filters.append(f"publication_year:-{year_to}")
    if only_with_abstract:
        filters.append("has_abstract:true")

    per_page = min(100, max_results)
    total_pages = math.ceil(max_results / per_page)
    works, total_count = [], 0

    for page in range(1, total_pages + 1):
        params = {
            "search": query,
            "per_page": per_page,
            "page": page,
            "api_key": OPENALEX_API_KEY,
        }
        if filters:
            params["filter"] = ",".join(filters)

        try:
            response = requests.get(f"{OPENALEX_BASE_URL}/works", params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            code = response.status_code
            if code in (401, 403):
                raise OpenAlexError("OpenAlex 金鑰無效或沒有權限，請確認 .env 中的金鑰。")
            if code == 429:
                raise OpenAlexError("OpenAlex 使用額度已達上限，請稍後或明天再試。")
            raise OpenAlexError(f"OpenAlex 回傳錯誤（狀態碼 {code}）：{response.text[:200]}")
        except requests.exceptions.Timeout:
            raise OpenAlexError("連線 OpenAlex 逾時，請檢查網路後再試。")
        except requests.exceptions.RequestException as e:
            raise OpenAlexError(f"無法連線到 OpenAlex：{_safe(e)}")

        data = response.json()
        total_count = data.get("meta", {}).get("count", 0)
        batch = data.get("results", [])
        works.extend(batch)
        if len(batch) < per_page:  # 已經沒有更多結果
            break

    return works[:max_results], total_count


def clean_dataframe(df):
    """去除缺標題與重複的論文，回傳 (乾淨 DataFrame, 統計資訊)。"""
    stats = {"fetched": len(df), "missing_title": 0, "duplicates_removed": 0}
    if df.empty:
        return df, stats

    before = len(df)
    df = df[df["title"].notna() & (df["title"].str.strip() != "")]
    stats["missing_title"] = before - len(df)

    # 先用 OpenAlex ID 去重，再用「標題(小寫去空白) + 年份」去重
    before = len(df)
    df = df.drop_duplicates(subset="openalex_id")
    df = df.assign(_key=df["title"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip())
    df = df.drop_duplicates(subset=["_key", "year"]).drop(columns="_key")
    stats["duplicates_removed"] = before - len(df)

    return df.reset_index(drop=True), stats


def search_papers(query, year_from=None, year_to=None, max_results=50, only_with_abstract=False):
    """對外主要函式：搜尋 → 解析 → 清理，回傳 (DataFrame, 統計資訊)。"""
    works, total_count = fetch_works(query, year_from, year_to, max_results, only_with_abstract)
    df = pd.DataFrame([parse_work(w) for w in works], columns=COLUMNS)
    df, stats = clean_dataframe(df)

    stats["total_in_openalex"] = total_count
    stats["final_count"] = len(df)
    stats["with_abstract"] = int(df["has_abstract"].sum()) if not df.empty else 0
    stats["without_abstract"] = stats["final_count"] - stats["with_abstract"]
    return df, stats

# ===================== Phase 5：資料庫整體年度數量（追加在檔案最底下）=====================
def fetch_year_counts(query, year_from=None, year_to=None):
    """用 OpenAlex 的 group_by 取得「資料庫中所有符合搜尋詞的論文」各年份數量。
    回傳 DataFrame（欄位 year, count），依年份排序。"""
    if not OPENALEX_API_KEY:
        raise OpenAlexError("找不到 OPENALEX_API_KEY，請檢查 .env 設定。")

    params = {"search": query, "group_by": "publication_year", "api_key": OPENALEX_API_KEY}
    if year_from and year_to:
        params["filter"] = f"publication_year:{year_from}-{year_to}"
    elif year_from:
        params["filter"] = f"publication_year:{year_from}-"
    elif year_to:
        params["filter"] = f"publication_year:-{year_to}"

    try:
        response = requests.get(f"{OPENALEX_BASE_URL}/works", params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        raise OpenAlexError(f"取得年度統計失敗（狀態碼 {response.status_code}）。")
    except requests.exceptions.RequestException as e:
        raise OpenAlexError(f"無法連線到 OpenAlex：{_safe(e)}")

    rows = []
    for g in response.json().get("group_by", []):
        try:
            rows.append({"year": int(g["key"]), "count": int(g["count"])})
        except (KeyError, ValueError, TypeError):
            continue  # 略過格式異常的項目
    df = pd.DataFrame(rows, columns=["year", "count"])
    return df.sort_values("year").reset_index(drop=True)

# ===================== Phase 7a：多組搜尋詞合併（追加在檔案最底下）=====================
def search_multi(queries, year_from=None, year_to=None, max_results=50, only_with_abstract=False):
    """用多組搜尋詞各搜一次，輪流取各組的高相關論文，合併去重後回傳 (DataFrame, 統計資訊)。"""
    queries = [q.strip() for q in queries if q and q.strip()]
    if not queries:
        raise OpenAlexError("請至少提供一組搜尋詞。")

    # 每組多抓一些，去重後才夠數量
    per_query = max(10, math.ceil(max_results * 1.5 / len(queries)))
    frames, per_query_total = [], {}

    for q in queries:
        df_q, s_q = search_papers(q, year_from, year_to, per_query, only_with_abstract)
        per_query_total[q] = s_q["total_in_openalex"]
        if not df_q.empty:
            df_q = df_q.copy()
            df_q["_rank"] = range(len(df_q))  # 這篇在該搜尋詞中的相關度名次
            frames.append(df_q)

    if not frames:
        empty = pd.DataFrame(columns=COLUMNS)
        return empty, {"fetched": 0, "duplicates_removed": 0, "final_count": 0,
                       "with_abstract": 0, "without_abstract": 0, "per_query_total": per_query_total}

    combined = pd.concat(frames, ignore_index=True)
    fetched = len(combined)
    combined = combined.sort_values("_rank", kind="stable")  # 各搜尋詞輪流排序
    combined, clean_stats = clean_dataframe(combined)
    combined = combined.drop(columns="_rank").head(max_results).reset_index(drop=True)

    with_abs = int(combined["has_abstract"].sum())
    stats = {
        "fetched": fetched,
        "duplicates_removed": clean_stats["duplicates_removed"] + clean_stats["missing_title"],
        "final_count": len(combined),
        "with_abstract": with_abs,
        "without_abstract": len(combined) - with_abs,
        "per_query_total": per_query_total,
    }
    return combined, stats