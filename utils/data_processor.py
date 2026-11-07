# utils/data_processor.py
# 所有統計數字都在這裡由 Pandas 計算，不交給 AI
from datetime import datetime
import pandas as pd


def yearly_counts(df):
    """樣本中各年份的論文數（中間沒有論文的年份補 0）。"""
    if df is None or df.empty or df["year"].dropna().empty:
        return pd.DataFrame(columns=["year", "count"])
    years = df["year"].dropna().astype(int)
    counts = years.value_counts().reindex(range(years.min(), years.max() + 1), fill_value=0).sort_index()
    return pd.DataFrame({"year": counts.index, "count": counts.values})


def category_distribution(df):
    """各研究分類的論文數。"""
    if df is None or df.empty or "category" not in df.columns:
        return pd.DataFrame(columns=["category", "count"])
    counts = df["category"].dropna().value_counts()
    return pd.DataFrame({"category": counts.index, "count": counts.values})


def category_by_year(df):
    """各分類在各年份的論文數（長表格，方便畫堆疊圖）。"""
    if df is None or df.empty or "category" not in df.columns:
        return pd.DataFrame(columns=["year", "category", "count"])
    d = df.dropna(subset=["year", "category"]).copy()
    d["year"] = d["year"].astype(int)
    return d.groupby(["year", "category"]).size().reset_index(name="count")


def build_trend_facts(df, full_counts=None):
    """把所有統計結果整理成一個字典：給畫面顯示，也給 Gemini 當作唯一的數據來源。"""
    sample = yearly_counts(df)
    cat = category_distribution(df)
    facts = {
        "sample_size": int(len(df)),
        "current_year": datetime.now().year,
        "sample_year_counts": {int(y): int(c) for y, c in zip(sample["year"], sample["count"])},
        "category_counts": {str(k): int(v) for k, v in zip(cat["category"], cat["count"])},
        "category_year_counts": {},
        "full_db_year_counts": None,
    }
    for r in category_by_year(df).itertuples(index=False):
        facts["category_year_counts"].setdefault(r.category, {})[int(r.year)] = int(r[2])
    if full_counts is not None and not full_counts.empty:
        facts["full_db_year_counts"] = {
            int(y): int(c) for y, c in zip(full_counts["year"], full_counts["count"])
        }
    return facts


def make_fact_statements(facts):
    """由 Python 產生的「數據事實」文字，不經過 AI。"""
    statements = []
    n, cy = facts["sample_size"], facts["current_year"]

    sy = facts["sample_year_counts"]
    if sy:
        peak = max(sy, key=sy.get)
        statements.append(f"本次分析的 {n} 篇論文中，出版年份最多的是 {peak} 年（{sy[peak]} 篇）。")
        if cy in sy:
            statements.append(f"{cy} 年尚未結束，該年度的論文數量可能不完整。")

    full = facts["full_db_year_counts"]
    if full:
        peak = max(full, key=full.get)
        statements.append(
            f"在所選年份範圍內，OpenAlex 中符合搜尋詞的論文共 {sum(full.values())} 篇，"
            f"以 {peak} 年最多（{full[peak]} 篇）。"
        )

    cc = facts["category_counts"]
    if cc:
        top = max(cc, key=cc.get)
        statements.append(f"篇數最多的研究分類是「{top}」（{cc[top]} 篇）。")
    return statements

# ===================== Phase 7c：推薦延伸閱讀（追加在檔案最底下）=====================
def recommend_reading(df, n=5):
    """由程式挑選延伸閱讀：高引用論文 + 近期論文（不經過 AI）。
    引用次數會隨時間累積，所以另外列出近期論文，避免只推薦舊文章。"""
    if df is None or df.empty:
        return {"most_cited": [], "latest": []}
    cols = ["openalex_id", "year", "title", "cited_by_count", "openalex_url",
            "doi", "has_abstract", "is_oa", "oa_url"]
    d = df.dropna(subset=["year"])[cols].copy()
    most = d.sort_values("cited_by_count", ascending=False, kind="stable").head(n)
    rest = d[~d["openalex_id"].isin(most["openalex_id"])]  # 近期清單不重複列出高引用論文
    latest = rest.sort_values(["year", "cited_by_count"], ascending=[False, False],
                              kind="stable").head(n)
    return {"most_cited": most.to_dict("records"), "latest": latest.to_dict("records")}