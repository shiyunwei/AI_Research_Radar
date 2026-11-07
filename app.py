# app.py  — AI Research Radar 網站主程式（Phase 7b）
from datetime import datetime
import streamlit as st

from config import get_missing_keys
from services.gemini_service import (
    expand_keywords, classify_papers, interpret_trends,
    explore_research_directions, GeminiError,
)
from services.openalex_service import search_multi, fetch_year_counts, OpenAlexError
from utils.data_processor import (
    yearly_counts, category_distribution, category_by_year,
    build_trend_facts, make_fact_statements, recommend_reading,
)
from utils.report import build_markdown_report
from utils.visualization import yearly_bar, category_bar, category_year_chart

st.set_page_config(page_title="AI Research Radar", page_icon="📡", layout="wide")

EXAMPLES = [
    "生成式 AI 對大學生學習的影響",
    "社群媒體使用與青少年心理健康",
    "遠距工作對員工生產力的影響",
    "電動車普及對都市交通的影響",
]
NOW_YEAR = datetime.now().year
ANALYSIS_STEPS = ("categories", "facts", "interp", "explore")

# ---------- 狀態 ----------
for key, default in {"stage": "home", "topic": "", "kw": None, "df": None, "stats": None,
                     "topic_input": "", "analysis": {}, "queries": [],
                     "year_from": 2020, "year_to": NOW_YEAR}.items():
    st.session_state.setdefault(key, default)


# ---------- 快取（相同輸入不重複呼叫 API）----------
@st.cache_data(ttl=86400, show_spinner=False)
def cached_keywords(topic):
    return expand_keywords(topic)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(queries, year_from, year_to, max_results):
    return search_multi(list(queries), year_from, year_to, max_results)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_year_counts(query, year_from, year_to):
    return fetch_year_counts(query, year_from, year_to)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_classify(df, topic):
    return classify_papers(df, topic)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_trends(facts, categories, topic):
    return interpret_trends(facts, categories, topic)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_explore(df, categories, topic):
    return explore_research_directions(df, categories, topic)


# ---------- 導覽與小工具 ----------
def set_example(text):
    st.session_state["topic_input"] = text


def nav(stage):
    """給按鈕的 on_click 使用：先切換頁面，再重新執行程式。"""
    st.session_state.stage = stage


def go(stage):
    st.session_state.stage = stage
    st.rerun()


def reset_analysis():
    st.session_state.analysis = {}
    cached_classify.clear()
    cached_trends.clear()
    cached_explore.clear()


def bullets(items):
    return "\n".join(f"- {x}" for x in items)


def show_flags(flags):
    for f in flags or []:
        st.caption(f"⚠ {f}")


def render_refs(ids, index, label="對應論文"):
    """顯示對應論文清單（可展開），每篇附 OpenAlex 原始連結。"""
    if not ids:
        st.caption("沒有有效對應的論文")
        return
    with st.expander(f"{label}（{len(ids)} 篇）"):
        for oid in ids:
            row = index.get(oid)
            if row is None:
                continue
            title = str(row["title"]).replace("[", "(").replace("]", ")")
            note = "" if row["has_abstract"] else "（無摘要，僅依標題判斷）"
            st.markdown(f"- ({row['year']}) [{title}]({row['openalex_url']}){note}")


def render_paper_table(df, with_category=False):
    cols = ["year", "title", "authors", "cited_by_count", "has_abstract", "is_oa", "openalex_url", "doi"]
    names = {"year": "年份", "title": "標題", "authors": "作者", "cited_by_count": "引用次數",
             "has_abstract": "有摘要", "is_oa": "開放取用", "openalex_url": "OpenAlex", "doi": "DOI"}
    if with_category and "category" in df.columns:
        cols.insert(1, "category")
        names["category"] = "分類"
    st.dataframe(
        df[cols].rename(columns=names), hide_index=True,
        column_config={
            "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="開啟"),
            "DOI": st.column_config.LinkColumn("DOI", display_text="開啟"),
        },
    )


