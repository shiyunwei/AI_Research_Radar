# 📡 AI Research Radar（AI 學術研究雷達）

> 結合真實學術文獻圖譜與大型語言模型之研究趨勢分析與選題輔助平台。  
> 專為大學專題、論文前期研究探索設計，具備**嚴格防 AI 幻覺**檢核機制。

---

## 💡 解決痛點

1. **文獻搜尋門檻高**：不知道如何將中文想法精準轉為學術英文關鍵字。
2. **AI 幻覺問題**：傳統問答 AI 容易捏造不存在的論文、假作者或虛構數據。
3. **資訊過載**：文獻篇數眾多，難以快速梳理主要流派與未解問題。

---

## ⚙️ 核心架構與運作流程

- **前端介面**：Streamlit、Plotly（互動視覺化）
- **學術資料庫**：OpenAlex REST API（數億篇真實學術論文圖譜）
- **語言模型**：Google Gemini 3.6 Flash（備用模型：Gemini 3.5 Flash Lite）
- **後端驗證**：Python 3.12、Pandas、Pydantic（嚴格檢驗文獻代號與事實數據）

### 系統流程：
1. **輸入主題** ➔ Gemini 提煉英文關鍵字、同義詞與 3~5 組檢索詞。
2. **檢索文獻** ➔ OpenAlex API 取得真實論文、還原摘要並去重。
3. **AI 結構化分析** ➔ 自動分類、趨勢推論、提出具體研究方向與可行性評估。
4. **防幻覺校驗** ➔ 代號嚴格比對，排除虛構文獻，未有證據支持者自動降級為推論。
5. **匯出成果** ➔ 支援一鍵下載結構化 Markdown 研究報告。

---

## 🚀 快速開始 (Quick Start)

### 1. 取得專案並建立虛擬環境
```bash
git clone https://github.com/shiyunwei/AI_Research_Radar.git
cd AI_Research_Radar

# 建立並啟動虛擬環境 (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安裝相依套件
```bash
pip install -r requirements.txt
```

### 3. 設定環境變數
請在專案根目錄建立 `.env` 檔案（可參考 `.env.example`）：
```env
OPENALEX_API_KEY=your_openalex_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
GEMINI_THINKING_LEVEL=LOW
```

### 4. 啟動系統
```bash
python -m streamlit run app.py
```
啟動後，瀏覽器將自動開啟 `http://localhost:8501`。

---

## 📁 專案目錄結構

```text
AI_Research_Radar/
├── app.py                      # Streamlit 網站主應用程式
├── config.py                   # 環境變數與設定讀取
├── requirements.txt            # 專案相依套件清單
├── services/
│   ├── openalex_service.py     # OpenAlex API 串接、摘要還原、檢索與去重
│   └── gemini_service.py       # Gemini 結構化輸出、關鍵字擴展與防幻覺檢核
├── utils/
│   ├── data_processor.py       # 資料聚合統計、推薦閱讀篩選演算法
│   ├── visualization.py        # Plotly 互動式圖表生成
│   └── report.py               # Markdown 研究報告格式化產出
└── tests/                      # 系統測試與各階段驗證腳本
```
