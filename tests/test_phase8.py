# test_phase8.py  （系統測試：自動檢查資料正確性與錯誤處理，並產生 test_results.md）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import re
import time
from datetime import datetime

import services.gemini_service as g
import services.openalex_service as o
from config import GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_THINKING_LEVEL
from services.gemini_service import (expand_keywords, classify_papers, interpret_trends,
                                     explore_research_directions, GeminiError)
from services.openalex_service import search_multi, search_papers, fetch_year_counts, OpenAlexError
from utils.data_processor import build_trend_facts, recommend_reading
from utils.report import build_markdown_report

# 可以自行替換主題。建議同時包含：中文常見主題、中文跨領域主題、英文技術性主題
TOPICS = [
    "生成式 AI 對大學生學習的影響",
    "遠距工作對員工生產力的影響",
    "Quantum error correction in superconducting qubits",
]
YEAR_FROM, YEAR_TO, MAX_RESULTS = 2020, datetime.now().year, 40
SECTIONS = ("supported", "inferences", "open_questions")


def count_flags(ex):
    n = sum(len(it["flags"]) for sec in SECTIONS for it in ex[sec])
    return n + sum(len(d["flags"]) for d in ex["directions"])


def run_topic(topic):
    r = {"topic": topic, "error": None, "timing": {}, "checks": [], "metrics": {}}
    t, m = r["timing"], r["metrics"]
    try:
        s = time.time()
        kw = expand_keywords(topic)
        t["關鍵字擴展"] = time.time() - s
        queries = kw.search_queries
        r["queries"] = queries

        s = time.time()
        df, stats = search_multi(queries, YEAR_FROM, YEAR_TO, MAX_RESULTS)
        t["OpenAlex 搜尋"] = time.time() - s
        m["論文數"] = len(df)
        m["各搜尋詞在 OpenAlex 的命中數"] = stats["per_query_total"]
        if len(df) < 5:
            r["error"] = f"只取得 {len(df)} 篇論文（少於 5 篇），略過 AI 分析"
            return r
        m["有摘要"], m["無摘要"] = stats["with_abstract"], stats["without_abstract"]

        full = None
        try:
            full = fetch_year_counts(queries[0], YEAR_FROM, YEAR_TO)
        except OpenAlexError:
            pass

        s = time.time()
        df2, cats, cstats = classify_papers(df, topic)
        t["AI 分類"] = time.time() - s

        facts = build_trend_facts(df2, full)
        s = time.time()
        interp = interpret_trends(facts, cats, topic)
        t["AI 趨勢解讀"] = time.time() - s

        s = time.time()
        ex, estats = explore_research_directions(df2, cats, topic)
        t["AI 研究方向"] = time.time() - s
    except (GeminiError, OpenAlexError) as e:
        r["error"] = str(e)
        return r

    # ---------- 指標 ----------
    m["分類數（不含未分類）"] = sum(1 for c in cats if c["name"] != "未分類")
    m["未分類論文數"] = cstats["unassigned"]
    m["僅依標題判斷的論文數（分類中）"] = sum(c["n_title_only"] for c in cats)
    m["分類階段：被丟棄的不存在代號"] = cstats["invalid_ids_dropped"]
    m["研究方向階段：被丟棄的不存在代號"] = estats["invalid_ids_dropped"]
    m["「已支持」被降級為推論"] = estats["downgraded_to_inference"]
    m["研究方向頁的 ⚠ 標記數"] = count_flags(ex)
    m["趨勢推論中「數據找不到的數字」"] = sum(len(i["unverified_numbers"]) for i in interp["inferences"])
    m["研究方向數"] = len(ex["directions"])

    # ---------- 自動檢查 ----------
    ids = set(df2["openalex_id"])
    yrs = df2["year"].dropna().astype(int)
    ai_ids = ([i for c in cats for i in c["paper_ids"]]
              + [i for sec in SECTIONS for it in ex[sec] for i in it["paper_ids"]]
              + [i for d in ex["directions"] for i in d["paper_ids"]])
    a = {"df": df2, "categories": cats, "cls_stats": cstats, "facts": facts,
         "full_counts": full, "interp": interp, "explore": ex, "explore_stats": estats}
    report = build_markdown_report(topic, kw, queries, YEAR_FROM, YEAR_TO, stats, a, recommend_reading(df2))
    report_ids = set(re.findall(r"https://openalex\.org/W\d+", report))

    def check(name, ok, detail=""):
        r["checks"].append((name, bool(ok), detail))

    check("論文沒有重複", df2["openalex_id"].is_unique)
    check("出版年份都在設定範圍內", yrs.between(YEAR_FROM, YEAR_TO).all(), f"{yrs.min()}–{yrs.max()}")
    check("每篇論文都有分類", df2["category"].notna().all())
    check("各分類篇數加總 = 論文數", sum(c["n_papers"] for c in cats) == len(df2))
    check("年度統計加總 = 有年份的論文數", sum(facts["sample_year_counts"].values()) == len(yrs))
    check("AI 引用的論文都存在於搜尋結果", all(i in ids for i in ai_ids), f"共 {len(ai_ids)} 筆引用")
    check("A 區每則發現都有對應論文", all(it["paper_ids"] for it in ex["supported"]))
    check("每個研究方向都有對應論文", all(d["paper_ids"] for d in ex["directions"]))
    check("報告中的 OpenAlex 連結都來自搜尋結果", report_ids <= ids, f"{len(report_ids)} 個連結")
    check("報告包含全部章節",
          all(h in report for h in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 附錄")))
    return r


def failure_tests():
    """暫時替換設定，模擬各種失敗情況，確認程式回報清楚的錯誤訊息而不是當機。"""
    out = []

    def attempt(name, fn, restore, should_error=True):
        try:
            res = fn()
            if should_error:
                out.append((name, False, "沒有出現錯誤（若服務對這種情況本來就不報錯，屬正常）"))
            else:
                out.append((name, True, res))
        except (GeminiError, OpenAlexError) as e:
            out.append((name, should_error, str(e)[:160]))
        except Exception as e:  # 未被處理的例外代表程式有漏洞
            out.append((name, False, f"未處理的例外 {type(e).__name__}：{str(e)[:120]}"))
        finally:
            restore()

    orig = (g.GEMINI_API_KEY, g.GEMINI_MODEL, g.GEMINI_FALLBACK_MODEL,
            o.OPENALEX_API_KEY, o.OPENALEX_BASE_URL)

    def restore():
        g.GEMINI_API_KEY, g.GEMINI_MODEL, g.GEMINI_FALLBACK_MODEL = orig[:3]
        o.OPENALEX_API_KEY, o.OPENALEX_BASE_URL = orig[3:]

    g.GEMINI_API_KEY = "invalid-key"
    attempt("Gemini 金鑰無效", lambda: expand_keywords("測試主題"), restore)

    g.GEMINI_MODEL, g.GEMINI_FALLBACK_MODEL = "not-a-real-model", ""
    attempt("Gemini 模型名稱不存在", lambda: expand_keywords("測試主題"), restore)

    attempt("使用者沒有輸入主題", lambda: expand_keywords("   "), restore)

    o.OPENALEX_API_KEY = "invalid-key"
    attempt("OpenAlex 金鑰無效", lambda: search_papers("test", max_results=5), restore)

    o.OPENALEX_BASE_URL = "https://api.openalex.invalid"
    attempt("OpenAlex 無法連線", lambda: search_papers("test", max_results=5), restore)

    attempt("搜尋不到任何論文（應回傳空結果，不是錯誤）",
            lambda: f"回傳 {len(search_multi(['zxqvbnm asdfghjkl qwertyuiop'], 2020, YEAR_TO, 10)[0])} 篇",
            restore, should_error=False)
    return out


DEFAULT_LOG_PATH = str(Path(__file__).resolve().parent / "test_results.md")


def write_log(results, failures, path=DEFAULT_LOG_PATH):
    L = [f"# 系統測試紀錄（{datetime.now():%Y-%m-%d %H:%M}）", "",
         f"- 主要模型：{GEMINI_MODEL}｜備用模型：{GEMINI_FALLBACK_MODEL or '無'}｜思考等級：{GEMINI_THINKING_LEVEL or '預設'}",
         f"- 搜尋條件：{YEAR_FROM}–{YEAR_TO} 年，論文數量上限 {MAX_RESULTS}", ""]
    for res in results:
        L += [f"## 主題：{res['topic']}", ""]
        if res.get("queries"):
            L += ["- AI 產生的搜尋詞：" + "；".join(res["queries"])]
        if res["error"]:
            L += [f"- ⚠ 測試中斷：{res['error']}", ""]
            continue
        L += ["- 各步驟耗時：" + "｜".join(f"{k} {v:.1f} 秒" for k, v in res["timing"].items()),
              f"- 總耗時：{sum(res['timing'].values()):.1f} 秒", "", "**指標**", ""]
        L += [f"- {k}：{v}" for k, v in res["metrics"].items()]
        L += ["", "**自動檢查**", "", "| 檢查項目 | 結果 | 說明 |", "|---|---|---|"]
        L += [f"| {n} | {'通過' if ok else '未通過'} | {d} |" for n, ok, d in res["checks"]]
        L += ["", "**人工抽查（請自行填寫）**", "",
              "- 隨機抽 5 篇論文，與主題相關的有：＿＿ / 5 篇",
              "- 抽查 A 區 2 則發現，摘要是否支持：＿＿",
              "- 分類是否合理、有沒有明顯錯分：＿＿", ""]
    L += ["## 錯誤處理與空資料測試", "", "| 情境 | 結果 | 系統回報的訊息 |", "|---|---|---|"]
    L += [f"| {n} | {'通過' if ok else '未通過'} | {d} |" for n, ok, d in failures]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    results = []
    for i, topic in enumerate(TOPICS, 1):
        if i > 1:
            print("   為避免觸發免費額度的速率限制，等待 60 秒…")
            time.sleep(60)
        print(f"[{i}/{len(TOPICS)}] 測試主題：{topic}")
        res = run_topic(topic)
        results.append(res)
        if res["error"]:
            print("   中斷：", res["error"])
        else:
            bad = [n for n, ok, _ in res["checks"] if not ok]
            print(f"   耗時 {sum(res['timing'].values()):.1f} 秒｜自動檢查未通過：{bad or '無'}")
    print("\n執行錯誤處理測試…")
    failures = failure_tests()
    for n, ok, d in failures:
        print(f"   {'通過' if ok else '未通過'}｜{n}｜{d}")
    write_log(results, failures)
    print("\n已產生 test_results.md")