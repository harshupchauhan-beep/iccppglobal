(() => {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".site-nav");
  const backdrop = document.querySelector(".nav-backdrop");

  const setOpen = (open) => {
    if (!nav || !toggle || !backdrop) return;
    nav.classList.toggle("open", open);
    backdrop.classList.toggle("open", open);
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };

  if (toggle && nav && backdrop) {
    toggle.addEventListener("click", () => setOpen(!nav.classList.contains("open")));
    backdrop.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setOpen(false);
    });
  }

  const isMobileNav = () => window.matchMedia("(max-width: 980px)").matches;

  const closeOpenSubs = (except) => {
    nav?.querySelectorAll(".has-sub.open").forEach((item) => {
      if (except && (item === except || item.contains(except) || except.contains(item))) return;
      item.classList.remove("open");
    });
  };

  nav?.querySelectorAll(".has-sub").forEach((item) => {
    let hideTimer;
    item.addEventListener("mouseenter", () => {
      if (isMobileNav()) return;
      clearTimeout(hideTimer);
      closeOpenSubs(item);
      item.classList.add("open");
    });
    item.addEventListener("mouseleave", () => {
      if (isMobileNav()) return;
      hideTimer = setTimeout(() => item.classList.remove("open"), 280);
    });
  });

  nav?.querySelectorAll(".has-sub > a").forEach((link) => {
    link.addEventListener("click", (event) => {
      const item = link.parentElement;
      if (isMobileNav()) {
        if (!item.classList.contains("open")) {
          event.preventDefault();
          item.classList.add("open");
        }
        return;
      }
      if (!item.classList.contains("open")) {
        event.preventDefault();
        closeOpenSubs(item);
        item.classList.add("open");
      }
    });
  });

  document.addEventListener("click", (event) => {
    if (nav && !nav.contains(event.target)) closeOpenSubs();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeOpenSubs();
  });

  const path = (location.pathname || "").replace(/\\/g, "/");
  const file = (path.split("/").pop() || "index.html").toLowerCase();
  const folder = path.split("/").slice(-2, -1)[0] || "";
  document.querySelectorAll(".site-nav a").forEach((link) => {
    const href = (link.getAttribute("href") || "").replace(/\\/g, "/").toLowerCase();
    const hrefFile = href.split("/").pop();
    const isHome = (file === "" || file === "index.html") && hrefFile === "index.html";
    const sameFile = hrefFile === file && file !== "index.html";
    const newsMatch = folder === "news" && hrefFile === "newsletters.html";
    const encMatch = folder === "encyclopedia" && hrefFile === "encyclopedia.html";
    const memberMatch = folder === "members" && hrefFile === "members.html";
    if (isHome || sameFile || newsMatch || encMatch || memberMatch) {
      link.setAttribute("aria-current", "page");
    }
  });

  const t = (en) =>
    window.ICCPP_I18N && typeof window.ICCPP_I18N.t === "function" ? window.ICCPP_I18N.t(en) : en;

  const emailOk = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

  document.querySelectorAll("form[data-validate]").forEach((form) => {
    const status = form.querySelector(".form-status");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const required = [...form.querySelectorAll("[required]")];
      const missing = required.filter((field) => {
        if (field.type === "checkbox") return !field.checked;
        return !String(field.value).trim();
      });
      const email = form.querySelector("input[type='email']");

      if (missing.length) {
        if (status) {
          status.textContent = t("Please complete the required fields.");
          status.className = "form-status error";
        }
        missing[0].focus();
        return;
      }

      if (email && !emailOk(email.value.trim())) {
        if (status) {
          status.textContent = t("Please enter a valid email address.");
          status.className = "form-status error";
        }
        email.focus();
        return;
      }

      const inquiryType = form.dataset.inquiry;
      if (inquiryType) {
        const fields = {};
        new FormData(form).forEach((value, key) => {
          if (key === "privacy") return;
          fields[key] = String(value).trim();
        });
        try {
          const res = await fetch("/api/inquiries", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ type: inquiryType, fields }),
          });
          const payload = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(payload.error || t("Could not send the form."));
        } catch (err) {
          if (status) {
            status.textContent = t(err.message || "Could not send the form.");
            status.className = "form-status error";
          }
          return;
        }
      }

      if (status) {
        status.textContent = t(form.dataset.success || "Thank you. Centre staff have received your message.");
        status.className = "form-status ok";
      }
      form.reset();
    });
  });

  const bindFilter = (inputId, itemSelector, emptyId) => {
    const search = document.querySelector(inputId);
    if (!search) return;
    const empty = document.querySelector(emptyId);
    const apply = () => {
      const items = [...document.querySelectorAll(itemSelector)];
      const q = search.value.trim().toLowerCase();
      let visible = 0;
      items.forEach((item) => {
        const match = item.textContent.toLowerCase().includes(q);
        item.hidden = !match;
        if (match) visible += 1;
      });
      if (empty) empty.hidden = visible > 0;
    };
    search.addEventListener("input", apply);
  };

  bindFilter("#partner-search", ".partner-chip", "#partner-empty");
  bindFilter("#member-search", ".person-chip", "#member-empty");
  bindFilter("#ency-search", ".entry-list li", "#ency-empty");

  const launch = document.getElementById("feedback-launch");
  const layer = document.getElementById("feedback-layer");
  const setFeedback = (open) => {
    if (!launch || !layer) return;
    layer.hidden = !open;
    document.body.classList.toggle("feedback-open", open);
    launch.setAttribute("aria-expanded", String(open));
    if (open) layer.querySelector("input, textarea")?.focus();
    else launch.focus();
  };
  launch?.addEventListener("click", () => setFeedback(true));
  layer?.querySelectorAll("[data-feedback-close]").forEach((el) => {
    el.addEventListener("click", () => setFeedback(false));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("feedback-open")) {
      setFeedback(false);
    }
  });

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reducedMotion) {
    const seen = new WeakSet();
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    const watchReveal = () => {
      document.querySelectorAll(".card, .issue-card, .section-head, .journal-strip, .hero-copy").forEach((el) => {
        if (seen.has(el) || el.classList.contains("is-visible")) return;
        seen.add(el);
        el.classList.add("reveal");
        io.observe(el);
      });
    };
    watchReveal();
    const main = document.querySelector("main");
    if (main) {
      new MutationObserver(watchReveal).observe(main, { childList: true, subtree: true });
    }
  }
})();
