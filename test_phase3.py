# test_phase3.py  （暫時的測試檔）
from services.gemini_service import expand_keywords, GeminiError
from services.openalex_service import search_papers, OpenAlexError

print("=== 測試 1：關鍵字擴展 ===")
try:
    result = expand_keywords("生成式 AI 對大學生學習的影響")
    print("英文主題：", result.topic_en)
    print("中文理解：", result.topic_summary_zh)
    print("核心關鍵字：", result.keywords)
    print("同義詞：", result.synonyms)
    print("相關概念：", result.related_concepts)
    print("搜尋詞：")
    for q in result.search_queries:
        print("  -", q)
except GeminiError as e:
    raise SystemExit(f"錯誤：{e}")

print("\n=== 測試 2：用第一組搜尋詞去 OpenAlex 搜尋（串接 Phase 2）===")
try:
    df, stats = search_papers(result.search_queries[0], year_from=2022, max_results=10)
    print("搜尋詞：", result.search_queries[0])
    print("統計：", stats)
    print(df[["year", "title"]].head(5))
except OpenAlexError as e:
    print("錯誤：", e)

print("\n=== 測試 3：空輸入（測試錯誤處理）===")
try:
    expand_keywords("   ")
except GeminiError as e:
    print("預期中的錯誤訊息：", e)