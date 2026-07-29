# -*- coding: utf-8 -*-
"""
任務 03:資料擷取－5 年／10 年平均殖利率排行(上市＋上櫃全市場)

抓法移植自 c:\\stock\\stock_widget.py 的 fetch_year_snapshot() / fetch_yield_history(),
差別是這裡保留「全市場」快照(該程式原本只留單一股票),並且加上 TPEx(上櫃)。

資料來源(已實測確認可用):
- TWSE(上市)歷史快照(依日期,全市場一次回傳):
  https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=json&date=YYYYMMDD&selectType=ALL
  欄位:證券代號,證券名稱,收盤價,殖利率(%),股利年度,本益比,股價淨值比,財報年/季
  (沒有直接給「每股股利」,比照 stock_widget.py 用 收盤價×殖利率/100 回推)
- TPEx(上櫃)歷史快照(依日期,全市場一次回傳):
  https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php
    ?l=zh-tw&d=民國年/MM/DD&o=json
  欄位:股票代號,公司名稱,本益比,每股股利,股利年度,殖利率(%),股價淨值比
  (這個有直接給「每股股利」,不用回推)

輸出:
- data/yield_history_raw.json      {year: {code: {name, market, close, yield, dividend}}}
                                    給任務 05(合理價)、06(風險試算預設值)重複使用
- data/yield_5y_top20.json         近 5 年平均殖利率 Top 20
- data/yield_10y_top20.json        近 10 年平均殖利率 Top 20
- data/yield_5y_full.json / yield_10y_full.json  完整清單
"""
import json
import time
from datetime import date, timedelta

from common import data_path, http_get, new_session

TWSE_URL = "https://www.twse.com.tw/exchangeReport/BWIBBU_d"
TPEX_URL = "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php"

FUND_SAMPLE_YEARS = 10
SAMPLE_MMDD = (6, 30)
TOP_N = 20
# 資料來源偶爾會出現離譜的殖利率(例如上櫃 8913 全銓曾回傳 189.67%,應是股價/股利
# 申報異常而非真實配息),超過這個門檻的樣本點直接視為不可信,不納入計算。
MAX_PLAUSIBLE_YIELD = 30.0


