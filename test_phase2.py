# test_phase2.py  （暫時的測試檔）
import pandas as pd
from services.openalex_service import search_papers, OpenAlexError

pd.set_option("display.max_colwidth", 60)
pd.set_option("display.width", 200)

print("=== 測試 1：正常搜尋 ===")
try:
    df, stats = search_papers(
        "generative AI university students learning",
        year_from=2022, year_to=2026, max_results=30,
    )
    print("統計：", stats)
    print(df[["year", "cited_by_count", "has_abstract", "title"]].head(10))
    print("\n第一篇的完整資料：")
    print(df.iloc[0].to_dict())
except OpenAlexError as e:
    print("錯誤：", e)

print("\n=== 測試 2：搜尋不存在的內容（測試空結果）===")
try:
    df, stats = search_papers("zxqvbnm asdfghjkl qwertyuiop", max_results=10)
    print("統計：", stats)
    print("DataFrame 是否為空：", df.empty)
except OpenAlexError as e:
    print("錯誤：", e)