# tests/test_storage.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from utils.storage import (
    save_history, load_history_list, get_history_item, delete_history_item,
    get_bookmarks, is_paper_bookmarked, toggle_paper_bookmark, remove_paper_bookmark,
    is_direction_bookmarked, toggle_direction_bookmark, remove_direction_bookmark,
    export_bookmarks_markdown
)
from services.gemini_service import KeywordResult


def test_storage():
    kw = KeywordResult(
        topic_en="Generative AI in Education",
        topic_summary_zh="生成式 AI 在教育領域的應用",
        keywords=["Generative AI", "Education"],
        synonyms=["LLM in learning"],
        related_concepts=["Prompt Engineering"],
        search_queries=["generative ai higher education"]
    )

    df = pd.DataFrame([{
        "openalex_id": "W99999",
        "title": "A Test Study on Generative AI",
        "year": 2024,
        "cited_by_count": 42,
        "has_abstract": True,
        "is_oa": True,
        "openalex_url": "https://openalex.org/W99999",
        "doi": "https://doi.org/10.1234/test",
        "authors": "Jane Doe",
        "oa_url": "https://oa.org/test.pdf",
        "category": "教學輔助"
    }])

    full_counts = pd.DataFrame([{"year": 2024, "count": 100}])

    analysis = {
        "df": df,
        "full_counts": full_counts,
        "categories": [{"name": "教學輔助", "n_papers": 1, "n_title_only": 0, "description": "說明", "research_questions": [], "paper_ids": ["W99999"]}],
        "facts": {"sample_size": 1, "current_year": 2024},
        "interp": {"inferences": [{"text": "推論", "unverified_numbers": []}], "limitations": []},
        "explore": {
            "supported": [],
            "inferences": [],
            "open_questions": [],
            "directions": [{
                "name": "專題方向一",
                "description": "探索方向一說明",
                "methods": ["問卷調查"],
                "feasibility": "高",
                "undergrad_suitable": True,
                "research_questions": ["Q1"],
                "flags": [],
                "paper_ids": ["W99999"]
            }]
        },
        "explore_stats": {"invalid_ids_dropped": 0, "downgraded_to_inference": 0},
        "cls_stats": {"papers_sent": 1, "invalid_ids_dropped": 0, "duplicate_assignments_dropped": 0, "unassigned": 0}
    }

    # 1. 測試未完成分析不儲存
    assert save_history("尚未分析的主題", kw, ["q"], 2020, 2024, {}, df, analysis={}) is None

    # 2. 測試儲存完整歷史
    item_id = save_history("教育與AI", kw, ["generative ai higher education"], 2020, 2024, {"final_count": 1}, df, analysis)
    assert item_id, "save_history 應回傳 item_id"

    # 3. 測試讀取清單（只包含日期，無精準時間，無已分析標籤）
    h_list = load_history_list()
    assert any(h["id"] == item_id for h in h_list), "歷史清單中應包含剛存入的紀錄"
    curr_item = next(h for h in h_list if h["id"] == item_id)
    assert "【" not in curr_item["label"], "標籤不應包含【已分析】或【已檢索】"
    assert curr_item["label"].startswith(f"[{curr_item['date']}] 教育與AI (1 篇)")

    # 4. 測試還原歷史項目
    item = get_history_item(item_id)
    assert item is not None
    assert isinstance(item["df"], pd.DataFrame)
    assert isinstance(item["analysis"]["df"], pd.DataFrame)
    assert isinstance(item["analysis"]["full_counts"], pd.DataFrame)
    assert item["topic"] == "教育與AI"

    # 4. 測試論文收藏
    p_dict = df.iloc[0].to_dict()
    assert toggle_paper_bookmark(p_dict) is True
    assert is_paper_bookmarked("W99999") is True

    # 5. 測試方向收藏
    d_dict = analysis["explore"]["directions"][0]
    assert toggle_direction_bookmark(d_dict, "教育與AI") is True
    assert is_direction_bookmarked("專題方向一") is True

    # 6. 測試 Markdown 匯出
    md = export_bookmarks_markdown()
    assert "A Test Study on Generative AI" in md
    assert "專題方向一" in md

    # 7. 清理
    delete_history_item(item_id)
    remove_paper_bookmark("W99999")
    remove_direction_bookmark("專題方向一")
    assert is_paper_bookmarked("W99999") is False
    assert is_direction_bookmarked("專題方向一") is False
    print("test_storage passed successfully!")


if __name__ == "__main__":
    test_storage()
