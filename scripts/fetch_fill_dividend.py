# -*- coding: utf-8 -*-
"""
任務:個股填息查詢 —— 熱門股票的雲端預先計算快取

把 assets/js/fill-dividend.js 裡「填息天數」「填息後連續維持天數」的計算邏輯移植成
Python 排程,對「熱門股票」(current_yield_top20 / yield_5y_top20 / yield_10y_top20
三份清單聯集,只保留上市 tse)預先算好結果存進 data/fill_dividend_cache.json,前端
之後直接讀取,不用每個使用者每個裝置各自即時查一次。

資料來源(與 fill-dividend.js 完全相同,只支援上市股票):
  - TWT49U:除權除息計算結果表(全市場,依日期區間查詢,一次可查多年)
    https://www.twse.com.tw/exchangeReport/TWT49U?response=json&startDate=YYYYMMDD&endDate=YYYYMMDD
    只呼叫「一次」(近 10 年區間),在記憶體裡依股票代號分組,取出目標股票各自的事件清單。
  - STOCK_DAY:個股單月每日收盤價(逐檔逐月呼叫,只對「這次判定需要重算」的股票才打)
    https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMM01&stockNo=CODE

計算邏輯(逐字對應 fill-dividend.js 的常數與 analyzeEvent()):
  - MAX_FILL_SEARCH_DAYS = 365:除息日起超過這個天數還沒填息,標記「逾期未填息」
    (not_filled_overdue)。
  - MAX_MAINTAIN_SEARCH_DAYS = 365:填息後最多追蹤這麼多天的連續維持天數。
  - HISTORY_YEARS = 10:TWT49U 查詢往回抓幾年。
  - TWT49U 的「權/息」欄位只留 "息" 或 "權息" 兩種(有現金股利成分),排除純「權」事件。
  - 填息天數:除息日起到收盤價 >= 除息前收盤價花了幾個交易日;超過 365 天算逾期未填息。
  - 填息後維持天數:填息後「連續」維持在除息前股價以上的交易日數,只要有一天跌破就停止
    累計(不是找到下一次還原就繼續算)。maintainCapped === null 代表「維持中,尚未跌破,
    資料抓到最新交易日」。

增量重算邏輯(避免每次執行都整批空轉):
  先讀取既有的 data/fill_dividend_cache.json,對每一檔目標股票判斷這次要不要重算:
    - 快取裡沒有這檔股票的紀錄 -> 要重算。
    - 這次從 TWT49U 抓到的該股票最新事件日期,比快取記錄裡最新的事件日期還新 -> 要重算。
    - 快取裡任何一筆事件的狀態是 not_filled_yet,或已填息但 maintainCapped is None
      (維持中,尚未確定跌破)-> 要重算。
    - 其餘情況(maintainCapped === True 已確定跌破、或 not_filled_overdue)視為穩定結果,
      沿用快取舊值,不重算。
  需要重算的股票,對該股票的「全部事件」整批重新分析(不做局部合併)。

輸出:data/fill_dividend_cache.json
  {
    "generated_at": "YYYY-MM-DD",
    "stocks": {
      "2330": {
        "name": "台積電",
        "computed_at": "YYYY-MM-DD",
        "events": [
          {exDate, preClose, type, status, fillDate?, fillDays?, maintainDays?, maintainCapped?}
        ]
      }
    }
  }
"""
import json
import os
import time
from collections import defaultdict
from datetime import date

from common import data_path, http_get, new_session

TWT49U_URL = "https://www.twse.com.tw/exchangeReport/TWT49U"
STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"

MAX_FILL_SEARCH_DAYS = 365
MAX_MAINTAIN_SEARCH_DAYS = 365
HISTORY_YEARS = 10
REQUEST_SLEEP = 0.25  # STOCK_DAY 逐檔逐月呼叫的節流間隔

SOURCE_LISTS = ("current_yield_top20.json", "yield_5y_top20.json", "yield_10y_top20.json")


# ---------- 日期/數值工具(對應 fill-dividend.js 的同名函式) ----------

def roc_slash_date_to_iso(s):
    """'114/07/01' -> '2025-07-01'"""
    if not s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0]) + 1911
        mm = parts[1].zfill(2)
        dd = parts[2].zfill(2)
        return f"{year}-{mm}-{dd}"
    except ValueError:
        return None


def twt49u_date_to_iso(s):
    """'114年01月02日' -> '114/01/02' -> '2025-01-02'(比照 JS 的字串取代邏輯)"""
    if not s:
        return None
    converted = s.replace("年", "/").replace("月", "/").replace("日", "")
    return roc_slash_date_to_iso(converted)


