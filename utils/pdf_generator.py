# utils/pdf_generator.py
# 負責將研究分析結果編排為專業學術排版之 PDF 報告（支援繁體中文與超連結）
import os
import io
import math
import xml.sax.saxutils as sax
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)

from utils.data_processor import make_fact_statements


# ===================== 中文字型註冊 =====================

def _register_cjk_fonts():
    """尋找本機可用的中文字型並註冊至 ReportLab，回傳 (正規字型名稱, 粗體字型名稱)。"""
    font_candidates = [
        # 微軟正黑體 (Windows 首選)
        ("MSJH", "MSJH-Bold", r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\msjhbd.ttc", 0),
        # 細明體 / 新細明體
        ("MingLiU", "MingLiU-Bold", r"C:\Windows\Fonts\mingliu.ttc", r"C:\Windows\Fonts\mingliu.ttc", 0),
        # 標楷體
        ("KaiU", "KaiU-Bold", r"C:\Windows\Fonts\kaiu.ttf", r"C:\Windows\Fonts\kaiu.ttf", None),
        # Linux / Noto Sans CJK
        ("NotoSansTC", "NotoSansTC-Bold", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ]

    registered = pdfmetrics.getRegisteredFontNames()
    if "CJK_Main" in registered:
        return "CJK_Main", "CJK_Main_Bold"

    for _, _, path, bold_path, sub_idx in font_candidates:
        if os.path.exists(path):
            try:
                if sub_idx is not None:
                    pdfmetrics.registerFont(TTFont("CJK_Main", path, subfontIndex=sub_idx))
                else:
                    pdfmetrics.registerFont(TTFont("CJK_Main", path))

                if os.path.exists(bold_path):
                    if sub_idx is not None:
                        pdfmetrics.registerFont(TTFont("CJK_Main_Bold", bold_path, subfontIndex=sub_idx))
                    else:
                        pdfmetrics.registerFont(TTFont("CJK_Main_Bold", bold_path))
                else:
                    pdfmetrics.registerFont(TTFont("CJK_Main_Bold", path, subfontIndex=sub_idx if sub_idx is not None else 0))

                return "CJK_Main", "CJK_Main_Bold"
            except Exception:
                continue

    # 若系統完全無可用 CJK 字型，退回預設（純英文無亂碼）
    return "Helvetica", "Helvetica-Bold"


# ===================== 雙頁面頁碼 Canvas =====================

class NumberedCanvas(canvas.Canvas):
    """自訂雙傳遞（Two-pass）Canvas，動態計算總頁數並繪製頁首頁尾。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.report_topic = getattr(self, "report_topic", "AI Research Radar")

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(page_count)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        font_name = "CJK_Main" if "CJK_Main" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
        self.setFont(font_name, 8.5)
        self.setFillColor(colors.HexColor("#64748B"))

        # 頁首（從第 2 頁開始）
        if self._pageNumber > 1:
            header_topic = self.report_topic[:40] + ("…" if len(self.report_topic) > 40 else "")
            self.drawString(54, 804, f"AI Research Radar 學術研究分析報告 ｜ {header_topic}")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(54, 796, 541, 796)

        # 頁尾（每頁顯示）
        self.drawString(54, 34, "AI Research Radar ｜ 文獻來源：OpenAlex ｜ 嚴謹度優先學術探索平台")
        page_text = f"第 {self._pageNumber} 頁 / 共 {page_count} 頁"
        self.drawRightString(541, 34, page_text)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(54, 46, 541, 46)

        self.restoreState()


# ===================== PDF 報告生成主邏輯 =====================

def _escape(text):
    """跳脫 XML/HTML 特殊字元避免 ReportLab 解析崩潰。"""
    if text is None:
        return ""
    return sax.escape(str(text).strip())


def _clean_paper_title(title):
    return str(title).replace("[", "(").replace("]", ")").replace("\n", " ").strip()


def build_pdf_report(topic, kw, queries, year_from, year_to, stats, a, reading) -> bytes:
    """將一次完整研究分析結果生成為高品質 PDF 位元組資料。"""
    cjk_font, cjk_bold = _register_cjk_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    # 色彩定義
    NAVY = colors.HexColor("#1E3A8A")
    BLUE = colors.HexColor("#2563EB")
    DARK = colors.HexColor("#1F2937")
    MUTED = colors.HexColor("#4B5563")
    LIGHT_BG = colors.HexColor("#F8FAFC")
    BORDER_CLR = colors.HexColor("#E2E8F0")

    # 樣式定義
    base_sheet = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=base_sheet["Normal"],
        fontName=cjk_bold,
        fontSize=20,
        leading=26,
        textColor=NAVY,
        spaceAfter=4,
        wordWrap="CJK",
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=base_sheet["Normal"],
        fontName=cjk_font,
        fontSize=10,
        leading=14,
        textColor=MUTED,
        spaceAfter=12,
        wordWrap="CJK",
    )
    h1_style = ParagraphStyle(
        "SecH1",
        parent=base_sheet["Normal"],
        fontName=cjk_bold,
        fontSize=13.5,
        leading=18,
        textColor=NAVY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
        wordWrap="CJK",
    )
    h2_style = ParagraphStyle(
        "SecH2",
        parent=base_sheet["Normal"],
        fontName=cjk_bold,
        fontSize=11,
        leading=15,
        textColor=BLUE,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
        wordWrap="CJK",
    )
    h3_style = ParagraphStyle(
        "SecH3",
        parent=base_sheet["Normal"],
        fontName=cjk_bold,
        fontSize=10,
        leading=14,
        textColor=DARK,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=base_sheet["Normal"],
        fontName=cjk_font,
        fontSize=9,
        leading=13.5,
        textColor=DARK,
        spaceAfter=4,
        wordWrap="CJK",
    )
    bullet_style = ParagraphStyle(
        "DocBullet",
        parent=body_style,
        leftIndent=12,
        spaceAfter=3,
    )
    caption_style = ParagraphStyle(
        "DocCaption",
        parent=base_sheet["Normal"],
        fontName=cjk_font,
        fontSize=8,
        leading=11.5,
        textColor=MUTED,
        spaceAfter=4,
        wordWrap="CJK",
    )
    disclaimer_style = ParagraphStyle(
        "DocDisclaimer",
        parent=base_sheet["Normal"],
        fontName=cjk_font,
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#1E40AF"),
        wordWrap="CJK",
    )

    story = []

    # 1. 頁首大標題與副標
    story.append(Paragraph("AI Research Radar 學術研究分析報告", title_style))
    story.append(Paragraph("Academic Exploration & Research Trend Intelligence", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=10))

    # 2. 元數據摘要表
    meta_data = [
        [
            Paragraph(f"<b>研究主題：</b>{_escape(topic)}", body_style),
            Paragraph(f"<b>產生日期：</b>{datetime.now():%Y-%m-%d}", body_style)
        ],
        [
            Paragraph(f"<b>出版年份範圍：</b>{year_from} 至 {year_to} 年", body_style),
            Paragraph(f"<b>分析論文篇數：</b>{stats.get('final_count', 0)} 篇", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[280, 207])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_CLR),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # 3. 免責與文獻查證框
    disclaimer_p = Paragraph(
        "<b>【使用須知】</b> 本報告由 AI Research Radar 自動產生。文獻資料來自 OpenAlex 學術資料庫；"
        "統計數據全部由程式計算；主題分類、趨勢推論與專題方向由生成式 AI 整理，可能存在推論侷限。"
        "報告中每篇論文皆附原始 OpenAlex / DOI 連結，請於引用或確立題目時自行查證原文。",
        disclaimer_style
    )
    disclaimer_table = Table([[disclaimer_p]], colWidths=[487])
    disclaimer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#BFDBFE")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(disclaimer_table)
    story.append(Spacer(1, 10))

    # 建立論文快取索引 (oid -> row dict)
    df = a["df"]
    index = df.set_index("openalex_id")[["year", "title", "openalex_url", "has_abstract", "doi", "cited_by_count"]].to_dict("index")

    # 4. 第一章：研究主題與關鍵字
    story.append(Paragraph("1. 研究主題與搜尋關鍵字", h1_style))
    story.append(Paragraph(f"• <b>英文學術表達</b>：{_escape(kw.topic_en)}", bullet_style))
    story.append(Paragraph(f"• <b>AI 概念理解</b>：{_escape(kw.topic_summary_zh)}", bullet_style))
    story.append(Paragraph(f"• <b>核心關鍵字</b>：{_escape('、'.join(kw.keywords))}", bullet_style))
    story.append(Paragraph(f"• <b>同義詞組</b>：{_escape('、'.join(kw.synonyms))}", bullet_style))
    story.append(Paragraph(f"• <b>相關概念</b>：{_escape('、'.join(kw.related_concepts))}", bullet_style))
    story.append(Paragraph(f"• <b>實際搜尋詞</b>：{_escape(' ； '.join(queries))}", bullet_style))

    # 5. 第二章：文獻搜尋概況
    story.append(Paragraph("2. 搜尋結果概況", h1_style))
    hits_str = " ； ".join(f"「{q}」{n:,} 篇" for q, n in stats.get("per_query_total", {}).items())
    story.append(Paragraph(
        f"本次檢索分析論文共 <b>{stats.get('final_count', 0)}</b> 篇（含摘要 {stats.get('with_abstract', 0)} 篇、"
        f"無摘要 {stats.get('without_abstract', 0)} 篇、去重移除 {stats.get('duplicates_removed', 0)} 篇）。",
        body_style
    ))
    if hits_str:
        story.append(Paragraph(f"各檢索詞在 OpenAlex 資料庫中之全域符合數量：{_escape(hits_str)}。", caption_style))

    # 6. 第三章：研究主題分類
    story.append(Paragraph("3. 研究主題分類", h1_style))
    story.append(Paragraph("分類由 AI 依據論文標題與摘要歸納整理，每篇論文歸入最相關的一個分類。", caption_style))

    for c in a.get("categories", []):
        cat_elements = []
        cat_title = f"{_escape(c['name'])}（{c['n_papers']} 篇，其中 {c['n_title_only']} 篇僅依標題判斷）"
        cat_elements.append(Paragraph(cat_title, h2_style))
        cat_elements.append(Paragraph(_escape(c.get("description", "")), body_style))

        if c.get("research_questions"):
            cat_elements.append(Paragraph("<b>探討之核心問題：</b>", h3_style))
            for q in c["research_questions"]:
                cat_elements.append(Paragraph(f"• {_escape(q)}", bullet_style))

        # 對應代表論文
        ref_pids = c.get("paper_ids", [])[:5]  # 取前 5 篇作為代表
        if ref_pids:
            cat_elements.append(Paragraph("<b>代表性論文：</b>", h3_style))
            for pid in ref_pids:
                row = index.get(pid)
                if row:
                    t = _escape(_clean_paper_title(row["title"]))
                    url = row.get("openalex_url", "")
                    cat_elements.append(Paragraph(
                        f"• ({row['year']}) <a href=\"{url}\" color=\"#2563EB\"><u>{t}</u></a>",
                        bullet_style
                    ))

        cat_elements.append(Spacer(1, 4))
        story.append(KeepTogether(cat_elements))

    # 7. 第四章：研究趨勢與數據事實
    story.append(Paragraph("4. 研究趨勢與數據事實", h1_style))
    facts = a["facts"]
    story.append(Paragraph("<b>由程式統計之數據事實：</b>", h2_style))
    for s in make_fact_statements(facts):
        story.append(Paragraph(f"• {_escape(s)}", bullet_style))

    # 年度趨勢與分類分佈表格（並排或表格呈現）
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>樣本發表年份分佈：</b>", h3_style))

    y_rows = [["年份", "論文數"]]
    for y, count in sorted(facts.get("sample_year_counts", {}).items()):
        y_rows.append([str(y), str(count)])

    y_table = Table(y_rows, colWidths=[120, 120])
    y_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(y_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>AI 趨勢解讀與推論：</b>", h2_style))
    for item in a.get("interp", {}).get("inferences", []):
        story.append(Paragraph(f"• {_escape(item['text'])}", bullet_style))
        if item.get("unverified_numbers"):
            unv = "、".join(str(n) for n in item["unverified_numbers"])
            story.append(Paragraph(f"  <i>⚠ 註：推論中提及之數字（{unv}）未見於程式提供之統計數據，僅供參考。</i>", caption_style))

    if a.get("interp", {}).get("limitations"):
        story.append(Paragraph("<b>分析限制：</b>", h3_style))
        for lim in a["interp"]["limitations"]:
            story.append(Paragraph(f"• {_escape(lim)}", bullet_style))

    # 8. 第五章：研究問題與潛在專題方向
    story.append(Paragraph("5. 研究問題與潛在專題方向", h1_style))

    ex = a["explore"]
    if ex.get("supported"):
        story.append(Paragraph("A. 文獻已支持之發現", h2_style))
        for it in ex["supported"]:
            story.append(Paragraph(f"• {_escape(it['text'])}", bullet_style))

    if ex.get("inferences"):
        story.append(Paragraph("B. 根據文獻整理之合理推論", h2_style))
        for it in ex["inferences"]:
            story.append(Paragraph(f"• {_escape(it['text'])}", bullet_style))

    if ex.get("open_questions"):
        story.append(Paragraph("尚待釐清之研究問題", h2_style))
        for it in ex["open_questions"]:
            story.append(Paragraph(f"• {_escape(it['text'])}", bullet_style))

    story.append(Paragraph("C. AI 提出之待驗證專題構想", h2_style))
    for d in ex.get("directions", []):
        d_elements = []
        suit_badge = "【適合大學生一學期完成】" if d.get("undergrad_suitable") else "【進階研究構想】"
        d_elements.append(Paragraph(f"{_escape(d['name'])}  <font color=\"#059669\"><b>{suit_badge}</b></font>", h3_style))
        d_elements.append(Paragraph(_escape(d.get("description", "")), body_style))

        if d.get("research_questions"):
            d_elements.append(Paragraph("<b>細化研究問題：</b>", body_style))
            for q in d["research_questions"]:
                d_elements.append(Paragraph(f"• {_escape(q)}", bullet_style))

        if d.get("methods"):
            d_elements.append(Paragraph(f"<b>建議研究方法：</b>{_escape('、'.join(d['methods']))}", body_style))

        if d.get("feasibility"):
            d_elements.append(Paragraph(f"<b>可行性與限制：</b>{_escape(d['feasibility'])}", body_style))

        d_elements.append(Spacer(1, 6))
        story.append(KeepTogether(d_elements))

    # 9. 第六章：推薦延伸閱讀
    story.append(Paragraph("6. 推薦延伸閱讀", h1_style))
    for title, key in (("高被引用文獻", "most_cited"), ("近期代表文獻", "latest")):
        story.append(Paragraph(title, h2_style))
        for p in reading.get(key, []):
            t = _escape(_clean_paper_title(p.get("title", "")))
            oa_str = " [開放取用]" if p.get("is_oa") else ""
            url = p.get("openalex_url", "")
            story.append(Paragraph(
                f"• ({p.get('year')}) <a href=\"{url}\" color=\"#2563EB\"><u>{t}</u></a>"
                f" —— 被引 {p.get('cited_by_count', 0)} 次{oa_str}",
                bullet_style
            ))

    # 10. 第七章：全部論文清單
    story.append(Paragraph("7. 本次分析論文清單", h1_style))
    for r in df.itertuples():
        t = _escape(_clean_paper_title(r.title))
        url = r.openalex_url if hasattr(r, "openalex_url") else ""
        cat = getattr(r, "category", "未分類")
        cites = getattr(r, "cited_by_count", 0)
        story.append(Paragraph(
            f"• ({r.year}) <a href=\"{url}\" color=\"#2563EB\"><u>{t}</u></a>"
            f" ｜ 類別：{_escape(cat)} ｜ 被引：{cites} 次",
            caption_style
        ))

    # 11. 附錄：方法說明
    story.append(Spacer(1, 10))
    story.append(Paragraph("附錄：資料來源與方法說明", h2_style))
    story.append(Paragraph("• 論文檢索來源：OpenAlex REST API，嚴格保留每篇論文之數位唯一識別代號。", caption_style))
    story.append(Paragraph("• 統計與趨勢：由 Python 與 Pandas 計算樣本分佈，數值完全精準。", caption_style))
    story.append(Paragraph("• 主題理解與方向探索：由 Gemini 3.6 Flash 模型依據實體論文內容歸納生成。", caption_style))

    # 綁定 canvas 屬性供頁首動態印出主題
    class BoundNumberedCanvas(NumberedCanvas):
        pass

    BoundNumberedCanvas.report_topic = topic

    doc.build(story, canvasmaker=BoundNumberedCanvas)
    return buffer.getvalue()
