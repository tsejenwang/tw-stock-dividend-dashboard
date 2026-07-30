# -*- coding: utf-8 -*-
"""
任務:ETF 殖利率查詢

TWSE BWIBBU_ALL / BWIBBU_d(現有 fetch_current_yield.py / fetch_multi_year_yield.py
的資料源)不含 ETF,所以 ETF 需要獨立的資料管線,改用 Yahoo Finance 配息事件計算。

資料來源(已實測確認可用):
1. ETF 清單:https://openapi.twse.com.tw/v1/opendata/t187ap47_L
   (基金基本資料彙總表,JSON)。這份資料實測下來 264 筆全部都是 ETF(欄位「基金類型」
   都是 XX指數股票型基金/主動式交易所交易基金之類),但仍比照需求用基金代號正規表示式
   `^00\d{2,4}[A-Z]?$` 過濾,避免未來資料源混入非 ETF 基金。
2. 每檔 ETF 的配息歷史 + 股價:Yahoo Finance chart API
   https://query1.finance.yahoo.com/v8/finance/chart/{code}.TW?interval=1d&range=10y&events=div
   寫法移植自 c:\\stock\\stock_widget.py 的 fetch_dividend_valuation_from_yahoo()
   (約第 759-838 行),但這裡不是算「單一動態合理價」,而是把配息依「日曆年」分組
   加總,算出每個完整年度的「年度總配息」與「年度殖利率」。

計算邏輯:
- 配息事件依「發放日期」(events.dividends 的 date timestamp)所在的日曆年分組
- 每年度所有配息金額加總 = 年度總配息(月配/季配/半年配/年配都一樣加總成一個年度總額)
- 年度殖利率(%) = 年度總配息 / 參考股價 * 100,參考股價比照
  fetch_multi_year_yield.py 的 SAMPLE_MMDD = (6, 30) 慣例,取當年 6/30 附近收盤價,
  找不到就用 price_near() 邏輯retreat 找最接近的一筆
- 殖利率超過 MAX_PLAUSIBLE_YIELD(30%)視為資料異常,該年度不採用
- 今年(還沒過完)不列入「已完成年度」,但額外標示成「本年度累計中」

輸出:
- data/etf_yield.json          {code: {name, years: {year: {...}}, latest_completed_year,
                                        current_year_partial}}
- data/etf_yield_ranked.json   依最近一個完整年度殖利率由高到低排序的陣列
"""
import calendar
import json
import re
import time
from collections import defaultdict

from common import data_path, http_get, new_session

FUND_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap47_L"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

ETF_CODE_RE = re.compile(r"^00\d{2,4}[A-Z]?$")
SAMPLE_MMDD = (6, 30)
YEAR_RANGE = "10y"
# 殖利率合理性過濾門檻,沿用專案既有慣例(fetch_multi_year_yield.py / stock_widget.py)。
MAX_PLAUSIBLE_YIELD = 30.0
MIN_YEARS_TO_KEEP = 1  # 至少要有 1 個完整年度的資料才輸出(剛上市的 ETF 可能完全沒有)
REQUEST_SLEEP = 0.3

FREQ_LABELS = {12: "月配", 4: "季配", 2: "半年配", 1: "年配"}


