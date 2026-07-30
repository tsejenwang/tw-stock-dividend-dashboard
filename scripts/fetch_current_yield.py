# -*- coding: utf-8 -*-
"""
任務 02:資料擷取－當年殖利率排行(上市＋上櫃全市場)

資料來源(已實測確認可用):
- TWSE(上市):https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL
  欄位:Date, Code, Name, PEratio, DividendYield, PBratio
  (注意:舊版 get_data.py 用的 BWIBHT_ALL 端點已經失效,正確端點是 BWIBBU_ALL)
- TPEx(上櫃):https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis
  欄位:Date, SecuritiesCompanyCode, CompanyName, PriceEarningRatio,
        DividendPerShare, YieldRatio, PriceBookRatio
- TWSE(上市)全市場當日收盤價:
  https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
  欄位:Date, Code, Name, ..., ClosingPrice, ...
  (BWIBBU_ALL 沒有現金股利欄位,用這裡的收盤價 × 殖利率 ÷ 100 回推現金股利,
  公式比照 fetch_multi_year_yield.py 的 fetch_twse_snapshot())
- TPEx(上櫃)全市場當日收盤價:
  https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes
  欄位:Date, SecuritiesCompanyCode, CompanyName, Close, ...
  (只用來補上顯示用的收盤價,上櫃 cash_dividend 官方已直接提供,不用這裡回推)

輸出:
- data/current_yield_top20.json  前 20 名(殖利率由高到低)
- data/current_yield_full.json   全市場完整清單(供任務 05/06/10 查表用)
"""
import json
import sys

from common import data_path, http_get, new_session

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
TWSE_CLOSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_CLOSE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

TOP_N = 20
# 比照任務 03,過濾掉明顯不合理(可能是來源資料異常)的殖利率數字。
MAX_PLAUSIBLE_YIELD = 30.0


def roc_date_to_iso(roc_str: str):
    """"1150728" -> "2026-07-28";格式不符就回傳 None"""
    if not roc_str or len(roc_str) != 7 or not roc_str.isdigit():
        return None
    year = int(roc_str[:3]) + 1911
    month = roc_str[3:5]
    day = roc_str[5:7]
    return f"{year}-{month}-{day}"


