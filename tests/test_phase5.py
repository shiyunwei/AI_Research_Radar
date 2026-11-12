# test_phase5.py  （暫時的測試檔）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.openalex_service import search_papers, fetch_year_counts, OpenAlexError
from services.gemini_service import classify_papers, interpret_trends, GeminiError
from utils.data_processor import (
    yearly_counts, category_distribution, category_by_year,
    build_trend_facts, make_fact_statements,
)
from utils.visualization import yearly_bar, category_bar, category_year_chart

TOPIC = "生成式 AI 對大學生學習的影響"
QUERY = "generative AI university students learning"
YEAR_FROM, YEAR_TO = 2020, 2026

df, s = search_papers(QUERY, year_from=YEAR_FROM, year_to=YEAR_TO, max_results=40)
print(f"取得 {s['final_count']} 篇")

try:
    full_counts = fetch_year_counts(QUERY, YEAR_FROM, YEAR_TO)
    print("\n資料庫年度數量：")
    print(full_counts)
except OpenAlexError as e:
    full_counts = None
    print("取得資料庫年度數量失敗：", e)

df2, categories, _ = classify_papers(df, TOPIC)

print("\n樣本年度數量：")
print(yearly_counts(df2))
print("\n分類分布：")
print(category_distribution(df2))

facts = build_trend_facts(df2, full_counts)
print("\n=== 數據事實（由 Python 產生）===")
for st in make_fact_statements(facts):
    print(" •", st)

print("\n=== AI 推論（Gemini）===")
try:
    interp = interpret_trends(facts, categories, TOPIC)
    for item in interp["inferences"]:
        flag = f"  ⚠ 數據中找不到的數字：{item['unverified_numbers']}" if item["unverified_numbers"] else ""
        print(" •", item["text"], flag)
    print("\n限制：")
    for lim in interp["limitations"]:
        print(" -", lim)
except GeminiError as e:
    print("錯誤：", e)

cy = facts["current_year"]
figs = [
    yearly_bar(yearly_counts(df2), f"樣本年度論文數（{len(df2)} 篇）", cy),
    yearly_bar(full_counts, "資料庫中符合搜尋詞的年度論文數", cy),
    category_bar(category_distribution(df2)),
    category_year_chart(category_by_year(df2), cy),
]
for fig in figs:
    if fig is not None:
        fig.show()  # 會在瀏覽器開新分頁