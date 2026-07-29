# 台股資訊儀表板

可透過網頁瀏覽的台股資訊儀表板:殖利率排行(當年／近5年／近10年)、個股填息查詢、
ETF 殖利率查詢、除權息日程表、定存股合理價查詢、定存股風險試算。完整規劃與任務拆解見
[`WBS.md`](WBS.md) 與 [`tasks/`](tasks/) 資料夾。

**正式網址:https://tsejenwang.github.io/tw-stock-dividend-dashboard/**
(2026-07-29 部署,已用瀏覽器實測三個頁面資料正常載入)

## 專案結構

```
data/                       排程產生的 JSON 資料檔(前端直接讀這裡)
scripts/                    Python 資料擷取／計算腳本
  common.py                   共用 HTTP 重試機制
  fetch_current_yield.py      當年殖利率排行(任務02)
  fetch_multi_year_yield.py   5年/10年平均殖利率排行(任務03)
  fetch_ex_dividend_calendar.py  除權除息日程表(任務04)
  compute_fair_value.py       合理價試算(任務05,依賴任務03的輸出)
  fetch_etf_yield.py          ETF 殖利率(月配/季配加總年度總額),資料源 Yahoo Finance
assets/
  css/style.css                共用樣式
  js/nav.js                    共用導覽列
  js/data-utils.js             共用資料讀取/錯誤呈現小工具
  js/risk.js                   風險試算公式(任務06,純前端計算)
  js/fill-dividend.js          個股填息天數查詢(即時向 TWSE 查、localStorage 快取,詳見下方)
index.html                  殖利率排行榜頁面(任務08)+ 個股填息查詢分頁
etf.html                    ETF 殖利率排行榜 + 個股 ETF 歷年殖利率查詢
calendar.html                除權息日程表頁面(任務09)
calculators.html             合理價查詢＋風險試算頁面(任務10)
.github/workflows/update-data.yml  自動化排程(任務07,已驗證可在 GitHub 上正常執行)
.claude/agents/              資料/前端/維運三個角色的 subagent 定義,供之後派工使用
get_data.py / line_push.py / run_daily_push.ps1  舊版 LINE 推播腳本(仍可用,見下方)
```

## 個股填息查詢(index.html 第 4 分頁)

查詢某檔上市股票近 10 年每次除息事件的「填息天數」與「填息後連續維持比原股價高的
天數」,依年度顯示,同一頁面也會帶出「各股每年殖利率狀況」。

- **資料來源**(瀏覽器端即時查詢,已確認支援 CORS):
  - `www.twse.com.tw/exchangeReport/TWT49U`(除權除息計算結果表,依日期區間查詢)
  - `www.twse.com.tw/exchangeReport/STOCK_DAY`(個股單月每日收盤價)
  - 殖利率數字取自既有的 `data/yield_history_raw.json`(排程已產生的資料,不用另外查)
- **只支援上市(TWSE)股票**:上櫃(TPEx)對應的 API 沒有開放跨網域(CORS)存取,瀏覽器
  端無法直接查,查詢上櫃股票會顯示明確提示,不會顯示錯誤的資料。
- **定義**:填息天數 = 除息日起到收盤價回到除息前收盤價以上所花的交易日數(超過 365
  天算逾期未填息);填息後連續維持天數 = 填息後收盤價連續維持在除息前股價以上的交易日
  數,只要有一天跌破就停止累計(最多追蹤 365 天,達上限顯示「N+ 天」)。
- **效能與快取**:每次查詢會依序呼叫多次 API(每個除息事件抓一段每日股價),第一次
  查某檔股票可能要 10~30 秒,查過的結果會存進瀏覽器 `localStorage`(1 天內有效),
  同一檔股票短時間內重複查詢會直接讀快取,不會重打 API。

## ETF 殖利率查詢(etf.html)

TWSE 的 `BWIBBU_ALL`/`BWIBBU_d`(既有排行榜的資料源)不含 ETF,所以 ETF 用獨立的
排程腳本(`scripts/fetch_etf_yield.py`)另外處理,資料源改用 Yahoo Finance 的配息事件。

- **排行榜**:目前約 94 檔有配息紀錄的 ETF,依「最近一個完整年度」殖利率由高到低排序。
- **年度總配息計算**:月配/季配/半年配/年配的 ETF,都是把同一年度所有配息事件加總成
  一個年度總額,再除以該年 6 月 30 日附近的參考股價算出年度殖利率,方便不同配息頻率
  的 ETF 互相比較。
- **個股查詢**:輸入代號或名稱可以查單一 ETF 每個年度的明細,今年還沒走完的部分會
  標示「累計中,尚未結束」,不會跟完整年度的數字混在一起比較。