def _to_float(v):
    if v in (None, "", "-", "N/A"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def fetch_twse_close(session):
    """回傳上市全市場當日收盤價 {code: (close_price, roc_date)}"""
    resp = http_get(session, TWSE_CLOSE_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    result = {}
    for row in rows:
        code = row.get("Code")
        close = _to_float(row.get("ClosingPrice"))
        if not code or close is None:
            continue
        result[code] = (close, row.get("Date"))
    return result


def fetch_tpex_close(session):
    """回傳上櫃全市場當日收盤價 {code: (close_price, roc_date)}"""
    resp = http_get(session, TPEX_CLOSE_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    result = {}
    for row in rows:
        code = row.get("SecuritiesCompanyCode")
        close = _to_float(row.get("Close"))
        if not code or close is None:
            continue
        result[code] = (close, row.get("Date"))
    return result


def fetch_twse(session):
    resp = http_get(session, TWSE_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()

    close_map = {}
    try:
        close_map = fetch_twse_close(session)
        print(f"  取得 {len(close_map)} 檔上市收盤價")
    except Exception as e:
        print(f"  [WARN] 上市收盤價擷取失敗,cash_dividend 將維持 None:{e}")

    result = []
    yield_date = None
    close_date = None
    for row in rows:
        yld = _to_float(row.get("DividendYield"))
        if yld is None or yld > MAX_PLAUSIBLE_YIELD:
            continue
        code = row.get("Code")
        yield_date = row.get("Date") or yield_date
        close_info = close_map.get(code)
        close = None
        cash_dividend = None
        if close_info is not None:
            close, close_date_row = close_info
            close_date = close_date_row or close_date
            if close and close > 0:
                cash_dividend = round(close * yld / 100.0, 4)
        result.append({
            "code": code,
            "name": row.get("Name"),
            "market": "tse",
            "yield": yld,
            "pe_ratio": _to_float(row.get("PEratio")),
            "pb_ratio": _to_float(row.get("PBratio")),
            "cash_dividend": cash_dividend,  # 用收盤價 × 殖利率 ÷ 100 回推(BWIBBU_ALL 無此欄位)
            "close": close,
            "date": roc_date_to_iso(row.get("Date")),
        })
    if close_map and yield_date and close_date and yield_date != close_date:
        print(f"  [WARN] 上市殖利率資料日期({yield_date})與收盤價資料日期({close_date})不一致")
    return result


def fetch_tpex(session):
    resp = http_get(session, TPEX_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()

    close_map = {}
    try:
        close_map = fetch_tpex_close(session)
        print(f"  取得 {len(close_map)} 檔上櫃收盤價")
    except Exception as e:
        print(f"  [WARN] 上櫃收盤價擷取失敗,close 欄位將維持 None:{e}")

    result = []
    yield_date = None
    close_date = None
    for row in rows:
        yld = _to_float(row.get("YieldRatio"))
        if yld is None or yld > MAX_PLAUSIBLE_YIELD:
            continue
        code = row.get("SecuritiesCompanyCode")
        yield_date = row.get("Date") or yield_date
        close_info = close_map.get(code)
        close = None
        if close_info is not None:
            close, close_date_row = close_info
            close_date = close_date_row or close_date
        result.append({
            "code": code,
            "name": row.get("CompanyName"),
            "market": "otc",
            "yield": yld,
            "pe_ratio": _to_float(row.get("PriceEarningRatio")),
            "pb_ratio": _to_float(row.get("PriceBookRatio")),
            "cash_dividend": _to_float(row.get("DividendPerShare")),  # 官方直接提供,不用收盤價回推覆蓋
            "close": close,
            "date": roc_date_to_iso(row.get("Date")),
        })
    if close_map and yield_date and close_date and yield_date != close_date:
        print(f"  [WARN] 上櫃殖利率資料日期({yield_date})與收盤價資料日期({close_date})不一致")
    return result


def main():
    session = new_session()

    print("正在擷取上市(TWSE)當年殖利率...")
    try:
        twse_rows = fetch_twse(session)
        print(f"  取得 {len(twse_rows)} 檔上市股票")
    except Exception as e:
        print(f"  [WARN] 上市資料擷取失敗:{e}")
        twse_rows = []

    print("正在擷取上櫃(TPEx)當年殖利率...")
    try:
        tpex_rows = fetch_tpex(session)
        print(f"  取得 {len(tpex_rows)} 檔上櫃股票")
    except Exception as e:
        print(f"  [WARN] 上櫃資料擷取失敗:{e}")
        tpex_rows = []

    all_rows = twse_rows + tpex_rows
    if not all_rows:
        print("[ERROR] 上市與上櫃資料都擷取失敗,不產生輸出檔案。")
        sys.exit(1)

    # 排除殖利率 <= 0(今年還沒配息/資料異常)的股票再排序
    ranked = sorted(
        (r for r in all_rows if r["yield"] and r["yield"] > 0),
        key=lambda r: r["yield"],
        reverse=True,
    )
    top20 = ranked[:TOP_N]

    with open(data_path("current_yield_top20.json"), "w", encoding="utf-8") as f:
        json.dump(top20, f, ensure_ascii=False, indent=2)
    with open(data_path("current_yield_full.json"), "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    print(f"完成。全市場共 {len(all_rows)} 檔,殖利率排行前 {len(top20)} 名已輸出。")
    if top20:
        print("前 5 名預覽:")
        for i, r in enumerate(top20[:5], start=1):
            print(f"  {i}. {r['code']} {r['name']} ({r['market']}) {r['yield']}%")


if __name__ == "__main__":
    main()
