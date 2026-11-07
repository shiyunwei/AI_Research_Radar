# test_phase4.py  （暫時的測試檔）
from services.openalex_service import search_papers
from services.gemini_service import classify_papers, GeminiError

TOPIC = "生成式 AI 對大學生學習的影響"

print("=== 取得論文 ===")
df, s = search_papers("generative AI university students learning",
                      year_from=2022, year_to=2026, max_results=40)
print(f"取得 {s['final_count']} 篇（有摘要 {s['with_abstract']}、無摘要 {s['without_abstract']}）")

print("\n=== 測試 1：AI 分類 ===")
try:
    df2, categories, stats = classify_papers(df, TOPIC)
except GeminiError as e:
    raise SystemExit(f"錯誤：{e}")

print("驗證統計：", stats)
total = 0
for c in categories:
    total += c["n_papers"]
    print("\n" + "=" * 50)
    print(f"【{c['name']}】共 {c['n_papers']} 篇（其中 {c['n_title_only']} 篇僅靠標題判斷）")
    print("說明：", c["description"])
    for q in c["research_questions"]:
        print("  ? ", q)
    print("對應論文：")
    for oid in c["paper_ids"][:3]:
        row = df2[df2["openalex_id"] == oid].iloc[0]
        print(f"  - ({row['year']}) {row['title'][:70]}")
        print(f"    {oid}")

print(f"\n各分類論文數加總：{total}，送出論文數：{stats['papers_sent']}")
print("category 欄位是否有缺值：", df2["category"].isna().any())

print("\n=== 測試 2：論文太少（測試錯誤處理）===")
try:
    classify_papers(df.head(3), TOPIC)
except GeminiError as e:
    print("預期中的錯誤訊息：", e)