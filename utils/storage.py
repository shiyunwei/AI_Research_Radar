# utils/storage.py
# 負責管理本機歷史搜尋紀錄與個人收藏庫（以 JSON 檔案儲存於 data/ 目錄）
import json
import os
import math
from datetime import datetime, date
from pathlib import Path
import numpy as np
import pandas as pd
from services.gemini_service import KeywordResult

DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "history.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _to_json_serializable(obj):
    """遞迴將物件轉換為可被標準 json.dump 處理的 Python 原生格式。
    全面支援：np.integer, np.floating, np.bool_, np.ndarray, pd.DataFrame, pd.Series, Timestamp, Pydantic 等。
    """
    if obj is None:
        return None
    elif isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    elif isinstance(obj, (float, np.floating)):
        return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
    elif isinstance(obj, np.ndarray):
        return [_to_json_serializable(v) for v in obj.tolist()]
    elif isinstance(obj, pd.DataFrame):
        return {"__pd_df__": True, "records": json.loads(obj.to_json(orient="records"))}
    elif isinstance(obj, pd.Series):
        return _to_json_serializable(obj.to_dict())
    elif isinstance(obj, (datetime, date, pd.Timestamp)):
        return str(obj)
    elif hasattr(obj, "model_dump"):
        return _to_json_serializable(obj.model_dump())
    elif isinstance(obj, dict):
        return {str(k): _to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_to_json_serializable(v) for v in obj]
    return str(obj) if not isinstance(obj, str) else obj


def _from_json_serializable(obj):
    """遞迴還原 JSON 中的特殊物件（如 DataFrame）。"""
    if isinstance(obj, dict):
        if obj.get("__pd_df__") is True and "records" in obj:
            return pd.DataFrame(obj["records"])
        return {k: _from_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_from_json_serializable(v) for v in obj]
    return obj


def _read_json(file_path, default):
    _ensure_data_dir()
    if not file_path.exists():
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return _from_json_serializable(data)
    except Exception:
        return default


def _write_json(file_path, data):
    _ensure_data_dir()
    temp_path = file_path.with_suffix(".tmp")
    serialized = _to_json_serializable(data)
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=2)
    # 原子替換，避免檔案寫入中斷損毀
    temp_path.replace(file_path)


# ===================== 歷史搜尋紀錄 =====================

def save_history(topic, kw, queries, year_from, year_to, stats, df, analysis):
    """將一次完整的 AI 分析成果儲存至歷史紀錄中。"""
    # 僅儲存已完成 AI 分析的成果
    if not analysis:
        return None

    history = _read_json(HISTORY_FILE, [])

    # 確保 kw 轉為字典
    kw_data = kw.model_dump() if hasattr(kw, "model_dump") else (kw if isinstance(kw, dict) else {})

    # 若主題已存在，保留原有的 item_id，避免前端 selectbox 的 key 脫靶
    existing = next((h for h in history if h.get("topic") == topic), None)
    item_id = existing.get("id") if existing else datetime.now().strftime("%Y%m%d_%H%M%S")

    # 僅記錄日期 YYYY-MM-DD
    item = {
        "id": item_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "kw": kw_data,
        "queries": list(queries or []),
        "year_from": year_from,
        "year_to": year_to,
        "stats": stats or {},
        "df": df,
        "analysis": analysis or {},
    }

    # 若主題已存在，先移除舊的同主題紀錄（保持最新）
    history = [h for h in history if h.get("topic") != topic]
    history.insert(0, item)

    # 最多保留 30 筆最新歷史
    _write_json(HISTORY_FILE, history[:30])
    return item_id


def load_history_list():
    """取得歷史紀錄簡要列表（用於下拉選單）。格式：[YYYY-MM-DD] 主題 (N 篇)"""
    history = _read_json(HISTORY_FILE, [])
    items = []
    for h in history:
        # 只顯示已有分析成果的紀錄
        if not h.get("analysis"):
            continue
        raw_df = h.get("df")
        count = len(raw_df) if raw_df is not None else 0
        date_str = str(h.get("date", "")).split()[0]  # 確保只保留 YYYY-MM-DD
        items.append({
            "id": h.get("id"),
            "date": date_str,
            "topic": h.get("topic"),
            "paper_count": count,
            "label": f"[{date_str}] {h.get('topic')} ({count} 篇)"
        })
    return items


def get_history_item(item_id):
    """根據 ID 完整載入歷史專案資料，還原為原本的資料格式。"""
    history = _read_json(HISTORY_FILE, [])
    for h in history:
        if h.get("id") == item_id:
            df = h.get("df")
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df or [])

            kw = None
            if h.get("kw"):
                try:
                    kw = KeywordResult.model_validate(h.get("kw"))
                except Exception:
                    kw = None

            analysis = dict(h.get("analysis", {}))
            if "df" in analysis and not isinstance(analysis["df"], pd.DataFrame):
                analysis["df"] = pd.DataFrame(analysis["df"] or [])
            if "full_counts" in analysis and not isinstance(analysis["full_counts"], pd.DataFrame) and analysis["full_counts"] is not None:
                analysis["full_counts"] = pd.DataFrame(analysis["full_counts"])

            return {
                "topic": h.get("topic", ""),
                "kw": kw,
                "queries": h.get("queries", []),
                "year_from": h.get("year_from", 2020),
                "year_to": h.get("year_to", datetime.now().year),
                "stats": h.get("stats", {}),
                "df": df,
                "analysis": analysis,
            }
    return None


