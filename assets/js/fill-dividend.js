// 個股填息查詢:填息天數 + 填息後連續維持比原股價高的天數,依年度顯示。
//
// 資料來源(僅支援上市/TSE,已實測確認瀏覽器可直接跨網域呼叫,回應含
// Access-Control-Allow-Origin: * ):
//   - TWT49U:除權除息計算結果表(全市場,依日期區間查詢,一次可查多年)
//     https://www.twse.com.tw/exchangeReport/TWT49U?response=json&startDate=YYYYMMDD&endDate=YYYYMMDD
//   - STOCK_DAY:個股單月每日收盤價
//     https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMM01&stockNo=CODE
// 上櫃(TPEx)的對應 API 沒有開放 CORS,瀏覽器端無法直接查,這個功能只支援上市股票。
//
// 查詢結果會存進 localStorage,同一檔股票 1 天內重複查詢不會再打 API。

const FillDividend = (() => {
  const CACHE_PREFIX = "fillDividendCache_v1_";
  const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 1 天
  const MAX_FILL_SEARCH_DAYS = 365; // 除息日起超過這個天數還沒填息,就標記「逾期未填息」
  const MAX_MAINTAIN_SEARCH_DAYS = 365; // 填息後最多追蹤這麼多天的連續維持天數
  const HISTORY_YEARS = 10; // TWT49U 查詢往回抓幾年

  function roundToInt(n) {
    return Math.round(n);
  }

  function rocDateToIso(rocStr) {
    // "114/08/01" -> "2025-08-01"
    const parts = rocStr.split("/");
    if (parts.length !== 3) return null;
    const year = parseInt(parts[0], 10) + 1911;
    const mm = parts[1].padStart(2, "0");
    const dd = parts[2].padStart(2, "0");
    return `${year}-${mm}-${dd}`;
  }

  function toNumber(v) {
    if (v == null) return NaN;
    const n = parseFloat(String(v).replace(/,/g, ""));
    return n;
  }

  function daysBetween(isoA, isoB) {
    return Math.round((new Date(isoB + "T00:00:00Z") - new Date(isoA + "T00:00:00Z")) / 86400000);
  }

  function monthStartIso(iso) {
    return iso.slice(0, 7) + "-01";
  }

  function addMonthsIso(iso, n) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCMonth(d.getUTCMonth() + n);
    return d.toISOString().slice(0, 7) + "-01";
  }

  async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`API 請求失敗(HTTP ${resp.status}):${url}`);
    return resp.json();
  }

  // ---- 抓某檔股票的歷史除權除息事件(只留有現金股利成分的「息」「權息」事件) ----
  async function fetchExDividendEvents(code) {
    const today = new Date();
    const endDate = today.toISOString().slice(0, 10).replace(/-/g, "");
    const startYear = today.getFullYear() - HISTORY_YEARS;
    const startDate = `${startYear}0101`;
    const url = `https://www.twse.com.tw/exchangeReport/TWT49U?response=json&startDate=${startDate}&endDate=${endDate}`;
    const data = await fetchJSON(url);
    if (data.stat !== "OK" || !data.data) return [];

    const fields = data.fields || [];
    const idxDate = fields.indexOf("資料日期");
    const idxCode = fields.indexOf("股票代號");
    const idxPreClose = fields.indexOf("除權息前收盤價");
    const idxRefPrice = fields.indexOf("除權息參考價");
    const idxType = fields.indexOf("權/息");

    const events = [];
    for (const row of data.data) {
      if (row[idxCode] !== code) continue;
      const type = row[idxType];
      if (type !== "息" && type !== "權息") continue; // 只留有現金股利成分的事件(填息,不是填權)
      const exDateRoc = row[idxDate];
      const exDateIso = rocDateToIso(exDateRoc.replace(/年|月/g, "/").replace("日", ""));
      const preClose = toNumber(row[idxPreClose]);
      if (!exDateIso || isNaN(preClose)) continue;
      events.push({ exDate: exDateIso, preClose, type });
    }
    events.sort((a, b) => (a.exDate < b.exDate ? 1 : -1)); // 新到舊
    return events;
  }

  // ---- 抓某檔股票從某天起的每日收盤價,抓到超過 maxDays 天份或抓到今天為止 ----
  async function fetchDailyPricesFrom(code, startIso, maxDays) {
    const prices = [];
    const todayIso = new Date().toISOString().slice(0, 10);
    let cursor = monthStartIso(startIso);
    let guard = 0;
    while (guard < 15) {
      guard++;
      const param = cursor.replace(/-/g, "");
      let monthData;
      try {
        monthData = await fetchJSON(
          `https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=${param}&stockNo=${code}`
        );
      } catch (e) {
        break;
      }
      if (monthData.stat === "OK" && monthData.data) {
        const fields = monthData.fields || [];
        const idxDate = fields.indexOf("日期");
        const idxClose = fields.indexOf("收盤價");
        for (const row of monthData.data) {
          const iso = rocDateToIso(row[idxDate]);
          const close = toNumber(row[idxClose]);
          if (iso && !isNaN(close) && iso >= startIso) {
            prices.push({ date: iso, close });
          }
        }
      }
      const lastIso = prices.length ? prices[prices.length - 1].date : cursor;
      if (cursor >= todayIso) break;
      if (daysBetween(startIso, lastIso) >= maxDays) break;
      cursor = addMonthsIso(cursor, 1);
      if (cursor > todayIso) break;
    }
    return prices;
  }

  // ---- 對單一除息事件計算填息天數 + 填息後連續維持天數 ----
  async function analyzeEvent(code, event) {
    const prices = await fetchDailyPricesFrom(
      code,
      event.exDate,
      MAX_FILL_SEARCH_DAYS + MAX_MAINTAIN_SEARCH_DAYS
    );
    if (!prices.length) {
      return { ...event, status: "no_data" };
    }

    let fillIdx = -1;
    for (let i = 0; i < prices.length; i++) {
      if (daysBetween(event.exDate, prices[i].date) > MAX_FILL_SEARCH_DAYS) break;
      if (prices[i].close >= event.preClose) {
        fillIdx = i;
        break;
      }
    }

    if (fillIdx === -1) {
      const lastChecked = prices[prices.length - 1];
      const daysSoFar = daysBetween(event.exDate, lastChecked.date);
      const status = daysSoFar >= MAX_FILL_SEARCH_DAYS ? "not_filled_overdue" : "not_filled_yet";
      return { ...event, status, fillDays: null, maintainDays: null };
    }

    const fillDate = prices[fillIdx].date;
    const fillDays = daysBetween(event.exDate, fillDate);

    let maintainDays = 0;
    let maintainCapped = false;
    for (let i = fillIdx; i < prices.length; i++) {
      const elapsed = daysBetween(fillDate, prices[i].date);
      if (elapsed > MAX_MAINTAIN_SEARCH_DAYS) {
        maintainCapped = true;
        break;
      }
      if (prices[i].close >= event.preClose) {
        maintainDays = i - fillIdx + 1; // 連續交易日數(含填息當天)
      } else {
        break; // 只要比原股價低就停止累計
      }
    }
    // 如果一路算到資料抓取上限都還沒跌破,代表可能還在維持中,不是「已結束」
    if (!maintainCapped && fillIdx + maintainDays - 1 === prices.length - 1) {
      const todayIso = new Date().toISOString().slice(0, 10);
      if (prices[prices.length - 1].date >= todayIso || daysBetween(prices[prices.length - 1].date, todayIso) <= 3) {
        maintainCapped = null; // 代表「維持中,尚未跌破,資料抓到最新交易日」
      }
    }

    return { ...event, status: "filled", fillDate, fillDays, maintainDays, maintainCapped };
  }

  // ---- localStorage 快取 ----
  function readCache(code) {
    try {
      const raw = localStorage.getItem(CACHE_PREFIX + code);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (Date.now() - parsed.cachedAt > CACHE_TTL_MS) return null;
      return parsed.events;
    } catch (e) {
      return null;
    }
  }

  function writeCache(code, events) {
    try {
      localStorage.setItem(
        CACHE_PREFIX + code,
        JSON.stringify({ cachedAt: Date.now(), events })
      );
    } catch (e) {
      // localStorage 滿了或被瀏覽器擋掉,忽略,不影響功能
    }
  }

  /**
   * 查詢某檔上市股票的填息分析結果(依年度,新到舊)。
   * @param {string} code 股票代號
   * @param {boolean} forceRefresh 是否略過快取強制重查
   * @returns {Promise<Array>} 每個除息事件一筆:
   *   { exDate, preClose, type, status, fillDate?, fillDays?, maintainDays?, maintainCapped? }
   */
  async function getFillDividendReport(code, forceRefresh = false) {
    if (!forceRefresh) {
      const cached = readCache(code);
      if (cached) return cached;
    }
    const events = await fetchExDividendEvents(code);
    const results = [];
    for (const event of events) {
      const analyzed = await analyzeEvent(code, event);
      results.push(analyzed);
    }
    writeCache(code, results);
    return results;
  }

  return { getFillDividendReport };
})();

if (typeof window !== "undefined") {
  window.FillDividend = FillDividend;
}