# ---------- 首頁 ----------
def render_home():
    st.title("📡 AI Research Radar")
    st.caption("Academic Research Exploration & Intelligence Platform")
    st.write("輸入你感興趣的研究主題，系統會從 OpenAlex 搜尋真實的學術論文，"
             "協助你整理研究主題、了解趨勢，並探索值得進一步研究的問題。")

    st.text_input("研究主題", key="topic_input", max_chars=200,
                  placeholder="例如：生成式 AI 對大學生學習的影響")

    st.write("或試試這些範例：")
    cols = st.columns(len(EXAMPLES))
    for col, text in zip(cols, EXAMPLES):
        col.button(text, on_click=set_example, args=(text,), key=f"ex_{text}")

    if st.button("開始探索", type="primary"):
        topic = st.session_state.topic_input.strip()
        if not topic:
            st.warning("請先輸入研究主題。")
            return
        try:
            with st.spinner("AI 正在理解主題並擴展關鍵字…"):
                kw = cached_keywords(topic)
        except GeminiError as e:
            st.error(str(e))
            return
        st.session_state.update(topic=topic, kw=kw, df=None, stats=None, analysis={})
        st.session_state.pop("queries_text", None)  # 換主題時重設搜尋詞輸入框
        go("keywords")

    st.divider()
    st.subheader("使用流程")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**① 輸入主題**\n\nAI 轉成英文學術關鍵字，你可以調整")
    c2.markdown("**② 搜尋文獻**\n\n從 OpenAlex 取得真實論文並附原始連結")
    c3.markdown("**③ 探索方向**\n\n分類、趨勢與研究問題，每項都能追溯到論文")


# ---------- ① 關鍵字確認 ----------
def render_keywords():
    kw = st.session_state.kw
    st.title("① 確認搜尋關鍵字")
    st.write(f"**研究主題**：{st.session_state.topic}")
    st.write(f"**英文表達**：{kw.topic_en}")
    st.write(f"**AI 的理解**：{kw.topic_summary_zh}")

    c1, c2, c3 = st.columns(3)
    c1.markdown("**核心關鍵字**\n\n" + bullets(kw.keywords))
    c2.markdown("**同義詞**\n\n" + bullets(kw.synonyms))
    c3.markdown("**相關概念**\n\n" + bullets(kw.related_concepts))

    st.divider()
    st.text_area("搜尋詞（每行一組，最多使用前 5 組，可自行修改）",
                 value="\n".join(kw.search_queries), height=150, key="queries_text")
    year_from, year_to = st.slider("出版年份範圍", 2000, NOW_YEAR, (2020, NOW_YEAR))
    max_results = st.selectbox("論文數量上限", [30, 40, 60], index=1,
                               help="AI 分析最多一次處理 60 篇，數量越多等待越久。")

    b1, b2 = st.columns([1, 5])
    if b1.button("← 返回"):
        go("home")
    if b2.button("搜尋文獻", type="primary"):
        queries = tuple(q.strip() for q in st.session_state.queries_text.splitlines() if q.strip())[:5]
        if not queries:
            st.warning("請至少保留一組搜尋詞。")
            return
        try:
            with st.spinner("正在從 OpenAlex 搜尋論文…"):
                df, stats = cached_search(queries, year_from, year_to, max_results)
        except OpenAlexError as e:
            st.error(str(e))
            return
        if df.empty:
            st.warning("沒有找到符合條件的論文，請放寬年份範圍或修改搜尋詞。")
            return
        st.session_state.update(df=df, stats=stats, analysis={}, queries=list(queries),
                                year_from=year_from, year_to=year_to)
        go("results")


