---
task: 01
title: 專案初始化與環境設定
depends_on: []
estimate: 0.5–1 天
---

## 目標
把現有零散的檔案整理成一個有清楚結構、可持續擴充、之後能部署到 GitHub Pages 的專案骨架。

## 背景／現況
專案資料夾 `c:\Users\TseJenWang\Desktop\網頁測試` 目前有：
- `get_data.py`、`data.json`、`index.html`（有殘留重複 HTML，先不用管，任務 08 會重寫）
- `line_push.py`、`run_daily_push.ps1`、`line_config.example.json`
- `requirements.txt`（目前只有 `requests`、`pandas`）
- `.gitignore`（已排除 `line_config.json`）
- **目前不是 git repository**

完整架構決策見 [`../WBS.md`](../WBS.md) 的「架構決策與假設」章節：靜態網頁 + GitHub Actions 排程產生 JSON + GitHub Pages 部署，涵蓋上市＋上櫃股票。

## 範圍
包含：
1. 建立資料夾結構，建議：
   ```
   /data/                 -- 所有排程產生的 JSON 資料檔（取代目前散在根目錄的 data.json）
   /scripts/               -- 所有 Python 資料擷取／計算腳本
   /site/ 或直接用 repo 根目錄  -- 靜態網頁前端（依部署方式決定，GitHub Pages 預設抓根目錄或 /docs）
   /tasks/, WBS.md          -- 已存在，維持
   ```
   （如果覺得不需要大搬家，也可以把 `get_data.py` 留在原位，只新增 `scripts/` 放之後新的抓取腳本 — 判斷基準是「後續任務好不好接」，不用強求一次到位的完美結構）
2. 更新 `requirements.txt`：後續任務會用到的套件先預留，例如 `requests`、`pandas`（已有），之後任務會依需要再補。
3. 確認 Python 版本與虛擬環境（建議 `venv`），寫進 README。
4. **`git init` 這個資料夾，但先不要 push 到 GitHub** — 部署平台（GitHub Pages）與遠端 repo 這件事屬於「建立外部服務串接」，要在任務 11 執行前另外向需求方確認一次帳號/repo 名稱等細節。這個任務只需要把本機 git repo 建起來、做第一個 commit，方便後續任務用 diff 追蹤變更。
5. 建一個根目錄 `README.md`，簡述專案是什麼、資料夾結構、怎麼在本機跑資料擷取腳本。

不包含：
- 實際推到 GitHub、設定 GitHub Actions（任務 07、11）
- 任何資料擷取邏輯本身（任務 02–06）

## 驗收標準
- [ ] 資料夾結構清楚，之後的任務知道新檔案要放哪裡
- [ ] `git status` 乾淨，第一個 commit 已建立
- [ ] 根目錄有 `README.md` 說明如何在本機跑起來
- [ ] `requirements.txt` 可用 `pip install -r requirements.txt` 成功安裝

## 技術備註
- 不需要做任何 UI 或抓取邏輯，純粹是整理和打地基。
- 如果決定搬動 `get_data.py` / `index.html` 等既有檔案，記得同步更新 `run_daily_push.ps1` 裡的相對路徑。
