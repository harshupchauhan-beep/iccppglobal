(() => {
  const form = document.getElementById("paper-form");
  const feeEl = document.getElementById("paper-fee");
  const status = document.getElementById("paper-status");
  const payBtn = document.getElementById("paper-pay");
  if (!form || !feeEl) return;

  const t = (en) =>
    window.ICCPP_I18N && typeof window.ICCPP_I18N.t === "function" ? window.ICCPP_I18N.t(en) : en;

  const setStatus = (text, kind) => {
    if (!status) return;
    status.textContent = text;
    status.className = kind ? `form-status ${kind}` : "form-status";
  };

  let config = { configured: false, amount: 0, currency: "INR", keyId: "", label: "" };

  const loadConfig = async () => {
    try {
      const res = await fetch("/api/payments/paper");
      config = await res.json();
      if (!config.configured) {
        feeEl.textContent = t("Paper payment is not configured yet. Please email iccppglobal@gmail.com.");
        if (payBtn) payBtn.disabled = true;
        return;
      }
      feeEl.textContent = `${t(config.label || "Article processing charge")}: ${config.amount} ${config.currency}`;
    } catch {
      feeEl.textContent = t("Could not load the payment fee.");
      if (payBtn) payBtn.disabled = true;
    }
  };

  const submitRecord = async (payment) => {
    const data = new FormData(form);
    data.set("razorpay_payment_id", payment.razorpay_payment_id);
    data.set("razorpay_order_id", payment.razorpay_order_id);
    data.set("razorpay_signature", payment.razorpay_signature);
    const res = await fetch("/api/payments/paper/submit", { method: "POST", body: data });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || t("Could not send the form."));
    return payload;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!config.configured) return;
    const name = form.name.value.trim();
    const email = form.email.value.trim();
    const title = form.title.value.trim();
    const abstract = form.abstract.value.trim();
    if (!name || !email || !title || !abstract) {
      setStatus(t("Please complete the required fields."), "error");
      return;
    }
    const file = form.file?.files?.[0];
    if (file && file.size > 4 * 1024 * 1024) {
      setStatus(
        t("PDF must be 4 MB or smaller on this form. Email the full file to iccppglobal@gmail.com with your payment id."),
        "error"
      );
      return;
    }
    if (payBtn) payBtn.disabled = true;
    setStatus(t("Starting payment…"));
    try {
      const orderRes = await fetch("/api/payments/paper/order", { method: "POST" });
      const order = await orderRes.json().catch(() => ({}));
      if (!orderRes.ok) throw new Error(order.error || t("Could not start payment."));
      if (typeof Razorpay !== "function") throw new Error(t("Could not load Razorpay checkout."));
      const checkout = new Razorpay({
        key: order.keyId || config.keyId,
        amount: order.amount * 100,
        currency: order.currency || config.currency,
        name: "ICCPP Journal",
        description: config.label || "Article processing charge",
        order_id: order.orderId,
        prefill: { name, email },
        handler: async (response) => {
          try {
            const saved = await submitRecord(response);
            const extra = saved.file
              ? t("Thank you. Centre staff have received your paid submission.")
              : t("Thank you. Centre staff have received your paid submission. Email the full PDF to iccppglobal@gmail.com with your payment id.");
            setStatus(extra, "ok");
            form.reset();
          } catch (err) {
            setStatus(t(err.message || "Could not send the form."), "error");
          } finally {
            if (payBtn) payBtn.disabled = false;
          }
        },
        modal: {
          ondismiss: () => {
            if (payBtn) payBtn.disabled = false;
            setStatus(t("Payment was cancelled."), "error");
          },
        },
      });
      checkout.open();
    } catch (err) {
      setStatus(t(err.message || "Could not start payment."), "error");
      if (payBtn) payBtn.disabled = false;
    }
  });

  loadConfig();
})();
