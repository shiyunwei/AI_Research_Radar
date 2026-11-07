# test_phase6.py  （暫時的測試檔）
import json, os, time
import pandas as pd
from services.openalex_service import search_papers
from services.gemini_service import classify_papers, explore_research_directions, GeminiError
from services.gemini_service import LAST_CALL_INFO

TOPIC = "生成式 AI 對大學生學習的影響"
QUERY = "generative AI university students learning"
CACHE_DF, CACHE_CAT = "cache_df.pkl", "cache_categories.json"

# 為了節省額度與時間，論文與分類結果會存成快取。想重新分類，刪掉這兩個檔案即可。
if os.path.exists(CACHE_DF) and os.path.exists(CACHE_CAT):
    df2 = pd.read_pickle(CACHE_DF)
    categories = json.load(open(CACHE_CAT, encoding="utf-8"))
    print(f"讀取快取：{len(df2)} 篇論文、{len(categories)} 個分類")
else:
    df, _ = search_papers(QUERY, year_from=2020, year_to=2026, max_results=40)
    df2, categories, _ = classify_papers(df, TOPIC)
    df2.to_pickle(CACHE_DF)
    json.dump(categories, open(CACHE_CAT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"完成搜尋與分類並存入快取：{len(df2)} 篇")

info = {r.openalex_id: (r.year, r.title) for r in df2.itertuples()}


def show_refs(ids):
    for oid in ids[:3]:
        year, title = info[oid]
        print(f"      ↳ ({year}) {title[:65]}")
        print(f"        {oid}")


def show_items(items):
    for it in items:
        print(f"  • {it['text']}")
        show_refs(it["paper_ids"])
        for fl in it["flags"]:
            print(f"      ⚠ {fl}")


print("\n=== 呼叫 Gemini 探索研究方向 ===")
t0 = time.time()
try:
    result, stats = explore_research_directions(df2, categories, TOPIC)
except GeminiError as e:
    raise SystemExit(f"錯誤：{e}")
print(f"耗時 {time.time() - t0:.1f} 秒")
print("呼叫診斷：", LAST_CALL_INFO)
print("驗證統計：", stats)

print("\n######## A. 文獻已支持的發現 ########")
show_items(result["supported"])
print("\n######## B. 根據文獻的合理推論 ########")
show_items(result["inferences"])
print("\n######## 待釐清的問題 ########")
show_items(result["open_questions"])

print("\n######## C. AI 提出的待驗證研究構想 ########")
for d in result["directions"]:
    tag = "適合大學生" if d["undergrad_suitable"] else "較難在一學期完成"
    print(f"\n【{d['name']}】（{tag}）")
    print("說明：", d["description"])
    for q in d["research_questions"]:
        print("  ? ", q)
    print("研究方法：", "、".join(d["methods"]))
    print("可行性與限制：", d["feasibility"])
    print("相關論文：")
    show_refs(d["paper_ids"])
    for fl in d["flags"]:
        print(f"  ⚠ {fl}")