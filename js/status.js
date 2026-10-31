(() => {
  const form = document.getElementById("status-form");
  const status = document.getElementById("status-result");
  if (!form || !status) return;
  const t = (en) =>
    window.ICCPP_I18N && typeof window.ICCPP_I18N.t === "function" ? window.ICCPP_I18N.t(en) : en;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.className = "form-status";
    status.textContent = "";
    try {
      const res = await fetch("/api/payments/paper/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: form.id.value.trim(), email: form.email.value.trim() }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.error || t("No submission matches that reference and email."));
      status.className = "form-status ok";
      status.textContent = `${payload.title ? `${payload.title} — ` : ""}${t(payload.status || "Received")}`;
    } catch (err) {
      status.className = "form-status error";
      status.textContent = t(err.message || "No submission matches that reference and email.");
    }
  });
})();
