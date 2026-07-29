// 任務 06:風險試算邏輯(定存股買入/期末價與配息打平點試算)
//
// 公式(需求方確認的定義,見 tasks/06-risk-calculation.md):
//   投資報酬率(%) = (期末股價 − 買入股價 + 今年配息 × 持有年數) ÷ 買入股價 × 100
//   最低可容忍股價(打平價) = 買入股價 − 今年配息 × 持有年數
//   可容忍下跌金額 = 今年配息 × 持有年數
//   可容忍下跌百分比(%) = 可容忍下跌金額 ÷ 買入股價 × 100
//
// 純公式計算,不依賴任何後端資料,可以直接在瀏覽器端呼叫。

const RiskCalc = (() => {
  /**
   * @param {{buyPrice:number, endPrice:number, dividend:number, years:number}} input
   * @returns {{ok:true, returnRate:number, breakevenPrice:number,
   *            toleratedDropAmount:number, toleratedDropPct:number,
   *            noDividendBuffer:boolean} | {ok:false, error:string}}
   */
  function calc({ buyPrice, endPrice, dividend, years }) {
    buyPrice = Number(buyPrice);
    endPrice = Number(endPrice);
    dividend = Number(dividend);
    years = Number(years);

    if (!Number.isFinite(buyPrice) || buyPrice <= 0) {
      return { ok: false, error: "買入股價必須是大於 0 的數字" };
    }
    if (!Number.isFinite(endPrice) || endPrice < 0) {
      return { ok: false, error: "期末股價必須是大於等於 0 的數字" };
    }
    if (!Number.isFinite(dividend) || dividend < 0) {
      return { ok: false, error: "今年配息不能是負數" };
    }
    if (!Number.isFinite(years) || years <= 0) {
      return { ok: false, error: "持有年數必須是大於 0 的數字" };
    }

    const toleratedDropAmount = dividend * years;
    const breakevenPrice = buyPrice - toleratedDropAmount;
    const returnRate = ((endPrice - buyPrice + toleratedDropAmount) / buyPrice) * 100;
    const toleratedDropPct = (toleratedDropAmount / buyPrice) * 100;

    return {
      ok: true,
      returnRate: round2(returnRate),
      breakevenPrice: round2(breakevenPrice),
      toleratedDropAmount: round2(toleratedDropAmount),
      toleratedDropPct: round2(toleratedDropPct),
      noDividendBuffer: dividend === 0,
    };
  }

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  return { calc };
})();

// 瀏覽器環境掛在 window 上供其他頁面直接使用;若未來改用模組化打包也可以匯出。
if (typeof window !== "undefined") {
  window.RiskCalc = RiskCalc;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = RiskCalc;
}
