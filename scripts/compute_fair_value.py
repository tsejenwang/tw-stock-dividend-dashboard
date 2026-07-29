# -*- coding: utf-8 -*-
"""
任務 05:合理價試算邏輯

公式(已由需求方確認,見 tasks/05-fair-value-calculation.md):
  基準 = 該股票最近 5 年平均現金股利
  合理價 = 基準 × 20(年息 5%)
  便宜價 = 基準 × 16(年息 6.25%)
  昂貴價 = 基準 × 32(年息 3.125%)
這三個倍數是固定常數,不像 stock_widget.py 的 compute_valuation() 是依個股自己
的歷史平均殖利率動態換算。

主要資料來源:任務 03 產出的 data/yield_history_raw.json(全市場歷史殖利率快照)。
備援資料來源(ETF,BWIBBU_d 沒有資料的品種):Yahoo Finance 配息事件,邏輯移植自
c:\\stock\\stock_widget.py 的 fetch_dividend_valuation_from_yahoo(),一樣改用
「近 5 年平均年度配息 × 16/20/32」。

輸出:data/fair_value.json  {code: {name, avg_dividend_5y, reasonable, cheap,
                                     expensive, sample_years, data_source}}
"""
import json
import time
from collections import defaultdict

from common import data_path, http_get, new_session

REASONABLE_MULT = 20
CHEAP_MULT = 16
EXPENSIVE_MULT = 32
MIN_SAMPLE_YEARS = 3

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# BWIBBU_d 沒有股利資料的常見高股息 ETF,改用 Yahoo Finance 配息事件當備援。
ETF_FALLBACK = [
    {"code": "0056", "name": "元大高股息", "symbol": "0056.TW"},
    {"code": "00878", "name": "國泰永續高股息", "symbol": "00878.TW"},
    {"code": "00919", "name": "群益台灣精選高息", "symbol": "00919.TW"},
    {"code": "00929", "name": "復華台灣科技優息", "symbol": "00929.TW"},
    {"code": "00713", "name": "元大台灣高息低波", "symbol": "00713.TW"},
]


def load_yield_history():
    with open(data_path("yield_history_raw.json"), encoding="utf-8") as f:
        return json.load(f)


def compute_from_history(history: dict):
    """回傳 {code: {...}},用最近 5 個抽樣年度的平均現金股利套固定倍數"""
    years_sorted = sorted((int(y) for y in history.keys()), reverse=True)[:5]
    per_stock = defaultdict(lambda: {"name": None, "dividends": []})

    for year in years_sorted:
        snap = history.get(str(year)) or history.get(year) or {}
        for code, info in snap.items():
            div = info.get("dividend")
            per_stock[code]["name"] = info.get("name")
            if div is not None and div > 0:
                per_stock[code]["dividends"].append(div)

    result = {}
    for code, info in per_stock.items():
        divs = info["dividends"]
        if len(divs) < MIN_SAMPLE_YEARS:
            continue
        avg_div = sum(divs) / len(divs)
        result[code] = {
            "name": info["name"],
            "avg_dividend_5y": round(avg_div, 4),
            "reasonable": round(avg_div * REASONABLE_MULT, 2),
            "cheap": round(avg_div * CHEAP_MULT, 2),
            "expensive": round(avg_div * EXPENSIVE_MULT, 2),
            "sample_years": len(divs),
            "data_source": "bwibbu_d",
        }
    return result


def fetch_etf_dividend_avg(session, symbol: str):
    """近 5 年 ETF 配息事件(Yahoo Finance),回傳每年配息加總後的清單"""
    url = YAHOO_CHART_URL.format(symbol=symbol)
    params = {"interval": "1d", "range": "10y", "events": "div"}
    resp = http_get(session, url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = (data.get("chart") or {}).get("result")
    if not results:
        return []
    dividends = ((results[0].get("events") or {}).get("dividends")) or {}
    if not dividends:
        return []

    by_year = defaultdict(float)
    for ev in dividends.values():
        ts, amount = ev.get("date"), ev.get("amount")
        if ts is None or amount is None:
            continue
        year = time.gmtime(ts).tm_year
        by_year[year] += amount

    this_year = time.gmtime().tm_year
    years_sorted = sorted((y for y in by_year if y < this_year), reverse=True)[:5]
    return [by_year[y] for y in years_sorted]


def compute_etf_fallback(session, existing: dict):
    added = 0
    for etf in ETF_FALLBACK:
        code = etf["code"]
        if code in existing:
            continue  # 主要資料源已經有結果就不用備援
        try:
            divs = fetch_etf_dividend_avg(session, etf["symbol"])
        except Exception as e:
            print(f"  [WARN] {code} {etf['name']} 從 Yahoo Finance 取得配息失敗:{e}")
            continue
        if len(divs) < MIN_SAMPLE_YEARS:
            print(f"  [WARN] {code} {etf['name']} 配息樣本不足({len(divs)} 年),略過")
            continue
        avg_div = sum(divs) / len(divs)
        existing[code] = {
            "name": etf["name"],
            "avg_dividend_5y": round(avg_div, 4),
            "reasonable": round(avg_div * REASONABLE_MULT, 2),
            "cheap": round(avg_div * CHEAP_MULT, 2),
            "expensive": round(avg_div * EXPENSIVE_MULT, 2),
            "sample_years": len(divs),
            "data_source": "yahoo_dividends",
        }
        added += 1
        print(f"  [OK] {code} {etf['name']} ETF 備援計算完成(近{len(divs)}年平均股利 {avg_div:.3f})")
    return added


def main():
    print("讀取任務 03 的歷史殖利率快照...")
    history = load_yield_history()
    result = compute_from_history(history)
    print(f"主要資料源(BWIBBU_d)算出 {len(result)} 檔股票的合理價")

    print("補算 ETF 備援清單...")
    session = new_session()
    added = compute_etf_fallback(session, result)
    print(f"ETF 備援新增 {added} 檔")

    with open(data_path("fair_value.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"完成,共 {len(result)} 檔股票有合理價資料,已輸出 fair_value.json")
    for code in list(result.keys())[:5]:
        r = result[code]
        print(f"  {code} {r['name']}: 便宜{r['cheap']} / 合理{r['reasonable']} / 昂貴{r['expensive']}"
              f"(近5年均股利{r['avg_dividend_5y']}, 來源{r['data_source']})")


if __name__ == "__main__":
    main()