- **已知限制**:少數 ETF(例如剛好近一兩年沒有配息、或 Yahoo Finance 資料更新較慢的
  冷門標的)「最近一個完整年度」不是 2025 年,排行榜的「年度」欄位會誠實反映這件事,
  使用時留意每一列實際對應的年度,不是所有 ETF 都是同一年的資料在比較。
- 2024~2025 年新掛牌、還沒有配息紀錄的主動式 ETF 不會出現在這份資料裡(屬正常現象,
  不是抓取錯誤)。

## 本機執行

### 1. 安裝套件

```powershell
pip install -r requirements.txt
```

### 2. 產生資料(依序執行,合理價試算依賴多年殖利率的輸出)

```powershell
python scripts\fetch_current_yield.py
python scripts\fetch_multi_year_yield.py
python scripts\fetch_ex_dividend_calendar.py
python scripts\compute_fair_value.py
python scripts\fetch_etf_yield.py
```

`fetch_etf_yield.py` 目前**還沒有加進** `.github/workflows/update-data.yml` 的自動排程
(約 260 檔 ETF、逐檔呼叫 Yahoo Finance,實測跑一次要 2 分多鐘,先手動執行,要不要排程
自動化屬於任務07維運範圍,還沒決定)。

執行後 `data/` 資料夾會產生:
`current_yield_top20.json`、`current_yield_full.json`、
`yield_history_raw.json`、`yield_5y_top20.json`、`yield_5y_full.json`、
`yield_10y_top20.json`、`yield_10y_full.json`、
`ex_dividend_calendar.json`、`fair_value.json`、
`etf_yield.json`、`etf_yield_ranked.json`。

### 3. 本機瀏覽網頁

前端用 `fetch()` 讀取 `data/*.json`,不能直接用 `file://` 開啟(會被瀏覽器 CORS 擋掉),
要用簡易 HTTP server:

```powershell
python -m http.server 8765
```

然後瀏覽器開 `http://127.0.0.1:8765/index.html`(排行榜)、
`http://127.0.0.1:8765/calendar.html`(除權息日程)、
`http://127.0.0.1:8765/calculators.html`(合理價／風險試算)。

## 資料來源(皆已實測確認可用)

| 用途 | 端點 |
|---|---|
| 上市當年殖利率 | `openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL` |
| 上櫃當年殖利率 | `www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis` |
| 上市歷史殖利率快照(依日期) | `www.twse.com.tw/exchangeReport/BWIBBU_d` |
| 上櫃歷史殖利率快照(依日期) | `www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php` |
| 上市除權息預告表 | `openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL` |
| 上櫃除權息預告表 | `www.tpex.org.tw/openapi/v1/tpex_exright_prepost` |
| ETF 配息備援(合理價試算用) | Yahoo Finance chart API(`query1.finance.yahoo.com`) |

## 已知限制

- 殖利率數值有做合理性過濾(超過 30% 直接排除),因為來源資料偶爾會出現離譜的異常值
  (實測時發現過一檔上櫃股票某年回傳 189% 殖利率,判斷是申報/資料異常)。
- 合理價試算(任務05)的 ETF 備援清單目前只涵蓋 5 檔常見高股息 ETF(0056、00878、
  00919、00929、00713),沒有嘗試涵蓋所有 ETF。
- 除權息日程表(任務04)的涵蓋範圍以官方「預告表」當下公告的資料為準,不是任意未來
  日期都查得到。
- 已推上 GitHub(`github.com/tsejenwang/tw-stock-dividend-dashboard`)並開啟 GitHub Pages,
  但 `data/` 底下的 JSON 目前是**手動跑腳本後 commit 上去的一次性快照**,還不會每天自動
  更新——`.github/workflows/update-data.yml` 排程還沒有實際在 GitHub Actions 上跑過、
  沒有驗證過排程觸發是否正常,這屬於任務07的收尾,還沒執行。
- LINE 推播(`line_push.py`)目前還是讀舊的根目錄 `data.json`(欄位較簡單),沒有整合
  新的 `data/` 底下的排行/日程/試算資料,這屬於任務12的範圍,還沒執行。

## 部署狀態

- Repo:`https://github.com/tsejenwang/tw-stock-dividend-dashboard`(public)
- GitHub Pages:`https://tsejenwang.github.io/tw-stock-dividend-dashboard/`(2026-07-29 上線)
- 自動化排程(`.github/workflows/update-data.yml`)已完整驗證:repo 的 Settings → Actions →
  General 已開啟「Read and write permissions」,手動觸發 `workflow_dispatch` 執行成功
  (53 秒),四支資料腳本都正確執行,最後「Commit and push updated data」步驟印出
  `No data changes`(因為當天稍早已手動跑過同一批資料,內容相同,正確跳過不產生空 commit)。
  排程本身設定每個交易日台北時間 14:30 自動執行,之後資料有變化時就會自動 commit + push。
