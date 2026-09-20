(() => {
  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const loadJson = async (path) => {
    const res = await fetch(path);
    if (!res.ok) throw new Error("Could not load content.");
    return res.json();
  };

  const renderNews = async () => {
    const panel = document.querySelector("[data-content=news]");
    if (!panel) return;
    try {
      const items = await loadJson("/api/content/news");
      const item = items[0];
      if (!item) {
        panel.innerHTML = "<p>No news is published at the moment.</p>";
        return;
      }
      const body = (item.body || []).map((para) => `<p>${escapeHtml(para)}</p>`).join("");
      const email = item.email
        ? `<p>Enquiries: <a href="mailto:${escapeHtml(item.email)}">${escapeHtml(item.email)}</a></p>`
        : "";
      panel.innerHTML = `
        <p class="news-meta">${escapeHtml(item.date || "")}${item.kicker ? ` · ${escapeHtml(item.kicker)}` : ""}</p>
        <h3>${escapeHtml(item.title || "")}</h3>
        ${body}
        ${email}`;
    } catch {
      /* keep static fallback */
    }
  };

  const renderMembers = async () => {
    const lead = document.querySelector("[data-content=leadership]");
    const groups = {
      management: document.querySelector("[data-content=members-management]"),
      phd: document.querySelector("[data-content=members-phd]"),
      lecturers: document.querySelector("[data-content=members-lecturers]"),
    };
    const reviewers = document.querySelector("[data-content=reviewers]");
    if (!lead && !reviewers && !Object.values(groups).some(Boolean)) return;
    try {
      const data = await loadJson("/api/content/members");
      const avatar = (row) => {
        if (row.photo) {
          return `<div class="avatar has-photo"><img src="${escapeHtml(row.photo)}" alt=""></div>`;
        }
        return `<div class="avatar${row.alt ? " alt" : ""}" aria-hidden="true">${escapeHtml(row.initials || "")}</div>`;
      };
      const personName = (row) =>
        row.profile
          ? `<a href="${escapeHtml(row.profile)}">${escapeHtml(row.name)}</a>`
          : escapeHtml(row.name);
      if (lead) {
        lead.innerHTML = (data.leadership || [])
          .map(
            (row) => `<article class="card member">
              ${avatar(row)}
              <div>
                <h3>${personName(row)}</h3>
                <p>${escapeHtml(row.bio || "")}</p>
                ${row.email ? `<p><a href="mailto:${escapeHtml(row.email)}">${escapeHtml(row.email)}</a></p>` : ""}
              </div>
            </article>`
          )
          .join("");
      }
      Object.entries(groups).forEach(([group, node]) => {
        if (!node) return;
        node.innerHTML = (data.directory || [])
          .filter((row) => row.group === group)
          .map((row) => {
            const media = row.photo
              ? `<img class="person-photo" src="${escapeHtml(row.photo)}" alt="">`
              : `<span class="person-fallback" aria-hidden="true">${escapeHtml((row.name || "?").replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase() || "?")}</span>`;
            return `<div class="person-chip">${media}<div><strong>${personName(row)}</strong><span>${escapeHtml(row.role || "")}</span></div></div>`;
          })
          .join("");
      });
      if (reviewers) {
        reviewers.innerHTML = (data.reviewers || [])
          .map((row) => `<article class="card"><h3>${escapeHtml(row.name)}</h3><p>${escapeHtml(row.bio || "")}</p></article>`)
          .join("");
      }
      document.getElementById("member-search")?.dispatchEvent(new Event("input"));
    } catch {
      /* keep static fallback */
    }
  };

  const renderPartners = async () => {
    const featured = document.querySelector("[data-content=partners-featured]");
    const directory = document.querySelector("[data-content=partners-directory]");
    if (!featured && !directory) return;
    try {
      const data = await loadJson("/api/content/partners");
      if (featured) {
        featured.innerHTML = (data.featured || [])
          .map((row) => `<article class="card"><h3>${escapeHtml(row.name)}</h3><p>${escapeHtml(row.blurb || "")}</p></article>`)
          .join("");
      }
      if (directory) {
        directory.innerHTML = (data.directory || [])
          .map((row) => `<div class="partner-chip">${escapeHtml(row.name)}</div>`)
          .join("");
      }
      document.getElementById("partner-search")?.dispatchEvent(new Event("input"));
    } catch {
      /* keep static fallback */
    }
  };

  const renderInternships = async () => {
    const facts = document.querySelector("[data-content=internship-facts]");
    const course = document.querySelector("[data-content=internship-coursework]");
    const formWrap = document.querySelector("[data-content=internship-form]");
    if (!facts && !course && !formWrap) return;
    try {
      const data = await loadJson("/api/content/internships");
      if (facts) {
        facts.innerHTML = (data.facts || [])
          .map((row) => `<div class="fact"><b>${escapeHtml(row.value)}</b><span>${escapeHtml(row.label)}</span></div>`)
          .join("");
      }
      if (course) {
        course.innerHTML = (data.coursework || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      }
      if (formWrap) {
        const form = formWrap.querySelector("form");
        const closed = formWrap.querySelector("[data-closed]");
        if (data.open) {
          if (form) form.hidden = false;
          if (closed) closed.hidden = true;
        } else {
          if (form) form.hidden = true;
          if (closed) closed.hidden = false;
        }
      }
    } catch {
      /* keep static fallback */
    }
  };

  const renderJournals = async () => {
    const grid = document.querySelector("[data-content=journal-issues]");
    if (!grid) return;
    try {
      const data = await loadJson("/api/content/journals");
      const issues = data.issues || [];
      if (!issues.length) return;
      grid.innerHTML = issues
        .map((row) => {
          const href = row.file || row.url || "#";
          const external = !row.file;
          const extra = external ? ` target="_blank" rel="noopener noreferrer"` : "";
          const img = row.cover
            ? `<img src="${escapeHtml(row.cover)}" alt="">`
            : `<span class="issue-fallback">${escapeHtml(row.number || "")}</span>`;
          return `<a class="issue-card" href="${escapeHtml(href)}"${extra}>${img}<b>${escapeHtml(row.label || "")}</b></a>`;
        })
        .join("");
    } catch {
      /* keep static fallback */
    }
  };

  const bindDonate = async () => {
    const btn = document.getElementById("donate-btn");
    if (!btn) return;
    try {
      const data = await loadJson("/api/content/donate");
      const url = String(data.paypalUrl || "").trim();
      if (url) btn.href = url;
    } catch {
      /* keep static fallback */
    }
  };

  renderNews();
  renderMembers();
  renderPartners();
  renderInternships();
  renderJournals();
  bindDonate();
})();
