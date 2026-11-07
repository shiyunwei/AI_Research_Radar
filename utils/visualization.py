# utils/visualization.py
# 負責畫 Plotly 圖表（只做畫圖，不做統計）
import plotly.express as px

BLUE = "#5B7FA6"
PALETTE = ["#5B7FA6", "#8FB3C9", "#A9B8D6", "#7FA99B", "#C7B29A", "#B5A3C4", "#C9CED6"]


def _style(fig, title):
    fig.update_layout(
        title=title, template="plotly_white", font=dict(size=14),
        margin=dict(l=20, r=20, t=60, b=20), legend_title_text="",
    )
    return fig


def _year_labels(years, current_year):
    """進行中的年份加上 * 標記。"""
    return [f"{y}*" if y == current_year else str(y) for y in years]


def yearly_bar(counts_df, title, current_year=None):
    if counts_df is None or counts_df.empty:
        return None
    d = counts_df.copy()
    d["年份"] = _year_labels(d["year"], current_year)
    fig = px.bar(d, x="年份", y="count", labels={"count": "論文數"}, color_discrete_sequence=[BLUE])
    return _style(fig, title)


def category_bar(dist_df, title="各研究分類的論文數"):
    if dist_df is None or dist_df.empty:
        return None
    d = dist_df.sort_values("count")
    fig = px.bar(d, x="count", y="category", orientation="h",
                 labels={"count": "論文數", "category": ""}, color_discrete_sequence=[BLUE])
    return _style(fig, title)


def category_year_chart(cby_df, current_year=None, title="各研究分類的年度變化"):
    if cby_df is None or cby_df.empty or cby_df["year"].nunique() < 2:
        return None  # 年份少於 2 年時，趨勢圖沒有意義
    d = cby_df.copy().sort_values("year")

    # 從最早到最晚的每一年都列出（沒有論文的年份也保留，橫軸才不會被壓縮）
    all_years = list(range(int(d["year"].min()), int(d["year"].max()) + 1))
    year_order = _year_labels(all_years, current_year)

    d["年份"] = _year_labels(d["year"], current_year)
    fig = px.bar(d, x="年份", y="count", color="category", barmode="stack",
                 labels={"count": "論文數"}, color_discrete_sequence=PALETTE,
                 category_orders={"年份": year_order})  # 明確指定橫軸順序
    return _style(fig, title)