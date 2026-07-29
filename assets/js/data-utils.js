// 共用的資料讀取小工具:抓 JSON、統一錯誤/空資料訊息呈現方式。
const DataUtils = (() => {
  async function fetchJSON(path) {
    const resp = await fetch(path, { cache: "no-store" });
    if (!resp.ok) {
      throw new Error(`讀取 ${path} 失敗(HTTP ${resp.status})`);
    }
    return resp.json();
  }

  function showState(container, message) {
    container.innerHTML = `<div class="state-message">${escapeHTML(message)}</div>`;
  }

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function marketLabel(market) {
    return market === "otc" ? "上櫃" : market === "tse" ? "上市" : market || "";
  }

  return { fetchJSON, showState, escapeHTML, marketLabel };
})();
