(() => {
  const view = document.getElementById("view");
  const title = document.getElementById("title");
  const subtitle = document.getElementById("subtitle");
  const who = document.getElementById("who");

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const api = async (path, options = {}) => {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (res.status === 401) {
      location.replace("/admin/login.html");
      throw new Error("unauthorized");
    }
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || "Request failed.");
    return payload;
  };

  const setNav = (name) => {
    document.querySelectorAll("[data-nav]").forEach((link) => {
      link.classList.toggle("active", link.dataset.nav === name);
    });
  };

  const statusLine = (id, message, ok) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.className = `status ${ok ? "ok" : "error"}`;
  };

  const formatWhen = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString();
  };

  const personName = (fields = {}) =>
    fields.name || [fields.first, fields.last].filter(Boolean).join(" ") || "—";

  const renderDashboard = async () => {
    setNav("dashboard");
    title.textContent = "Dashboard";
    subtitle.textContent = "New messages and a snapshot of Centre content.";
    const stats = await api("/api/admin/stats");
    const rows = (stats.recent || [])
      .map(
        (item) => `<tr>
          <td><span class="badge ${item.status}">${escapeHtml(item.status)}</span></td>
          <td>${escapeHtml(item.type)}</td>
          <td>${escapeHtml(personName(item.fields))}</td>
          <td>${escapeHtml(item.fields?.email || "")}</td>
          <td>${escapeHtml(formatWhen(item.created))}</td>
        </tr>`
      )
      .join("");
    view.innerHTML = `
      <div class="stats">
        <div class="stat"><b>${stats.new}</b><span>New messages</span></div>
        <div class="stat"><b>${stats.byType?.internship || 0}</b><span>Internship applications</span></div>
        <div class="stat"><b>${stats.byType?.contact || 0}</b><span>Contact messages</span></div>
        <div class="stat"><b>${stats.byType?.newsletter || 0}</b><span>Newsletter sign-ups</span></div>
        <div class="stat"><b>${stats.byType?.paper || 0}</b><span>Paid paper submissions</span></div>
      </div>
      <div class="panel">
        <h2>Recent inbox</h2>
        <table>
          <thead><tr><th>Status</th><th>Type</th><th>Name</th><th>Email</th><th>Received</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="5">No submissions yet.</td></tr>`}</tbody>
        </table>
        <p><a class="btn" href="#/inbox">Open inbox</a></p>
      </div>`;
  };

  const inquiryDetail = (item) => {
    const fields = item.fields || {};
    const lines = Object.entries(fields)
      .map(([key, value]) => {
        const text = String(value || "");
        const safe = escapeHtml(text);
        if (key === "file" && /^assets\/papers\/[A-Za-z0-9._-]+\.pdf$/.test(text)) {
          return `<p><strong>${escapeHtml(key)}:</strong> <a href="/${safe}" target="_blank" rel="noopener noreferrer">${safe}</a></p>`;
        }
        return `<p><strong>${escapeHtml(key)}:</strong> ${safe}</p>`;
      })
      .join("");
    return `
      <div class="panel detail" data-detail="${escapeHtml(item.id)}">
        <p><span class="badge ${item.status}">${escapeHtml(item.status)}</span> ${escapeHtml(item.type)} · ${escapeHtml(formatWhen(item.created))}</p>
        ${lines}
        <div class="row-actions">
          <button class="btn btn-small" data-status="read">Mark read</button>
          <button class="btn btn-small" data-status="replied">Mark replied</button>
          <button class="btn btn-small btn-ghost" data-status="new">Mark new</button>
          <button class="btn btn-small btn-ghost" data-delete>Delete</button>
        </div>
      </div>`;
  };

  const renderInbox = async () => {
    setNav("inbox");
    title.textContent = "Inbox";
    subtitle.textContent = "Internship applications, contact messages, paper submissions, and newsletter sign-ups.";
    view.innerHTML = `
      <div class="toolbar">
        <select id="filter-type">
          <option value="">All types</option>
          <option value="internship">Internship</option>
          <option value="contact">Contact</option>
          <option value="feedback">Feedback</option>
          <option value="paper">Paper</option>
          <option value="newsletter">Newsletter</option>
        </select>
        <select id="filter-status">
          <option value="">All statuses</option>
          <option value="new">New</option>
          <option value="read">Read</option>
          <option value="replied">Replied</option>
        </select>
        <input id="filter-q" type="search" placeholder="Search name, email, message">
        <a class="btn btn-ghost" href="/api/admin/inquiries.csv">Export CSV</a>
      </div>
      <div id="inbox-list"></div>`;

    const list = document.getElementById("inbox-list");
    const load = async () => {
      const params = new URLSearchParams();
      const type = document.getElementById("filter-type").value;
      const status = document.getElementById("filter-status").value;
      const q = document.getElementById("filter-q").value.trim();
      if (type) params.set("type", type);
      if (status) params.set("status", status);
      if (q) params.set("q", q);
      const items = await api(`/api/admin/inquiries?${params}`);
      list.innerHTML = items.length
        ? items.map(inquiryDetail).join("")
        : `<div class="panel"><p>No matching submissions.</p></div>`;
    };

    view.querySelector(".toolbar").addEventListener("change", load);
    document.getElementById("filter-q").addEventListener("input", () => {
      clearTimeout(renderInbox.timer);
      renderInbox.timer = setTimeout(load, 200);
    });
    list.addEventListener("click", async (event) => {
      const detail = event.target.closest("[data-detail]");
      if (!detail) return;
      const id = detail.dataset.detail;
      try {
        if (event.target.matches("[data-delete]")) {
          if (!confirm("Delete this submission?")) return;
          await api(`/api/admin/inquiries/${id}`, { method: "DELETE" });
        } else if (event.target.dataset.status) {
          await api(`/api/admin/inquiries/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: event.target.dataset.status }),
          });
        } else {
          return;
        }
        await load();
      } catch (err) {
        alert(err.message);
      }
    });
    await load();
  };

  const newsCard = (item = {}, index) => `
    <div class="panel" data-news="${index}">
      <div class="grid-2">
        <label class="field">Date <input name="date" value="${escapeHtml(item.date || "")}"></label>
        <label class="field">Kicker <input name="kicker" value="${escapeHtml(item.kicker || "")}"></label>
      </div>
      <label class="field">Title <input name="title" value="${escapeHtml(item.title || "")}"></label>
      <label class="field">Body (blank line between paragraphs)
        <textarea name="body" rows="6">${escapeHtml((item.body || []).join("\n\n"))}</textarea>
      </label>
      <label class="field">Enquiry email <input name="email" value="${escapeHtml(item.email || "")}"></label>
      <label class="check"><input type="checkbox" name="published" ${item.published ? "checked" : ""}> Published on homepage</label>
      <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
      <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
    </div>`;

  const collectNews = () =>
    [...view.querySelectorAll("[data-news]")].map((card) => ({
      id: card.querySelector("[name=id]").value,
      date: card.querySelector("[name=date]").value,
      kicker: card.querySelector("[name=kicker]").value,
      title: card.querySelector("[name=title]").value,
      body: card.querySelector("[name=body]").value,
      email: card.querySelector("[name=email]").value,
      published: card.querySelector("[name=published]").checked,
    }));

  const renderNews = async () => {
    setNav("news");
    title.textContent = "Homepage news";
    subtitle.textContent = "The first published item appears in the Leadership of the Centre panel.";
    const items = await api("/api/admin/news");
    view.innerHTML = `
      <div id="news-list">${items.map(newsCard).join("") || newsCard({}, 0)}</div>
      <div class="row-actions">
        <button class="btn btn-ghost" type="button" id="add-news">Add news item</button>
        <button class="btn" type="button" id="save-news">Save news</button>
      </div>
      <p class="status" id="news-status"></p>`;
    document.getElementById("add-news").addEventListener("click", () => {
      document.getElementById("news-list").insertAdjacentHTML("beforeend", newsCard({}, view.querySelectorAll("[data-news]").length));
    });
    view.addEventListener("click", (event) => {
      if (event.target.matches("[data-remove]")) event.target.closest("[data-news]").remove();
    });
    document.getElementById("save-news").addEventListener("click", async () => {
      try {
        await api("/api/admin/news", { method: "PUT", body: JSON.stringify(collectNews()) });
        statusLine("news-status", "News saved. Refresh the homepage to see published items.", true);
      } catch (err) {
        statusLine("news-status", err.message, false);
      }
    });
  };

  const photoField = (item = {}) => `
    <div class="photo-field">
      <input type="hidden" name="photo" value="${escapeHtml(item.photo || "")}">
      <label class="field">Photo
        <input type="file" name="photo-file" accept="image/jpeg,image/png,image/webp">
      </label>
      <img class="photo-preview" alt="" ${item.photo ? `src="/${escapeHtml(item.photo)}"` : "hidden"}>
      <p class="photo-status"></p>
    </div>`;

  const memberRow = (item = {}, kind) => {
    if (kind === "leadership") {
      return `<div class="panel" data-row="leadership">
        <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
        <input type="hidden" name="profile" value="${escapeHtml(item.profile || "")}">
        <div class="grid-2">
          <label class="field">Name <input name="name" value="${escapeHtml(item.name || "")}"></label>
          <label class="field">Initials <input name="initials" maxlength="3" value="${escapeHtml(item.initials || "")}"></label>
        </div>
        <label class="field">Biography <textarea name="bio" rows="3">${escapeHtml(item.bio || "")}</textarea></label>
        <label class="field">Email <input name="email" value="${escapeHtml(item.email || "")}"></label>
        ${photoField(item)}
        <label class="check"><input type="checkbox" name="alt" ${item.alt ? "checked" : ""}> Alternate avatar colour</label>
        <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
        <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
      </div>`;
    }
    if (kind === "directory") {
      return `<div class="panel" data-row="directory">
        <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
        <input type="hidden" name="profile" value="${escapeHtml(item.profile || "")}">
        <div class="grid-2">
          <label class="field">Name <input name="name" value="${escapeHtml(item.name || "")}"></label>
          <label class="field">Group
            <select name="group">
              <option value="management" ${item.group === "management" ? "selected" : ""}>Management</option>
              <option value="phd" ${item.group === "phd" ? "selected" : ""}>PhD students</option>
              <option value="lecturers" ${item.group === "lecturers" || !item.group ? "selected" : ""}>Lecturers</option>
            </select>
          </label>
        </div>
        <label class="field">Role / country <input name="role" value="${escapeHtml(item.role || "")}"></label>
        ${photoField(item)}
        <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
        <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
      </div>`;
    }
    return `<div class="panel" data-row="reviewers">
      <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
      <label class="field">Name <input name="name" value="${escapeHtml(item.name || "")}"></label>
      <label class="field">Biography <textarea name="bio" rows="3">${escapeHtml(item.bio || "")}</textarea></label>
      <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
      <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
    </div>`;
  };

  const collectMembers = () => {
    const grab = (kind) =>
      [...view.querySelectorAll(`[data-row="${kind}"]`)].map((row) => {
        const data = { id: row.querySelector("[name=id]").value, name: row.querySelector("[name=name]").value, visible: row.querySelector("[name=visible]").checked };
        if (kind === "leadership") {
          data.initials = row.querySelector("[name=initials]").value;
          data.bio = row.querySelector("[name=bio]").value;
          data.email = row.querySelector("[name=email]").value;
          data.alt = row.querySelector("[name=alt]").checked;
          data.photo = row.querySelector("[name=photo]")?.value || "";
          data.profile = row.querySelector("[name=profile]")?.value || "";
        } else if (kind === "directory") {
          data.role = row.querySelector("[name=role]").value;
          data.group = row.querySelector("[name=group]").value;
          data.photo = row.querySelector("[name=photo]")?.value || "";
          data.profile = row.querySelector("[name=profile]")?.value || "";
        } else {
          data.bio = row.querySelector("[name=bio]").value;
        }
        return data;
      });
    return {
      leadership: grab("leadership"),
      directory: grab("directory"),
      reviewers: grab("reviewers"),
    };
  };

  const renderMembers = async () => {
    setNav("members");
    title.textContent = "Members";
    subtitle.textContent = "Leadership cards, directory chips, and journal reviewers.";
    const data = await api("/api/admin/members");
    view.innerHTML = `
      <h2>Leadership</h2>
      <div id="lead-list">${(data.leadership || []).map((row) => memberRow(row, "leadership")).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add="leadership">Add leader</button></p>
      <h2>Directory</h2>
      <div id="dir-list">${(data.directory || []).map((row) => memberRow(row, "directory")).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add="directory">Add directory member</button></p>
      <h2>Reviewers</h2>
      <div id="rev-list">${(data.reviewers || []).map((row) => memberRow(row, "reviewers")).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add="reviewers">Add reviewer</button></p>
      <p><button class="btn" type="button" id="save-members">Save members</button></p>
      <p class="status" id="members-status"></p>`;
    const lists = { leadership: "lead-list", directory: "dir-list", reviewers: "rev-list" };
    view.addEventListener("click", (event) => {
      if (event.target.matches("[data-remove]")) event.target.closest("[data-row]").remove();
      if (event.target.dataset.add) {
        document.getElementById(lists[event.target.dataset.add]).insertAdjacentHTML("beforeend", memberRow({}, event.target.dataset.add));
      }
    });
    document.getElementById("save-members").addEventListener("click", async () => {
      try {
        await api("/api/admin/members", { method: "PUT", body: JSON.stringify(collectMembers()) });
        statusLine("members-status", "Members saved. Refresh members.html to see the public page.", true);
      } catch (err) {
        statusLine("members-status", err.message, false);
      }
    });
    view.addEventListener("change", async (event) => {
      const input = event.target.closest("[name=photo-file]");
      if (!input || !input.files?.[0]) return;
      const row = input.closest("[data-row]");
      const status = row.querySelector(".photo-status");
      const preview = row.querySelector(".photo-preview");
      const hidden = row.querySelector("[name=photo]");
      const body = new FormData();
      body.append("file", input.files[0]);
      try {
        if (status) status.textContent = "Uploading…";
        const res = await fetch("/api/admin/upload", { method: "POST", body });
        if (res.status === 401) {
          location.replace("/admin/login.html");
          return;
        }
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.error || "Upload failed.");
        if (hidden) hidden.value = payload.path || "";
        if (preview && payload.path) {
          preview.src = `/${payload.path}`;
          preview.hidden = false;
        }
        if (status) status.textContent = "Photo ready. Save members to keep it.";
      } catch (err) {
        if (status) status.textContent = err.message;
      }
    });
  };

  const partnerRow = (item = {}, kind) => {
    if (kind === "featured") {
      return `<div class="panel" data-row="featured">
        <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
        <label class="field">Name <input name="name" value="${escapeHtml(item.name || "")}"></label>
        <label class="field">Blurb <textarea name="blurb" rows="2">${escapeHtml(item.blurb || "")}</textarea></label>
        <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
        <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
      </div>`;
    }
    return `<div class="panel" data-row="directory">
      <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
      <label class="field">Name <input name="name" value="${escapeHtml(item.name || "")}"></label>
      <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
      <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
    </div>`;
  };

  const collectPartners = () => ({
    featured: [...view.querySelectorAll("[data-row=featured]")].map((row) => ({
      id: row.querySelector("[name=id]").value,
      name: row.querySelector("[name=name]").value,
      blurb: row.querySelector("[name=blurb]").value,
      visible: row.querySelector("[name=visible]").checked,
    })),
    directory: [...view.querySelectorAll("[data-row=directory]")].map((row) => ({
      id: row.querySelector("[name=id]").value,
      name: row.querySelector("[name=name]").value,
      visible: row.querySelector("[name=visible]").checked,
    })),
  });

  const renderPartners = async () => {
    setNav("partners");
    title.textContent = "Partners";
    subtitle.textContent = "Featured collaborations and the searchable directory.";
    const data = await api("/api/admin/partners");
    view.innerHTML = `
      <h2>Featured</h2>
      <div id="feat-list">${(data.featured || []).map((row) => partnerRow(row, "featured")).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add="featured">Add featured partner</button></p>
      <h2>Directory</h2>
      <div id="pdir-list">${(data.directory || []).map((row) => partnerRow(row, "directory")).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add="directory">Add directory partner</button></p>
      <p><button class="btn" type="button" id="save-partners">Save partners</button></p>
      <p class="status" id="partners-status"></p>`;
    const lists = { featured: "feat-list", directory: "pdir-list" };
    view.addEventListener("click", (event) => {
      if (event.target.matches("[data-remove]")) event.target.closest("[data-row]").remove();
      if (event.target.dataset.add) {
        document.getElementById(lists[event.target.dataset.add]).insertAdjacentHTML("beforeend", partnerRow({}, event.target.dataset.add));
      }
    });
    document.getElementById("save-partners").addEventListener("click", async () => {
      try {
        await api("/api/admin/partners", { method: "PUT", body: JSON.stringify(collectPartners()) });
        statusLine("partners-status", "Partners saved. Refresh partners.html to see the public page.", true);
      } catch (err) {
        statusLine("partners-status", err.message, false);
      }
    });
  };

  const uploadAdminFile = async (file, kind) => {
    const body = new FormData();
    body.append("file", file);
    if (kind) body.append("kind", kind);
    const res = await fetch("/api/admin/upload", { method: "POST", body });
    if (res.status === 401) {
      location.replace("/admin/login.html");
      throw new Error("unauthorized");
    }
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || "Upload failed.");
    return payload;
  };

  const journalRow = (item = {}) => `<div class="panel" data-row="issue">
      <input type="hidden" name="id" value="${escapeHtml(item.id || "")}">
      <input type="hidden" name="cover" value="${escapeHtml(item.cover || "")}">
      <input type="hidden" name="file" value="${escapeHtml(item.file || "")}">
      <div class="grid-2">
        <label class="field">Number <input name="number" value="${escapeHtml(item.number || "")}" placeholder="10"></label>
        <label class="field">Label <input name="label" value="${escapeHtml(item.label || "")}" placeholder="Nr. 10 - January 2024"></label>
      </div>
      <label class="field">Read URL <input name="url" value="${escapeHtml(item.url || "")}" placeholder="https://www.iccpp.org/..."></label>
      <div class="photo-field">
        <label class="field">Cover image
          <input type="file" name="cover-file" accept="image/jpeg,image/png,image/webp">
        </label>
        <img class="photo-preview cover-preview" src="${item.cover ? escapeHtml(item.cover.startsWith("http") ? item.cover : `/${item.cover}`) : ""}" alt="" ${item.cover ? "" : "hidden"}>
        <p class="photo-status" data-status="cover">${item.cover ? "Cover on file." : ""}</p>
      </div>
      <div class="photo-field">
        <label class="field">Journal PDF
          <input type="file" name="pdf-file" accept="application/pdf">
        </label>
        <p class="photo-status" data-status="file">${item.file ? escapeHtml(item.file) : "Optional. If uploaded, the cover opens this PDF."}</p>
      </div>
      <label class="check"><input type="checkbox" name="visible" ${item.visible !== false ? "checked" : ""}> Visible</label>
      <button class="btn btn-ghost btn-small" type="button" data-remove>Remove</button>
    </div>`;

  const collectJournals = () => ({
    issues: [...view.querySelectorAll("[data-row=issue]")].map((row) => ({
      id: row.querySelector("[name=id]").value,
      number: row.querySelector("[name=number]").value,
      label: row.querySelector("[name=label]").value,
      url: row.querySelector("[name=url]").value,
      cover: row.querySelector("[name=cover]").value,
      file: row.querySelector("[name=file]").value,
      visible: row.querySelector("[name=visible]").checked,
    })),
  });

  const renderJournals = async () => {
    setNav("journals");
    title.textContent = "Journals";
    subtitle.textContent = "Issue covers, labels, and optional PDF uploads for the public journal page.";
    const data = await api("/api/admin/journals");
    view.innerHTML = `
      <div id="issue-list">${(data.issues || []).map((row) => journalRow(row)).join("")}</div>
      <p><button class="btn btn-ghost btn-small" type="button" data-add>Add issue</button></p>
      <p><button class="btn" type="button" id="save-journals">Save journals</button></p>
      <p class="status" id="journals-status"></p>`;
    view.addEventListener("click", (event) => {
      if (event.target.matches("[data-remove]")) event.target.closest("[data-row]").remove();
      if (event.target.matches("[data-add]")) {
        document.getElementById("issue-list").insertAdjacentHTML("afterbegin", journalRow({}));
      }
    });
    document.getElementById("save-journals").addEventListener("click", async () => {
      try {
        await api("/api/admin/journals", { method: "PUT", body: JSON.stringify(collectJournals()) });
        statusLine("journals-status", "Journals saved. Refresh journal.html to see the public page.", true);
      } catch (err) {
        statusLine("journals-status", err.message, false);
      }
    });
    view.addEventListener("change", async (event) => {
      const coverInput = event.target.closest("[name=cover-file]");
      const pdfInput = event.target.closest("[name=pdf-file]");
      const input = coverInput || pdfInput;
      if (!input || !input.files?.[0]) return;
      const row = input.closest("[data-row]");
      const kind = coverInput ? "journal-cover" : "journal-file";
      const status = row.querySelector(coverInput ? "[data-status=cover]" : "[data-status=file]");
      try {
        if (status) status.textContent = "Uploading…";
        const payload = await uploadAdminFile(input.files[0], kind);
        if (coverInput) {
          row.querySelector("[name=cover]").value = payload.path || "";
          const preview = row.querySelector(".cover-preview");
          if (preview && payload.path) {
            preview.src = `/${payload.path}`;
            preview.hidden = false;
          }
          if (status) status.textContent = "Cover ready. Save journals to keep it.";
        } else {
          row.querySelector("[name=file]").value = payload.path || "";
          if (status) status.textContent = payload.path || "PDF ready. Save journals to keep it.";
        }
      } catch (err) {
        if (status) status.textContent = err.message;
      }
    });
  };

  const renderInternships = async () => {
    setNav("internships");
    title.textContent = "Internships";
    subtitle.textContent = "Programme facts, coursework, and whether applications are open.";
    const data = await api("/api/admin/internships");
    const facts = (data.facts || []).concat([{ value: "", label: "" }, { value: "", label: "" }, { value: "", label: "" }]).slice(0, 3);
    view.innerHTML = `
      <div class="panel">
        <label class="check"><input type="checkbox" id="intern-open" ${data.open ? "checked" : ""}> Applications are open</label>
      </div>
      <div class="panel">
        <h2>Facts</h2>
        ${facts
          .map(
            (fact, i) => `<div class="grid-2">
              <label class="field">Value <input name="fact-value" data-i="${i}" value="${escapeHtml(fact.value || "")}"></label>
              <label class="field">Label <input name="fact-label" data-i="${i}" value="${escapeHtml(fact.label || "")}"></label>
            </div>`
          )
          .join("")}
      </div>
      <div class="panel">
        <label class="field">Coursework (one item per line)
          <textarea id="intern-course" rows="12">${escapeHtml((data.coursework || []).join("\n"))}</textarea>
        </label>
      </div>
      <p><button class="btn" type="button" id="save-intern">Save internships</button></p>
      <p class="status" id="intern-status"></p>`;
    document.getElementById("save-intern").addEventListener("click", async () => {
      const values = [...view.querySelectorAll("[name=fact-value]")];
      const labels = [...view.querySelectorAll("[name=fact-label]")];
      const payload = {
        open: document.getElementById("intern-open").checked,
        facts: values.map((input, i) => ({ value: input.value, label: labels[i].value })),
        coursework: document.getElementById("intern-course").value,
      };
      try {
        await api("/api/admin/internships", { method: "PUT", body: JSON.stringify(payload) });
        statusLine("intern-status", "Internship details saved. Refresh internships.html to see the public page.", true);
      } catch (err) {
        statusLine("intern-status", err.message, false);
      }
    });
  };

  const routes = {
    "": renderDashboard,
    inbox: renderInbox,
    news: renderNews,
    members: renderMembers,
    partners: renderPartners,
    internships: renderInternships,
    journals: renderJournals,
  };

  const route = async () => {
    const name = (location.hash.replace(/^#\/?/, "") || "").split("?")[0];
    const render = routes[name] || renderDashboard;
    view.innerHTML = `<div class="panel"><p>Loading…</p></div>`;
    try {
      await render();
    } catch (err) {
      if (err.message === "unauthorized") return;
      view.innerHTML = `<div class="panel"><p class="status error">${escapeHtml(err.message)}</p></div>`;
    }
  };

  document.getElementById("logout").addEventListener("click", async () => {
    await api("/api/admin/logout", { method: "POST" });
    location.replace("/admin/login.html");
  });

  api("/api/admin/me")
    .then((me) => {
      who.textContent = `Signed in as ${me.user}`;
      window.addEventListener("hashchange", route);
      route();
    })
    .catch(() => {});
})();
