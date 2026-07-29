# 台股資訊儀表板

可透過網頁瀏覽的台股資訊儀表板:殖利率排行(當年／近5年／近10年)、除權息日程表、
定存股合理價查詢、定存股風險試算。完整規劃與任務拆解見 [`WBS.md`](WBS.md) 與
[`tasks/`](tasks/) 資料夾。

## 專案結構

```
data/                       排程產生的 JSON 資料檔(前端直接讀這裡)
scripts/                    Python 資料擷取／計算腳本
  common.py                   共用 HTTP 重試機制
  fetch_current_yield.py      當年殖利率排行(任務02)
  fetch_multi_year_yield.py   5年/10年平均殖利率排行(任務03)
  fetch_ex_dividend_calendar.py  除權除息日程表(任務04)
  compute_fair_value.py       合理價試算(任務05,依賴任務03的輸出)
assets/
  css/style.css                共用樣式
  js/nav.js                    共用導覽列
  js/data-utils.js             共用資料讀取/錯誤呈現小工具
  js/risk.js                   風險試算公式(任務06,純前端計算)
index.html                  殖利率排行榜頁面(任務08)
calendar.html                除權息日程表頁面(任務09)
calculators.html             合理價查詢＋風險試算頁面(任務10)
.github/workflows/update-data.yml  自動化排程草稿(任務07,還沒推上 GitHub 執行過)
get_data.py / line_push.py / run_daily_push.ps1  舊版 LINE 推播腳本(仍可用,見下方)
```

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
```

執行後 `data/` 資料夾會產生:
`current_yield_top20.json`、`current_yield_full.json`、
`yield_history_raw.json`、`yield_5y_top20.json`、`yield_5y_full.json`、
`yield_10y_top20.json`、`yield_10y_full.json`、
`ex_dividend_calendar.json`、`fair_value.json`。

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
- git 已安裝並完成本機 `git init` + 第一個 commit,但**還沒有 remote、還沒推到 GitHub**,
  所以任務11(部署到 GitHub Pages)、任務07 的排程還沒有實際在 GitHub 上執行驗證過。
  `.github/workflows/update-data.yml` 已驗證 YAML 語法正確,等 repo 推上 GitHub 後才能
  真正觸發。
- LINE 推播(`line_push.py`)目前還是讀舊的根目錄 `data.json`(欄位較簡單),沒有整合
  新的 `data/` 底下的排行/日程/試算資料,這屬於任務12的範圍,還沒執行。

## 部署(尚未執行,需要先確認)

依 [`tasks/11-deployment.md`](tasks/11-deployment.md),部署到 GitHub Pages 前需要先確認:
GitHub 帳號/repo 名稱、public/private、是否要自訂網域、由誰執行 `git push`(本機 repo
已經就緒,只差 remote 設定)。