def fetch_etf_list(session):
    """抓 ETF 基本資料清單,回傳 {code: name},並印出篩選結果供人工確認。"""
    resp = http_get(session, FUND_LIST_URL, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    print(f"基金基本資料彙總表原始筆數:{len(rows)}")

    etfs = {}
    for row in rows:
        code = str(row.get("基金代號") or "").strip()
        name = str(row.get("基金簡稱") or "").strip()
        if not code or not ETF_CODE_RE.match(code):
            continue
        etfs[code] = name

    print(f"符合 ETF 代號規則(^00\\d{{2,4}}[A-Z]?$)篩選後:{len(etfs)} 檔")
    for code in list(etfs.keys())[:5]:
        print(f"  {code} {etfs[code]}")

    # 人工確認幾個知名 ETF 有沒有出現
    for known_code, known_name in (("0050", "元大台灣50"), ("0056", "元大高股息"), ("00878", "國泰永續高股息")):
        if known_code in etfs:
            print(f"  [確認] {known_code} {etfs[known_code]} 有出現在篩選結果中")
        else:
            print(f"  [WARN] {known_code}({known_name})沒有出現在篩選結果中!")

    return etfs


def fetch_etf_year_data(session, code: str):
    """
    抓單一 ETF 近 10 年的配息事件 + 收盤價序列,回傳
    {year: {"total_dividend": float, "num_payments": int}} 以及 price_near() 函式。
    找不到資料回傳 (None, None)。
    """
    symbol = f"{code}.TW"
    url = YAHOO_CHART_URL.format(symbol=symbol)
    params = {"interval": "1d", "range": YEAR_RANGE, "events": "div"}
    resp = http_get(session, url, params=params, timeout=15)
    if resp.status_code != 200:
        return None, None
    try:
        data = resp.json()
    except ValueError:
        return None, None

    results = (data.get("chart") or {}).get("result")
    if not results:
        return None, None
    result = results[0]

    dividends = ((result.get("events") or {}).get("dividends")) or {}
    if not dividends:
        return None, None

    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote")) or [{}])[0].get("close") or []
    price_series = sorted(
        (ts, c) for ts, c in zip(timestamps, closes) if c is not None
    )
    if not price_series:
        return None, None

    def price_near(ts):
        """找出不晚於 ts 的最後一筆收盤價;找不到就退而求其次取最早一筆。"""
        candidates = [p for p in price_series if p[0] <= ts]
        if candidates:
            return candidates[-1][1]
        return price_series[0][1]

    by_year = defaultdict(list)
    for ev in dividends.values():
        ts, amount = ev.get("date"), ev.get("amount")
        if ts is None or amount is None:
            continue
        year = time.gmtime(ts).tm_year
        by_year[year].append(amount)

    year_data = {}
    for year, amounts in by_year.items():
        year_data[year] = {
            "total_dividend": round(sum(amounts), 4),
            "num_payments": len(amounts),
        }

    return year_data, price_near


def frequency_label(num_payments: int) -> str:
    return FREQ_LABELS.get(num_payments, f"{num_payments}次配息")


def build_etf_record(code: str, name: str, year_data: dict, price_near, this_year: int):
    """把 year_data + price_near 轉成單一 ETF 的輸出結構,回傳 dict 或 None(無可用年度)。"""
    years_out = {}
    current_year_partial = None

    for year, info in sorted(year_data.items(), reverse=True):
        ref_ts = calendar.timegm((year, SAMPLE_MMDD[0], SAMPLE_MMDD[1], 0, 0, 0, 0, 0, 0))
        # 今年 6/30 可能還沒到(尚未除息完該年度全部次數),但仍抓一個參考價供「累計中」顯示用;
        # 真正決定要不要當作已完成年度是用 year < this_year 判斷,不是用 6/30 是否已過判斷。
        ref_price = price_near(ref_ts)
        if not ref_price or ref_price <= 0:
            continue

        total = info["total_dividend"]
        yld = round(total / ref_price * 100, 3)

        entry = {
            "total_dividend": round(total, 3),
            "yield": yld,
            "num_payments": info["num_payments"],
            "frequency_label": frequency_label(info["num_payments"]),
            "ref_price": round(ref_price, 3),
        }

        if year >= this_year:
            # 今年還沒過完,不列入已完成年度清單,另外標示成累計中
            if yld <= MAX_PLAUSIBLE_YIELD:
                current_year_partial = {"year": str(year), **entry}
            continue

        if yld <= 0 or yld > MAX_PLAUSIBLE_YIELD:
            continue  # 殖利率異常,跳過該年度

        years_out[str(year)] = entry

    if not years_out:
        return None

    latest_completed_year = str(max(int(y) for y in years_out.keys()))

    if current_year_partial:
        # 今年還沒配完全年次數,直接用今年至今的配息次數對照配息頻率會誤判(例如季配
        # ETF 今年才配 2 次,會被誤標成「半年配」)。改用最近一個已完整年度的配息頻率
        # 當代表值,才是這檔 ETF 實際的配息頻率。
        current_year_partial["frequency_label"] = years_out[latest_completed_year]["frequency_label"]

    record = {
        "name": name,
        "years": years_out,
        "latest_completed_year": latest_completed_year,
    }
    if current_year_partial:
        record["current_year_partial"] = current_year_partial
    return record


def main():
    session = new_session()
    print("抓取 ETF 清單...")
    etfs = fetch_etf_list(session)
    if not etfs:
        print("[ERROR] ETF 清單抓取失敗或篩選結果為空,不繼續執行。")
        return

    this_year = time.gmtime().tm_year
    codes = sorted(etfs.keys())
    total = len(codes)
    print(f"開始逐檔抓取 {total} 檔 ETF 的配息歷史(Yahoo Finance,每次呼叫間隔 {REQUEST_SLEEP}s)...")

    start_ts = time.time()
    result = {}
    ok_count = 0
    skip_no_data = 0
    skip_no_valid_year = 0
    fail_count = 0

    for i, code in enumerate(codes, start=1):
        name = etfs[code]
        try:
            year_data, price_near = fetch_etf_year_data(session, code)
        except Exception as e:
            print(f"  [WARN] {code} {name} 抓取失敗:{e}")
            fail_count += 1
            time.sleep(REQUEST_SLEEP)
            continue

        if not year_data:
            skip_no_data += 1
            time.sleep(REQUEST_SLEEP)
            continue

        record = build_etf_record(code, name, year_data, price_near, this_year)
        if record is None:
            skip_no_valid_year += 1
            time.sleep(REQUEST_SLEEP)
            continue

        result[code] = record
        ok_count += 1
        if i % 25 == 0 or i == total:
            print(f"  進度 {i}/{total}...(目前成功 {ok_count} 檔)")

        time.sleep(REQUEST_SLEEP)

    elapsed = time.time() - start_ts
    print(
        f"抓取完成,耗時 {elapsed:.1f} 秒。成功 {ok_count} 檔 / "
        f"無配息資料 {skip_no_data} 檔 / 無有效年度 {skip_no_valid_year} 檔 / 失敗 {fail_count} 檔"
    )

    with open(data_path("etf_yield.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已輸出 data/etf_yield.json,共 {len(result)} 檔 ETF")

    # 排行榜:依「最近一個完整年度」的殖利率由高到低排序
    ranked = []
    for code, rec in result.items():
        year = rec["latest_completed_year"]
        info = rec["years"][year]
        ranked.append({
            "code": code,
            "name": rec["name"],
            "year": year,
            "total_dividend": info["total_dividend"],
            "yield": info["yield"],
            "frequency_label": info["frequency_label"],
        })
    ranked.sort(key=lambda r: r["yield"], reverse=True)

    with open(data_path("etf_yield_ranked.json"), "w", encoding="utf-8") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)
    print(f"已輸出 data/etf_yield_ranked.json,共 {len(ranked)} 檔")

    print("排行榜前 10 名:")
    for i, r in enumerate(ranked[:10], start=1):
        print(f"  {i}. {r['code']} {r['name']} ({r['year']}年): 總配息{r['total_dividend']} "
              f"殖利率{r['yield']}% ({r['frequency_label']})")

    print("抽查知名 ETF:")
    for code in ("0050", "0056", "00878"):
        if code in result:
            rec = result[code]
            y = rec["latest_completed_year"]
            info = rec["years"][y]
            print(f"  {code} {rec['name']}: {y}年 總配息{info['total_dividend']} "
                  f"殖利率{info['yield']}% ({info['frequency_label']}, 參考價{info['ref_price']})")
        else:
            print(f"  [WARN] {code} 沒有出現在最終結果中")


if __name__ == "__main__":
    main()
