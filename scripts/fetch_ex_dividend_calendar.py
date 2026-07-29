# -*- coding: utf-8 -*-
"""
任務 04:資料擷取－除權除息日程表(上市＋上櫃)

資料來源研究結果(已實測確認可用,從 openapi.twse.com.tw / www.tpex.org.tw 的
swagger 規格檔裡找到,不是用猜的路徑):

- TWSE(上市)除權息預告表:
  https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL
  欄位:Date(除權息日期,民國年格式如 "1150805"), Code, Name, Exdividend(除權/息別),
        StockDividendRatio(無償配股率), SubscriptionRatio(現金增資配股率),
        SubscriptionPricePerShare(現金增資認購價), CashDividend(現金股利),
        SharesOffered, SharesEmpOwner, SharesholderOwner, StockHoldingRatio

- TPEx(上櫃)除權息預告表:
  https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost
  欄位:ExRrightsExDividendDate(除權息日期,民國年格式), SecuritiesCompanyCode,
        CompanyName, ExRrightsExDividend(除權/息別), StockDividendRatio,
        SubscriptionRatioToNewSharesIssued, SubscriptionPricePerShare,
        CashDividend, AllocatedForPublicUnderwriting, SubscribedByEmployees,
        SubscribedByExistingShareholders, SubscribedProRataInThousandShares

注意:這兩個都是「預告表」,涵蓋的時間範圍以官方當下公告的資料為準(通常是
近期已公告、尚未執行或剛執行的除權息事件),不是任意未來日期都查得到。

輸出:data/ex_dividend_calendar.json
  {
    "generated_at": "...",
    "upcoming": [...以除權息日由近到遠排序,今天(含)以後...],
    "recent": [...以除權息日由近到遠排序,今天以前 RECENT_DAYS 天內...]
  }
"""
import json
from datetime import date, timedelta

from common import data_path, http_get, new_session

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost"

RECENT_DAYS = 60  # "近期已發生"回溯天數


def _to_float(v):
    if v in (None, "", "-", "N/A", "0.00000000") :
        return None
    try:
        f = float(str(v).replace(",", ""))
        return f if f != 0 else None
    except ValueError:
        return None


def roc_date_to_iso(roc_str: str):
    if not roc_str or len(roc_str) != 7 or not roc_str.isdigit():
        return None
    year = int(roc_str[:3]) + 1911
    month = roc_str[3:5]
    day = roc_str[5:7]
    try:
        d = date(year, int(month), int(day))
    except ValueError:
        return None
    return d.isoformat()


def fetch_twse(session):
    resp = http_get(session, TWSE_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    result = []
    for row in rows:
        ex_date = roc_date_to_iso(row.get("Date"))
        if not ex_date:
            continue
        result.append({
            "code": row.get("Code"),
            "name": row.get("Name"),
            "market": "tse",
            "ex_date": ex_date,
            "type": row.get("Exdividend"),
            "cash_dividend": _to_float(row.get("CashDividend")),
            "stock_dividend_ratio": _to_float(row.get("StockDividendRatio")),
        })
    return result


def fetch_tpex(session):
    resp = http_get(session, TPEX_URL, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    result = []
    for row in rows:
        ex_date = roc_date_to_iso(row.get("ExRrightsExDividendDate"))
        if not ex_date:
            continue
        result.append({
            "code": row.get("SecuritiesCompanyCode"),
            "name": row.get("CompanyName"),
            "market": "otc",
            "ex_date": ex_date,
            "type": row.get("ExRrightsExDividend"),
            "cash_dividend": _to_float(row.get("CashDividend")),
            "stock_dividend_ratio": _to_float(row.get("StockDividendRatio")),
        })
    return result


def main():
    session = new_session()

    print("正在擷取上市(TWSE)除權息預告表...")
    try:
        twse_rows = fetch_twse(session)
        print(f"  取得 {len(twse_rows)} 筆")
    except Exception as e:
        print(f"  [WARN] 上市除權息資料擷取失敗:{e}")
        twse_rows = []

    print("正在擷取上櫃(TPEx)除權息預告表...")
    try:
        tpex_rows = fetch_tpex(session)
        print(f"  取得 {len(tpex_rows)} 筆")
    except Exception as e:
        print(f"  [WARN] 上櫃除權息資料擷取失敗:{e}")
        tpex_rows = []

    all_rows = twse_rows + tpex_rows
    if not all_rows:
        print("[ERROR] 上市與上櫃資料都擷取失敗,不產生輸出檔案。")
        return

    today = date.today()
    recent_cutoff = today - timedelta(days=RECENT_DAYS)

    upcoming = sorted(
        (r for r in all_rows if r["ex_date"] >= today.isoformat()),
        key=lambda r: r["ex_date"],
    )
    recent = sorted(
        (r for r in all_rows if recent_cutoff.isoformat() <= r["ex_date"] < today.isoformat()),
        key=lambda r: r["ex_date"],
        reverse=True,
    )

    output = {
        "generated_at": today.isoformat(),
        "upcoming": upcoming,
        "recent": recent,
    }
    with open(data_path("ex_dividend_calendar.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完成。即將到來 {len(upcoming)} 筆,近 {RECENT_DAYS} 天內已發生 {len(recent)} 筆。")
    for r in upcoming[:5]:
        print(f"  {r['ex_date']} {r['code']} {r['name']} ({r['market']}) {r['type']} 現金股利{r['cash_dividend']}")


if __name__ == "__main__":
    main()
