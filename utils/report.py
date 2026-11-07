# utils/report.py
# 把分析結果組成 Markdown 報告（只做文字整理，不呼叫任何 API）
from datetime import datetime
from utils.data_processor import make_fact_statements


def _t(title):
    """清理標題中會破壞 Markdown 連結的字元。"""
    return str(title).replace("[", "(").replace("]", ")").replace("\n", " ").strip()


def _paper_md(row):
    note = "" if row.get("has_abstract") else "（無摘要，僅依標題判斷）"
    return f"[{_t(row['title'])}]({row['openalex_url']}){note}"


def _refs(ids, index, indent):
    lines = []
    for oid in ids or []:
        row = index.get(oid)
        if row is not None:
            lines.append(f"{indent}- ({row['year']}) {_paper_md(row)}")
    return lines or [f"{indent}- （沒有有效對應的論文）"]


def _items(items, index):
    out = []
    for it in items:
        out.append(f"- {it['text']}")
        for fl in it.get("flags", []):
            out.append(f"  - ⚠ {fl}")
        out.append("  - 對應論文：")
        out += _refs(it["paper_ids"], index, "    ")
    return out + [""]


def _year_table(counts, label):
    lines = [f"| 年份 | {label} |", "|---|---|"]
    for y, c in sorted(counts.items()):
        lines.append(f"| {y} | {c} |")
    return lines + [""]


