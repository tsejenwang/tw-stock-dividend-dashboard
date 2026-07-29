---
task: 07
title: 自動化排程管線
depends_on: [02, 03, 04, 05, 06]
estimate: 1 天
---

## 目標
讓任務 02–06 的所有資料擷取／計算腳本每天自動執行一次，產生的 JSON 自動發布，不需要人工手動跑腳本或依賴自己的電腦保持開機。

## 背景／現況
目前 `run_daily_push.ps1` 是本機 PowerShell 腳本，要靠 Windows工作排程器觸發，缺點是電腦沒開機就不會執行。`WBS.md` 的架構決策是改用 **GitHub Actions 排程（cron）**，在 GitHub 的伺服器上執行，不依賴本機。

## 範圍
包含：
1. 撰寫 GitHub Actions workflow（`.github/workflows/update-data.yml`）：
   - 排程時間：建議台股收盤後（下午 1:30 收盤，抓資料建議排在下午 2:00–3:00 之後，讓 TWSE/TPEx 官方資料更新完成），注意 GitHub Actions cron 用 UTC 時間，要換算成台北時間（UTC+8）。
   - 依序（或平行，視資源相依關係）執行任務 02、03、04、05、06 的腳本。
   - 把新產生的 JSON commit 並 push 回 repo（觸發 GitHub Pages 自動重新部署）。
2. 失敗處理：任一步驟失敗時，workflow 要明確失敗（不要吞掉錯誤），方便發現問題；可以考慮失敗時透過既有的 LINE 推播機制通知（沿用 `line_push.py` 的 token 設定方式，但改成失敗通知訊息，屬於任務 12 的加值項目，這裡先不強制）。
3. Secrets 管理：如果排程過程需要任何憑證（例如 LINE token），要用 GitHub repo 的 Secrets 功能，不能把 token 寫死進程式碼或 commit 進 repo。
4. 執行時間評估：任務 03（10 年份全市場歷史資料）可能是耗時最久的步驟，需要確認能在 GitHub Actions 免費額度的時限內跑完（單一 job 預設 6 小時上限，但要避免浪費額度，也要避免對 TWSE/TPEx 發送過於密集的請求被限流）。

不包含：
- 實際 GitHub repo 的建立與推送（任務 01 已建立本機 git repo，但推到 GitHub 這件事屬於任務 11「部署」的前置動作，需要先跟需求方確認帳號/repo 設定）
- 前端頁面本身（任務 08–10）

## 驗收標準
- [ ] workflow 檔案語法正確（可以用 `act` 工具本機測試，或先手動觸發一次 `workflow_dispatch` 驗證）
- [ ] 排程執行後，`data/` 底下的 JSON 檔案有更新且 commit 訊息清楚（例如 `chore: update daily stock data 2026-07-29`）
- [ ] 任一資料來源暫時失效時，workflow 會明確顯示失敗，不會悄悄產生空資料或舊資料當新資料用
- [ ] 記錄下整個 pipeline 的實際執行時間，供後續優化參考

## 技術備註
- GitHub Actions 語法：`on: schedule: - cron: '...'`，注意 cron 表達式用 UTC。
- 這個任務要等到 02–06 的腳本介面（輸入輸出路徑、執行方式）都穩定後才適合做，避免 workflow 寫好又要因為腳本介面變動而跟著改。