# ---------- ② 搜尋結果 ----------
def render_results():
    df, stats = st.session_state.df, st.session_state.stats
    st.title("② 搜尋到的學術論文")
    st.write(f"**研究主題**：{st.session_state.topic}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("論文數", stats["final_count"])
    m2.metric("有摘要", stats["with_abstract"])
    m3.metric("無摘要", stats["without_abstract"])
    m4.metric("移除重複", stats["duplicates_removed"])

    hits = "；".join(f"「{q}」{n:,} 篇" for q, n in stats["per_query_total"].items())
    st.info("這裡只列出依相關度取得的部分論文，不代表整個領域的全部文獻。"
            f"各搜尋詞在 OpenAlex 中符合的論文數：{hits}。")
    if stats["without_abstract"]:
        st.caption("沒有摘要的論文，後續 AI 分析只會依標題判斷，不會假裝讀過內容。")

    render_paper_table(df)

    b1, b2, b3 = st.columns([1, 1, 4])
    if b1.button("← 修改搜尋"):
        go("keywords")
    if b2.button("重新開始"):
        go("home")
    if len(df) < 5:
        b3.caption("論文數量少於 5 篇，無法進行 AI 分析，請放寬年份範圍或修改搜尋詞。")
    elif b3.button("開始 AI 分析", type="primary"):
        go("analysis")


# ---------- ③ AI 分析 ----------
def run_analysis():
    """依序執行分析步驟；已完成的步驟會跳過，所以失敗後重試不會從頭來過。"""
    a = st.session_state.analysis
    topic, df = st.session_state.topic, st.session_state.df
    with st.status("AI 分析進行中，請稍候…", expanded=True) as status:
        try:
            if "categories" not in a:
                st.write("① 正在歸納研究主題分類…")
                df_cat, categories, cls_stats = cached_classify(df, topic)
                a.update(df=df_cat, categories=categories, cls_stats=cls_stats)
            if "facts" not in a:
                st.write("② 正在統計年度趨勢…")
                full_counts = None
                try:
                    full_counts = cached_year_counts(
                        st.session_state.queries[0], st.session_state.year_from, st.session_state.year_to)
                except OpenAlexError:
                    pass  # 取不到資料庫整體統計時，只顯示樣本統計
                a["full_counts"] = full_counts
                a["facts"] = build_trend_facts(a["df"], full_counts)
            if "interp" not in a:
                st.write("③ 正在解讀研究趨勢…")
                a["interp"] = cached_trends(a["facts"], a["categories"], topic)
            if "explore" not in a:
                st.write("④ 正在探索研究問題與方向…")
                a["explore"], a["explore_stats"] = cached_explore(a["df"], a["categories"], topic)
        except (GeminiError, OpenAlexError) as e:
            status.update(label="分析中斷", state="error")
            st.error(f"{e}\n\n已完成的步驟會保留，按下方「重試」會從中斷處繼續。")
            return False
        status.update(label="分析完成", state="complete", expanded=False)
    return True


def render_categories_tab(a, index):
    st.caption("分類由 AI 依據論文標題與摘要歸納，每篇論文只歸入一個分類。"
               "同樣的資料重新分析，分類名稱與歸屬可能略有不同。")
    for c in a["categories"]:
        with st.container(border=True):
            st.subheader(c["name"])
            st.caption(f"{c['n_papers']} 篇論文（其中 {c['n_title_only']} 篇僅依標題判斷）")
            st.write(c["description"])
            if c["research_questions"]:
                st.markdown("**此分類主要探討的研究問題（AI 整理）**\n\n" + bullets(c["research_questions"]))
            render_refs(c["paper_ids"], index)


def render_trend_tab(a):
    facts = a["facts"]
    cy = facts["current_year"]
    st.info(
        "統計數字全部由程式依 OpenAlex 實際資料計算，AI 只負責解讀。"
        f"樣本圖只涵蓋本次分析的 {facts['sample_size']} 篇論文（依相關度取得，不是隨機樣本）；"
        "資料庫圖是 OpenAlex 中符合搜尋詞的論文年度數量，仍受搜尋詞與資料庫收錄範圍影響，"
        f"不等於整個領域的完整發表量。{cy} 年尚未結束，圖中以 * 標示。")

    c1, c2 = st.columns(2)
    fig1 = yearly_bar(yearly_counts(a["df"]), "樣本年度論文數", cy)
    if fig1 is not None:
        c1.plotly_chart(fig1, key="chart_sample")
    fig2 = yearly_bar(a["full_counts"], "資料庫年度論文數", cy)
    if fig2 is not None:
        c2.plotly_chart(fig2, key="chart_full")
        c2.caption(f"依第一組搜尋詞「{st.session_state.queries[0]}」統計")
    else:
        c2.caption("這次無法取得資料庫整體年度統計。")

    c3, c4 = st.columns(2)
    fig3 = category_bar(category_distribution(a["df"]))
    if fig3 is not None:
        c3.plotly_chart(fig3, key="chart_cat")
    fig4 = category_year_chart(category_by_year(a["df"]), cy)
    if fig4 is not None:
        c4.plotly_chart(fig4, key="chart_cat_year")
    else:
        c4.caption("樣本涵蓋的年份少於兩年，無法呈現各分類的年度變化。")

    st.subheader("數據事實（由程式計算）")
    for s in make_fact_statements(facts):
        st.markdown(f"- {s}")

    st.subheader("AI 推論（不是數據事實）")
    st.caption("以下是 AI 根據上方統計數字所做的推測，僅供參考，請勿當作確定的結論。")
    for item in a["interp"]["inferences"]:
        st.markdown(f"- {item['text']}")
        if item["unverified_numbers"]:
            st.caption("⚠ 這則推論提到的數字（" + "、".join(item["unverified_numbers"])
                       + "）不在程式提供的統計中，請勿直接採信。")

    st.subheader("分析限制")
    for lim in a["interp"]["limitations"]:
        st.markdown(f"- {lim}")


def render_item(item, index):
    with st.container(border=True):
        st.write(item["text"])
        show_flags(item["flags"])
        render_refs(item["paper_ids"], index)


def render_direction(d, index):
    with st.container(border=True):
        st.markdown(f"#### {d['name']}")
        st.caption("適合大學生一學期內完成" if d["undergrad_suitable"] else "較難在一學期內完成")
        st.write(d["description"])
        if d["research_questions"]:
            st.markdown("**可能的研究問題**\n\n" + bullets(d["research_questions"]))
        if d["methods"]:
            st.markdown("**研究方法建議**：" + "、".join(d["methods"]))
        st.markdown("**可行性與限制**：" + d["feasibility"])
        show_flags(d["flags"])
        render_refs(d["paper_ids"], index, "相關論文")


def render_directions_tab(a, index):
    ex = a["explore"]
    st.info("以下內容由 AI 根據這批論文的標題與摘要整理。A 與 B 是對文獻的整理與推論，"
            "C 是 AI 提出的研究構想，不是已發表的研究成果。請點開對應論文自行查證。")

    st.subheader("A. 文獻已支持的發現")
    st.caption("AI 對論文內容的整理，措辭可能比原文肯定，請以論文原文為準。")
    for it in ex["supported"]:
        render_item(it, index)
    if not ex["supported"]:
        st.caption("這次沒有產生可對應論文的發現。")

    st.subheader("B. 根據文獻整理出的合理推論")
    st.caption("綜合多篇論文後的推測，不是論文直接寫出的結論。")
    for it in ex["inferences"]:
        render_item(it, index)

    st.subheader("尚待釐清的問題")
    st.caption("「在這批論文中較少看到」不等於學術界沒有人研究，請另行檢索確認。")
    for it in ex["open_questions"]:
        render_item(it, index)

    st.subheader("C. AI 提出的待驗證研究構想")
    for d in ex["directions"]:
        render_direction(d, index)


def render_sources_tab(a):
    st.caption("以下是本次分析使用的全部論文，每篇都可以開啟 OpenAlex 或 DOI 連結查證。")
    render_paper_table(a["df"], with_category=True)
    with st.expander("AI 輸出驗證紀錄"):
        c, e = a["cls_stats"], a["explore_stats"]
        st.markdown(
            f"- 分類：送出 {c['papers_sent']} 篇，丟棄不存在的論文代號 {c['invalid_ids_dropped']} 個，"
            f"重複歸類 {c['duplicate_assignments_dropped']} 個，未分類 {c['unassigned']} 篇。\n"
            f"- 研究方向：丟棄不存在的論文代號 {e['invalid_ids_dropped']} 個，"
            f"「已支持」降級為推論 {e['downgraded_to_inference']} 則。")

def render_reading_tab(reading):
    st.caption("以下由程式依 OpenAlex 的引用次數與出版年份挑選，不經過 AI。"
               "引用次數會隨時間累積，近期論文引用較少不代表品質較低。")
    for title, key in (("高引用論文", "most_cited"), ("近期論文", "latest")):
        st.subheader(title)
        for p in reading[key]:
            t = str(p["title"]).replace("[", "(").replace("]", ")")
            line = f"- ({p['year']}) [{t}]({p['openalex_url']})，引用 {p['cited_by_count']} 次"
            if p["is_oa"] and isinstance(p["oa_url"], str):
                line += f"，[開放取用全文]({p['oa_url']})"
            st.markdown(line)

def render_analysis():
    st.title("③ AI 研究分析")
    st.write(f"**研究主題**：{st.session_state.topic}")

    a = st.session_state.analysis
    if not all(k in a for k in ANALYSIS_STEPS):
        ok = run_analysis()
        if not ok:
            b1, b2 = st.columns([1, 5])
            b1.button("← 回到搜尋結果", on_click=nav, args=("results",))
            b2.button("重試", type="primary")  # 點擊後頁面重新執行，會從中斷處繼續
            return
        st.rerun()

    index = a["df"].set_index("openalex_id")[["year", "title", "openalex_url", "has_abstract"]].to_dict("index")
    reading = recommend_reading(a["df"])
    report = build_markdown_report(
        st.session_state.topic, st.session_state.kw, st.session_state.queries,
        st.session_state.year_from, st.session_state.year_to,
        st.session_state.stats, a, reading)

    b1, b2, b3, b4 = st.columns([1, 1, 1, 3])
    b1.button("← 回到搜尋結果", on_click=nav, args=("results",))
    b2.button("重新分析", on_click=reset_analysis, help="重新呼叫 AI，分類與內容可能略有不同")
    b3.button("重新開始", on_click=nav, args=("home",))
    b4.download_button("下載 Markdown 報告", data=report,
                       file_name=f"research_radar_{datetime.now():%Y%m%d_%H%M}.md",
                       mime="text/markdown")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["研究主題分類", "研究趨勢", "研究問題與方向", "推薦延伸閱讀", "論文清單"])
    with tab1:
        render_categories_tab(a, index)
    with tab2:
        render_trend_tab(a)
    with tab3:
        render_directions_tab(a, index)
    with tab4:
        render_reading_tab(reading)
    with tab5:
        render_sources_tab(a)

    st.divider()
    st.caption("本頁的分類、推論與研究構想由生成式 AI 產生，可能有誤；論文資料來自 OpenAlex。"
               "請點開對應論文自行查證，再引用或據以決定研究方向。")


# ---------- 主流程 ----------
missing = get_missing_keys()
if missing:
    st.error("缺少設定：" + "、".join(missing) + "。請檢查 .env 檔案。")
    st.stop()

stage = st.session_state.stage
if stage == "keywords" and st.session_state.kw is not None:
    render_keywords()
elif stage == "results" and st.session_state.df is not None:
    render_results()
elif stage == "analysis" and st.session_state.df is not None:
    render_analysis()
else:
    render_home()