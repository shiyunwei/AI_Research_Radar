# test_openalex.py  （暫時的測試檔，確認 OpenAlex 能連線）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
from config import OPENALEX_API_KEY, OPENALEX_BASE_URL, get_missing_keys

if "OPENALEX_API_KEY" in get_missing_keys():
    raise SystemExit("找不到 OPENALEX_API_KEY，請檢查 .env")

params = {
    "search": "generative AI university students learning",
    "per_page": 5,
    "api_key": OPENALEX_API_KEY,
}

try:
    response = requests.get(f"{OPENALEX_BASE_URL}/works", params=params, timeout=30)
    response.raise_for_status()
except requests.exceptions.HTTPError:
    raise SystemExit(f"OpenAlex 回傳錯誤，狀態碼：{response.status_code}\n{response.text[:300]}")
except requests.exceptions.RequestException as e:
    raise SystemExit(f"連線失敗：{e}")

data = response.json()
print(f"符合條件的論文總數：{data['meta']['count']}")
print(f"本次呼叫花費（USD）：{data['meta'].get('cost_usd')}")
print("-" * 40)

for work in data["results"]:
    print(work["publication_year"], "|", work["cited_by_count"], "次引用")
    print(work["title"])
    print(work["id"])
    print()