# tests/test_pdf.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd
from utils.storage import get_history_item, load_history_list
from utils.data_processor import recommend_reading
from utils.pdf_generator import build_pdf_report


def test_pdf_generation():
    h_list = load_history_list()
    if not h_list:
        print("No history items to test PDF generator.")
        return

    # 取得第一筆已有分析的歷史專案
    item_id = h_list[0]["id"]
    data = get_history_item(item_id)
    assert data is not None, "Failed to load history item"

    df = data["df"]
    reading = recommend_reading(df)

    pdf_bytes = build_pdf_report(
        topic=data["topic"],
        kw=data["kw"],
        queries=data["queries"],
        year_from=data["year_from"],
        year_to=data["year_to"],
        stats=data["stats"],
        a=data["analysis"],
        reading=reading,
    )

    assert isinstance(pdf_bytes, bytes), "PDF report should be bytes"
    assert len(pdf_bytes) > 1000, f"PDF report size too small: {len(pdf_bytes)}"
    assert pdf_bytes.startswith(b"%PDF"), "PDF byte stream should start with %PDF header"

    out_path = os.path.join("data", "test_report.pdf")
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)

    print(f"PDF generated successfully! Size: {len(pdf_bytes):,} bytes, saved to {out_path}")


if __name__ == "__main__":
    test_pdf_generation()