def to_number(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s == "" or s == "--":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def days_between(iso_a, iso_b):
    da = date.fromisoformat(iso_a)
    db = date.fromisoformat(iso_b)
    return (db - da).days


def month_start_iso(iso):
    return iso[:7] + "-01"


def add_months_iso(iso, n):
    d = date.fromisoformat(iso)
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return f"{year:04d}-{month:02d}-01"


# ---------- TWT49U:一次抓全市場近 10 年除權息事件,依代號分組 ----------

def fetch_twt49u_events(session, target_codes):
    """回傳 {code: [事件, ...]}(每檔已依 exDate 新到舊排序),只對 target_codes 保留資料。"""
    today = date.today()
    end_date = today.strftime("%Y%m%d")
    start_year = today.year - HISTORY_YEARS
    start_date = f"{start_year}0101"

    resp = http_get(
        session, TWT49U_URL,
        params={"response": "json", "startDate": start_date, "endDate": end_date},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    events_by_code = defaultdict(list)
    if data.get("stat") != "OK" or not data.get("data"):
        return events_by_code

    fields = data.get("fields") or []
    idx_date = fields.index("資料日期")
    idx_code = fields.index("股票代號")
    idx_preclose = fields.index("除權息前收盤價")
    idx_type = fields.index("權/息")

    for row in data["data"]:
        code = str(row[idx_code]).strip()
        if code not in target_codes:
            continue
        ev_type = row[idx_type]
        if ev_type not in ("息", "權息"):
            continue  # 只留有現金股利成分的事件(填息,不是填權)
        ex_date_iso = twt49u_date_to_iso(row[idx_date])
        pre_close = to_number(row[idx_preclose])
        if not ex_date_iso or pre_close is None:
            continue
        events_by_code[code].append({"exDate": ex_date_iso, "preClose": pre_close, "type": ev_type})

    for code in events_by_code:
        events_by_code[code].sort(key=lambda e: e["exDate"], reverse=True)  # 新到舊

    return events_by_code


# ---------- STOCK_DAY:逐月抓單一股票收盤價 ----------

def fetch_daily_prices_from(session, code, start_iso, max_days):
    prices = []
    today_iso = date.today().isoformat()
    cursor = month_start_iso(start_iso)
    guard = 0

    while guard < 15:
        guard += 1
        param = cursor.replace("-", "")
        try:
            resp = http_get(
                session, STOCK_DAY_URL,
                params={"response": "json", "date": param, "stockNo": code},
                timeout=15,
            )
            month_data = resp.json()
        except Exception:
            break
        finally:
            time.sleep(REQUEST_SLEEP)

        if month_data.get("stat") == "OK" and month_data.get("data"):
            fields = month_data.get("fields") or []
            if "日期" in fields and "收盤價" in fields:
                idx_date = fields.index("日期")
                idx_close = fields.index("收盤價")
                for row in month_data["data"]:
                    iso = roc_slash_date_to_iso(row[idx_date])
                    close = to_number(row[idx_close])
                    if iso and close is not None and iso >= start_iso:
                        prices.append({"date": iso, "close": close})

        last_iso = prices[-1]["date"] if prices else cursor
        if cursor >= today_iso:
            break
        if days_between(start_iso, last_iso) >= max_days:
            break
        cursor = add_months_iso(cursor, 1)
        if cursor > today_iso:
            break

    return prices


# ---------- 單一除息事件的填息/維持天數分析(逐字對應 JS analyzeEvent) ----------

def analyze_event(session, code, event):
    prices = fetch_daily_prices_from(
        session, code, event["exDate"], MAX_FILL_SEARCH_DAYS + MAX_MAINTAIN_SEARCH_DAYS
    )
    if not prices:
        return {**event, "status": "no_data"}

    fill_idx = -1
    for i, p in enumerate(prices):
        if days_between(event["exDate"], p["date"]) > MAX_FILL_SEARCH_DAYS:
            break
        if p["close"] >= event["preClose"]:
            fill_idx = i
            break

    if fill_idx == -1:
        last_checked = prices[-1]
        days_so_far = days_between(event["exDate"], last_checked["date"])
        status = "not_filled_overdue" if days_so_far >= MAX_FILL_SEARCH_DAYS else "not_filled_yet"
        return {**event, "status": status, "fillDays": None, "maintainDays": None}

    fill_date = prices[fill_idx]["date"]
    fill_days = days_between(event["exDate"], fill_date)

    maintain_days = 0
    maintain_capped = False
    for i in range(fill_idx, len(prices)):
        elapsed = days_between(fill_date, prices[i]["date"])
        if elapsed > MAX_MAINTAIN_SEARCH_DAYS:
            maintain_capped = True
            break
        if prices[i]["close"] >= event["preClose"]:
            maintain_days = i - fill_idx + 1  # 連續交易日數(含填息當天)
        else:
            break  # 只要比原股價低就停止累計

    # 如果一路算到資料抓取上限都還沒跌破,代表可能還在維持中,不是「已結束」
    if not maintain_capped and fill_idx + maintain_days - 1 == len(prices) - 1:
        today_iso = date.today().isoformat()
        last_price_date = prices[-1]["date"]
        if last_price_date >= today_iso or days_between(last_price_date, today_iso) <= 3:
            maintain_capped = None  # 維持中,尚未跌破,資料抓到最新交易日

    return {
        **event, "status": "filled", "fillDate": fill_date, "fillDays": fill_days,
        "maintainDays": maintain_days, "maintainCapped": maintain_capped,
    }


# ---------- 目標股票清單 ----------

def load_target_codes():
    """讀三份 top20 清單,取聯集,只保留 market == 'tse',回傳 {code: name}(依字典序無關,插入序即可)。"""
    codes = {}
    for fname in SOURCE_LISTS:
        path = data_path(fname)
        if not os.path.exists(path):
            print(f"  [WARN] 找不到 {fname},跳過")
            continue
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        for row in rows:
            if row.get("market") != "tse":
                continue
            code = row.get("code")
            name = row.get("name")
            if not code:
                continue
            codes[code] = name
    return codes


# ---------- 增量重算判斷 ----------

def needs_recompute(cached_entry, new_events):
    if cached_entry is None:
        return True
    cached_events = cached_entry.get("events", [])

    if not new_events:
        # 這次 TWT49U 近 10 年窗口內完全查不到事件:
        # 如果快取本來就是空的,維持穩定不用重算;如果快取本來有事件(可能是舊事件過了
        # 10 年滑動窗口而消失),需要重算以反映窗口變化。
        return len(cached_events) > 0

    if not cached_events:
        return True  # 之前沒事件,這次冒出新事件

    if new_events[0]["exDate"] > cached_events[0]["exDate"]:
        return True  # 有更新的除息事件發生

    for ev in cached_events:
        if ev.get("status") == "not_filled_yet":
            return True
        if ev.get("status") == "filled" and ev.get("maintainCapped") is None:
            return True

    return False


# ---------- main ----------

def main():
    session = new_session()

    print("讀取熱門股票清單(current_yield_top20 / yield_5y_top20 / yield_10y_top20 聯集,僅 tse)...")
    target = load_target_codes()
    codes_sorted = sorted(target.keys())
    print(f"目標股票數量:{len(codes_sorted)}")
    for code in codes_sorted:
        print(f"  {code} {target[code]}")

    cache_file = data_path("fill_dividend_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            old_cache = json.load(f)
        print(f"讀取既有快取:{cache_file}(上次產生時間 {old_cache.get('generated_at')})")
    else:
        old_cache = {}
        print("沒有既有快取,視為全部初次計算。")
    old_stocks = old_cache.get("stocks", {})

    print("抓取 TWT49U 除權息事件(近 10 年,一次性查詢全市場再依代號分組)...")
    events_by_code = fetch_twt49u_events(session, set(codes_sorted))
    print(f"目標股票中,近 10 年內有現金股利成分除權息事件的共 {len(events_by_code)} 檔")

    today_iso = date.today().isoformat()
    result_stocks = {}
    recompute_count = 0
    skip_count = 0
    fail_count = 0

    total = len(codes_sorted)
    for i, code in enumerate(codes_sorted, start=1):
        name = target[code]
        new_events = events_by_code.get(code, [])
        cached_entry = old_stocks.get(code)

        try:
            if needs_recompute(cached_entry, new_events):
                results = [analyze_event(session, code, event) for event in new_events]
                result_stocks[code] = {"name": name, "computed_at": today_iso, "events": results}
                recompute_count += 1
                print(f"  [{i}/{total}] {code} {name}: 重算完成,{len(results)} 筆事件")
            else:
                cached_entry["name"] = name  # 名稱可能更新,其餘沿用
                result_stocks[code] = cached_entry
                skip_count += 1
                print(f"  [{i}/{total}] {code} {name}: 沿用快取(穩定結果),跳過")
        except Exception as e:
            print(f"  [WARN] [{i}/{total}] {code} {name} 處理失敗:{e}")
            fail_count += 1
            if cached_entry:
                result_stocks[code] = cached_entry  # 失敗時盡量保留舊值,不要讓資料整檔消失

    # 曾經被快取過、但這次不在 top20 聯集目標清單裡的股票(跌出排行榜),保留舊資料不刪除,
    # 只是不會再被排程主動更新。
    carried_over = 0
    for code, entry in old_stocks.items():
        if code not in result_stocks:
            result_stocks[code] = entry
            carried_over += 1

    output = {"generated_at": today_iso, "stocks": result_stocks}
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(
        f"完成。目標股票 {total} 檔:重算 {recompute_count} 檔 / 沿用快取 {skip_count} 檔 / "
        f"失敗 {fail_count} 檔 / 跌出排行榜但保留舊資料 {carried_over} 檔。已輸出 {cache_file}"
    )


if __name__ == "__main__":
    main()