def delete_history_item(item_id):
    """刪除指定的一筆歷史紀錄。"""
    history = _read_json(HISTORY_FILE, [])
    history = [h for h in history if h.get("id") != item_id]
    _write_json(HISTORY_FILE, history)


# ===================== 個人主題與論文收藏庫 =====================

def get_bookmarks():
    """取得全部已收藏的論文與研究方向。"""
    return _read_json(BOOKMARKS_FILE, {"papers": [], "directions": []})


def is_paper_bookmarked(openalex_id):
    """確認某篇論文是否已收藏。"""
    if not openalex_id:
        return False
    b = get_bookmarks()
    return any(p.get("openalex_id") == openalex_id for p in b.get("papers", []))


def toggle_paper_bookmark(paper_dict):
    """切換論文收藏狀態（若無則新增，若有則取消）。回傳切換後的狀態（True=已收藏, False=已取消）。"""
    b = get_bookmarks()
    papers = b.get("papers", [])
    oid = paper_dict.get("openalex_id")
    if not oid:
        return False

    exists = any(p.get("openalex_id") == oid for p in papers)

    if exists:
        papers = [p for p in papers if p.get("openalex_id") != oid]
        status = False
    else:
        papers.insert(0, {
            "openalex_id": oid,
            "title": paper_dict.get("title", ""),
            "authors": paper_dict.get("authors", ""),
            "year": int(paper_dict.get("year", 0)) if paper_dict.get("year") else None,
            "cited_by_count": int(paper_dict.get("cited_by_count", 0)),
            "openalex_url": paper_dict.get("openalex_url", ""),
            "doi": paper_dict.get("doi", ""),
            "is_oa": bool(paper_dict.get("is_oa", False)),
            "oa_url": paper_dict.get("oa_url", ""),
            "category": paper_dict.get("category", ""),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        status = True

    b["papers"] = papers
    _write_json(BOOKMARKS_FILE, b)
    return status


def remove_paper_bookmark(openalex_id):
    """直接移除指定論文的收藏。"""
    b = get_bookmarks()
    b["papers"] = [p for p in b.get("papers", []) if p.get("openalex_id") != openalex_id]
    _write_json(BOOKMARKS_FILE, b)


def is_direction_bookmarked(direction_name):
    """確認某個研究方向是否已收藏。"""
    if not direction_name:
        return False
    b = get_bookmarks()
    return any(d.get("name") == direction_name for d in b.get("directions", []))


def toggle_direction_bookmark(direction_dict, topic="", related_paper_titles=None):
    """切換研究方向收藏狀態。回傳切換後狀態（True=已收藏, False=已取消）。"""
    b = get_bookmarks()
    directions = b.get("directions", [])
    name = direction_dict.get("name")
    if not name:
        return False

    exists = any(d.get("name") == name for d in directions)

    if exists:
        directions = [d for d in directions if d.get("name") != name]
        status = False
    else:
        titles = list(related_paper_titles or direction_dict.get("related_paper_titles", []))
        directions.insert(0, {
            "name": name,
            "topic": topic or direction_dict.get("topic", ""),
            "description": direction_dict.get("description", ""),
            "methods": list(direction_dict.get("methods", [])),
            "research_questions": list(direction_dict.get("research_questions", [])),
            "feasibility": direction_dict.get("feasibility", ""),
            "undergrad_suitable": bool(direction_dict.get("undergrad_suitable", True)),
            "paper_ids": list(direction_dict.get("paper_ids", [])),
            "related_paper_titles": titles,
            "saved_at": datetime.now().strftime("%Y-%m-%d"),
        })
        status = True

    b["directions"] = directions
    _write_json(BOOKMARKS_FILE, b)
    return status


def remove_direction_bookmark(direction_name):
    """直接移除指定研究方向的收藏。"""
    b = get_bookmarks()
    b["directions"] = [d for d in b.get("directions", []) if d.get("name") != direction_name]
    _write_json(BOOKMARKS_FILE, b)


def export_bookmarks_markdown():
    """將收藏庫中的全部論文與方向匯出為 Markdown 格式。"""
    b = get_bookmarks()
    lines = [
        f"# ⭐ 個人學術收藏清單（產出時間：{datetime.now():%Y-%m-%d %H:%M}）",
        "",
        "## 📚 已收藏之學術論文",
        "",
    ]
    if not b.get("papers"):
        lines.append("- （尚未收藏任何論文）")
    else:
        for p in b["papers"]:
            oa = f"，[開放全文]({p['oa_url']})" if p.get("is_oa") and p.get("oa_url") else ""
            doi = f"，[DOI 連結]({p['doi']})" if p.get("doi") else ""
            lines.append(
                f"- ({p.get('year')}) [{p.get('title')}]({p.get('openalex_url')}) —— 作者：{p.get('authors', '未知')}，被引：{p.get('cited_by_count', 0)} 次{oa}{doi}（收藏於 {p.get('saved_at', '')}）"
            )

    lines.extend([
        "",
        "## 🎯 已收藏之研究構想與方向",
        "",
    ])
    if not b.get("directions"):
        lines.append("- （尚未收藏任何研究方向）")
    else:
        for d in b.get("directions", []):
            methods = "、".join(d.get("methods", [])) or "未指定"
            lines.extend([
                f"### {d.get('name')}",
                f"- **來源研究主題**：{d.get('topic', '未記錄')}",
                f"- **方向說明**：{d.get('description', '')}",
                f"- **建議研究方法**：{methods}",
                f"- **可行性與限制**：{d.get('feasibility', '')}",
                f"- **收藏時間**：{d.get('saved_at', '')}",
                "",
            ])

    return "\n".join(lines)
