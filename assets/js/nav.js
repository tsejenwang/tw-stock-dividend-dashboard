// 共用導覽列,三個頁面(排行榜/除權息日程/試算工具)都用同一份,
// 用 window.ACTIVE_PAGE 決定哪個連結要顯示成 active,避免三個 HTML 檔各自維護一份導覽列。
(function () {
  const PAGES = [
    { key: "rankings", href: "index.html", label: "殖利率排行榜" },
    { key: "etf", href: "etf.html", label: "ETF殖利率查詢" },
    { key: "calendar", href: "calendar.html", label: "除權息日程表" },
    { key: "calculators", href: "calculators.html", label: "合理價／風險試算" },
  ];

  function renderNav() {
    const active = window.ACTIVE_PAGE || "";
    const links = PAGES.map((p) => {
      const cls = "nav-link" + (p.key === active ? " active" : "");
      return `<a class="${cls}" href="${p.href}">${p.label}</a>`;
    }).join("");

    return `
      <header class="dashboard-header text-center">
        <div class="container">
          <h1>📊 台股資訊儀表板</h1>
          <p class="lead mb-0">殖利率排行・除權息日程・合理價與風險試算</p>
        </div>
      </header>
      <nav class="dashboard-nav">
        <div class="container d-flex flex-wrap gap-3 py-2 nav">
          ${links}
        </div>
      </nav>
    `;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const mount = document.getElementById("site-nav");
    if (mount) {
      mount.outerHTML = renderNav();
    }
  });
})();
