# test_gemini.py  （暫時的測試檔，確認 Gemini 能連線）
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, get_missing_keys

if "GEMINI_API_KEY" in get_missing_keys():
    raise SystemExit("找不到 GEMINI_API_KEY，請檢查 .env")

print(f"使用模型：{GEMINI_MODEL}")

client = genai.Client(api_key=GEMINI_API_KEY)

try:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="請用一句繁體中文說明什麼是學術論文的摘要。",
    )
    print(response.text)
except Exception as e:
    print("Gemini 呼叫失敗：")
    print(e)