def build_markdown_report(topic, kw, queries, year_from, year_to, stats, a, reading):
    df, ex, facts = a["df"], a["explore"], a["facts"]
    index = df.set_index("openalex_id")[["year", "title", "openalex_url", "has_abstract"]].to_dict("index")
    L = []

    L += [f"# AI Research Radar 研究分析報告", "",
          f"- **研究主題**：{topic}",
          f"- **產生時間**：{datetime.now():%Y-%m-%d %H:%M}",
          "",
          "> 本報告由 AI Research Radar 自動產生。論文資料來自 OpenAlex；統計數字由程式計算；"
          "分類、推論與研究構想由生成式 AI 整理，可能有誤，請點開論文連結自行查證。", ""]

    L += ["## 1. 研究主題與搜尋關鍵字", "",
          f"- **英文表達**：{kw.topic_en}",
          f"- **AI 的理解**：{kw.topic_summary_zh}",
          f"- **核心關鍵字**：{'、'.join(kw.keywords)}",
          f"- **同義詞**：{'、'.join(kw.synonyms)}",
          f"- **相關概念**：{'、'.join(kw.related_concepts)}",
          f"- **實際使用的搜尋詞**：{'；'.join(queries)}",
          f"- **出版年份範圍**：{year_from} 至 {year_to}", ""]

    hits = "；".join(f"「{q}」{n:,} 篇" for q, n in stats["per_query_total"].items())
    L += ["## 2. 搜尋結果概況", "",
          f"- 分析論文數：{stats['final_count']} 篇（有摘要 {stats['with_abstract']} 篇、"
          f"無摘要 {stats['without_abstract']} 篇、移除重複 {stats['duplicates_removed']} 篇）",
          f"- 各搜尋詞在 OpenAlex 中符合的論文數：{hits}",
          "- 注意：本報告只分析依相關度取得的部分論文，不代表整個領域的全部文獻。", ""]

    L += ["## 3. 研究主題分類", "",
          "_分類由 AI 依論文標題與摘要歸納，同樣的資料重新分析，結果可能略有不同。_", ""]
    for c in a["categories"]:
        L += [f"### {c['name']}", "",
              f"{c['n_papers']} 篇（其中 {c['n_title_only']} 篇僅依標題判斷）", "",
              c["description"], ""]
        if c["research_questions"]:
            L += ["**此分類主要探討的研究問題（AI 整理）**", ""]
            L += [f"- {q}" for q in c["research_questions"]] + [""]
        L += ["**對應論文**", ""] + _refs(c["paper_ids"], index, "") + [""]

    L += ["## 4. 研究趨勢", "",
          f"_以下統計數字由程式計算。樣本只涵蓋本次分析的 {facts['sample_size']} 篇論文"
          f"（依相關度取得，非隨機樣本）；{facts['current_year']} 年尚未結束，數量可能不完整。_", "",
          "### 數據事實（由程式計算）", ""]
    L += [f"- {s}" for s in make_fact_statements(facts)] + [""]
    L += ["**樣本年度論文數**", ""] + _year_table(facts["sample_year_counts"], "論文數")
    if facts["full_db_year_counts"]:
        L += ["**OpenAlex 中符合搜尋詞的年度論文數**（依第一組搜尋詞，仍受搜尋詞與資料庫收錄範圍影響）", ""]
        L += _year_table(facts["full_db_year_counts"], "論文數")
    L += ["**各分類論文數**", "", "| 分類 | 論文數 |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in facts["category_counts"].items()] + [""]
    L += ["### AI 推論（不是數據事實）", ""]
    for item in a["interp"]["inferences"]:
        L.append(f"- {item['text']}")
        if item["unverified_numbers"]:
            L.append(f"  - ⚠ 此則提到的數字（{'、'.join(item['unverified_numbers'])}）不在程式提供的統計中，請勿直接採信")
    L += ["", "### 分析限制", ""] + [f"- {x}" for x in a["interp"]["limitations"]] + [""]

    L += ["## 5. 研究問題與潛在研究方向", "",
          "_A、B 是 AI 對文獻的整理與推論，C 是 AI 提出的研究構想，不是已發表的研究成果。_", "",
          "### A. 文獻已支持的發現", ""] + _items(ex["supported"], index)
    L += ["### B. 根據文獻整理出的合理推論", ""] + _items(ex["inferences"], index)
    L += ["### 尚待釐清的問題", "",
          "_「在這批論文中較少看到」不等於學術界沒有人研究，請另行檢索確認。_", ""] + _items(ex["open_questions"], index)
    L += ["### C. AI 提出的待驗證研究構想", ""]
    for d in ex["directions"]:
        L += [f"#### {d['name']}", "",
              "適合大學生一學期內完成" if d["undergrad_suitable"] else "較難在一學期內完成", "",
              d["description"], ""]
        if d["research_questions"]:
            L += ["**可能的研究問題**", ""] + [f"- {q}" for q in d["research_questions"]] + [""]
        if d["methods"]:
            L += [f"**研究方法建議**：{'、'.join(d['methods'])}", ""]
        L += [f"**可行性與限制**：{d['feasibility']}", ""]
        for fl in d["flags"]:
            L.append(f"- ⚠ {fl}")
        L += ["", "**相關論文**", ""] + _refs(d["paper_ids"], index, "") + [""]

    L += ["## 6. 推薦延伸閱讀", "",
          "_由程式依 OpenAlex 的引用次數與出版年份挑選，不經過 AI。引用次數會隨時間累積，"
          "近期論文引用較少不代表品質較低。_", ""]
    for title, key in (("高引用論文", "most_cited"), ("近期論文", "latest")):
        L += [f"### {title}", ""]
        for p in reading[key]:
            line = f"- ({p['year']}) {_paper_md(p)}，引用 {p['cited_by_count']} 次"
            if p["is_oa"] and isinstance(p["oa_url"], str):
                line += f"，[開放取用全文]({p['oa_url']})"
            L.append(line)
        L.append("")

    L += ["## 7. 本次分析的全部論文", ""]
    for r in df.itertuples():
        line = f"- ({r.year}) {_paper_md({'title': r.title, 'openalex_url': r.openalex_url, 'has_abstract': r.has_abstract})}"
        line += f"｜{r.category}｜引用 {r.cited_by_count} 次"
        if isinstance(r.doi, str):
            line += f"｜[DOI]({r.doi})"
        L.append(line)

    L += ["", "## 附錄：資料與方法說明", "",
          "- 論文資料：OpenAlex API，每篇論文都保留 OpenAlex 識別碼與原始連結。",
          "- 去重與統計：由 Python 與 Pandas 完成。",
          "- 關鍵字擴展、分類、趨勢解讀與研究構想：由 Gemini 產生，輸出經程式驗證論文代號是否真實存在。",
          "- 沒有摘要的論文只依標題判斷，AI 無法確認的內容應視為待查證。", ""]
    return "\n".join(L)