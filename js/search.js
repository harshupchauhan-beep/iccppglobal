(() => {
  const form = document.getElementById("site-search");
  const results = document.getElementById("search-results");
  if (!form || !results) return;
  const t = (en) =>
    window.ICCPP_I18N && typeof window.ICCPP_I18N.t === "function" ? window.ICCPP_I18N.t(en) : en;
  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const run = async (query) => {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const items = await res.json().catch(() => []);
    if (!items.length) {
      results.innerHTML = `<p>${escapeHtml(t("No pages matched that search."))}</p>`;
      return;
    }
    results.innerHTML = items
      .map(
        (item) => `<a class="search-hit" href="${escapeHtml(item.url)}">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.summary || "")}</span>
        </a>`
      )
      .join("");
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = form.q.value.trim();
    if (query.length < 2) return;
    const url = new URL(location.href);
    url.searchParams.set("q", query);
    history.replaceState(null, "", url);
    run(query);
  });

  const initial = new URL(location.href).searchParams.get("q");
  if (initial) {
    form.q.value = initial;
    run(initial);
  }
})();
