# test_speed.py  （暫時的測試檔：比較各模型的回應速度）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_THINKING_LEVEL

MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
PROMPT = "請用繁體中文寫一段約 200 字的文字，說明什麼是自我調節學習。"

client = genai.Client(api_key=GEMINI_API_KEY)
kwargs = {}
if GEMINI_THINKING_LEVEL:
    kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
config = types.GenerateContentConfig(**kwargs)
print(f"思考等級設定：{GEMINI_THINKING_LEVEL or '預設'}\n")

for model in MODELS:
    for run in (1, 2):
        start = time.time()
        try:
            r = client.models.generate_content(model=model, contents=PROMPT, config=config)
            u = r.usage_metadata
            print(f"{model} 第{run}次：{time.time() - start:.1f} 秒 | "
                  f"輸出 {getattr(u, 'candidates_token_count', None)} tokens | "
                  f"思考 {getattr(u, 'thoughts_token_count', None)} tokens")
        except Exception as e:
            print(f"{model} 第{run}次：失敗（{time.time() - start:.1f} 秒）{str(e)[:120]}")