def _to_float(v):
    if v in (None, "", "-", "N/A"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def fetch_twse_snapshot(session, d: date):
    params = {"response": "json", "date": d.strftime("%Y%m%d"), "selectType": "ALL"}
    resp = http_get(session, TWSE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    fields = data.get("fields") or []
    rows = data.get("data") or []
    if not fields or not rows:
        return {}
    try:
        idx_code = fields.index("證券代號")
        idx_name = fields.index("證券名稱")
        idx_yield = fields.index("殖利率(%)")
    except ValueError:
        return {}
    # 較早年份(例如 2016)的欄位裡沒有「收盤價」,這種情況股利改回傳 None,
    # 但代號/名稱/殖利率仍然有效,不能整批放棄。
    idx_close = fields.index("收盤價") if "收盤價" in fields else None
    result = {}
    for row in rows:
        try:
            code = str(row[idx_code]).strip()
            close = _to_float(row[idx_close]) if idx_close is not None else None
            yld = _to_float(row[idx_yield])
        except (IndexError, TypeError):
            continue
        if yld is None or yld < 0 or yld > MAX_PLAUSIBLE_YIELD:
            continue
        dividend = (close * yld / 100.0) if (close and close > 0) else None
        result[code] = {
            "name": str(row[idx_name]).strip(),
            "market": "tse",
            "close": close,
            "yield": yld,
            "dividend": dividend,
        }
    return result


def fetch_tpex_snapshot(session, d: date):
    roc_year = d.year - 1911
    roc_str = f"{roc_year}/{d.month:02d}/{d.day:02d}"
    params = {"l": "zh-tw", "d": roc_str, "o": "json"}
    resp = http_get(session, TPEX_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    tables = data.get("tables") or []
    if not tables:
        return {}
    table = tables[0]
    fields = table.get("fields") or []
    rows = table.get("data") or []
    if not fields or not rows:
        return {}
    try:
        idx_code = fields.index("股票代號")
        idx_name = fields.index("公司名稱")
        idx_div = fields.index("每股股利")
        idx_yield = fields.index("殖利率(%)")
    except ValueError:
        return {}
    result = {}
    for row in rows:
        try:
            code = str(row[idx_code]).strip()
            dividend = _to_float(row[idx_div])
            yld = _to_float(row[idx_yield])
        except (IndexError, TypeError):
            continue
        if yld is None or yld < 0 or yld > MAX_PLAUSIBLE_YIELD:
            continue
        result[code] = {
            "name": str(row[idx_name]).strip(),
            "market": "otc",
            "close": None,
            "yield": yld,
            "dividend": dividend,
        }
    return result


def fetch_year_snapshot(session, year: int):
    """回傳某年抽樣日(6/30 附近,遇假日往前找)全市場快照:{code: {...}}"""
    mm, dd = SAMPLE_MMDD
    for back in range(8):
        d = date(year, mm, dd) - timedelta(days=back)
        twse = {}
        tpex = {}
        try:
            twse = fetch_twse_snapshot(session, d)
        except Exception as e:
            print(f"  [WARN] {d} 上市快照擷取失敗:{e}")
        try:
            tpex = fetch_tpex_snapshot(session, d)
        except Exception as e:
            print(f"  [WARN] {d} 上櫃快照擷取失敗:{e}")
        if twse or tpex:
            merged = {**twse, **tpex}
            print(f"  [OK] {year} 年快照取得成功({d},上市{len(twse)}檔+上櫃{len(tpex)}檔)")
            return merged
        time.sleep(0.8)
    print(f"  [WARN] {year} 年附近找不到可用的殖利率資料")
    return {}


def fetch_yield_history(session):
    today = date.today()
    history = {}
    for i in range(FUND_SAMPLE_YEARS):
        year = today.year - 1 - i
        snap = fetch_year_snapshot(session, year)
        if snap:
            history[year] = snap
        time.sleep(1.2)
    return history


def rank_by_avg_yield(history: dict, num_years: int, min_samples: int = 3):
    """取歷史字典裡最近 num_years 個年度,對每檔股票算平均殖利率並排序"""
    years_sorted = sorted(history.keys(), reverse=True)[:num_years]
    per_stock = {}
    for year in years_sorted:
        for code, info in history[year].items():
            per_stock.setdefault(code, {"name": info["name"], "market": info["market"], "yields": []})
            per_stock[code]["yields"].append(info["yield"])

    ranked = []
    for code, info in per_stock.items():
        yields = info["yields"]
        if len(yields) < min_samples:
            continue
        avg_yield = sum(yields) / len(yields)
        ranked.append({
            "code": code,
            "name": info["name"],
            "market": info["market"],
            "avg_yield": round(avg_yield, 3),
            "sample_years": len(yields),
        })
    ranked.sort(key=lambda r: r["avg_yield"], reverse=True)
    return ranked


def main():
    session = new_session()
    print(f"開始抓取近 {FUND_SAMPLE_YEARS} 年全市場殖利率快照(每年 1 個抽樣日,上市+上櫃各一次 API 呼叫)...")
    history = fetch_yield_history(session)

    if not history:
        print("[ERROR] 沒有任何一年抓到資料,不產生輸出檔案。")
        return

    with open(data_path("yield_history_raw.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"已儲存 {len(history)} 個年度的原始快照到 yield_history_raw.json")

    for label, num_years, min_samples in (("5y", 5, 3), ("10y", 10, 3)):
        ranked = rank_by_avg_yield(history, num_years, min_samples)
        top20 = ranked[:TOP_N]
        with open(data_path(f"yield_{label}_top20.json"), "w", encoding="utf-8") as f:
            json.dump(top20, f, ensure_ascii=False, indent=2)
        with open(data_path(f"yield_{label}_full.json"), "w", encoding="utf-8") as f:
            json.dump(ranked, f, ensure_ascii=False, indent=2)
        print(f"近{label}平均殖利率:全市場 {len(ranked)} 檔有足夠樣本,Top20 已輸出")
        for i, r in enumerate(top20[:5], start=1):
            print(f"  {i}. {r['code']} {r['name']} ({r['market']}) 平均{r['avg_yield']}% (樣本{r['sample_years']}年)")


if __name__ == "__main__":
    main()
