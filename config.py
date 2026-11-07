# config.py
# 集中讀取 .env 的設定，其他檔案只需要 from config import ...
import os
from dotenv import load_dotenv

load_dotenv()  # 從專案根目錄的 .env 讀取環境變數

OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()   # 備用模型，可留空
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "").strip().upper()  # 思考等級，可留空

OPENALEX_BASE_URL = "https://api.openalex.org"


def get_missing_keys():
    """回傳缺少的設定名稱清單，方便其他程式顯示友善的錯誤訊息。"""
    missing = []
    if not OPENALEX_API_KEY:
        missing.append("OPENALEX_API_KEY")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    return missing