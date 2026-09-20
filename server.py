"""ICCPP local server: public site + /admin panel."""
from __future__ import annotations

import csv
import hmac
import io
import json
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
)

ROOT = Path(__file__).resolve().parent
PACKAGED_DATA = ROOT / "data"
ADMIN = ROOT / "admin"
BLOCKED_PREFIXES = ("admin", "api", "data")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
INQUIRY_TYPES = {"newsletter", "internship", "contact", "feedback"}
INQUIRY_STATUSES = {"new", "read", "replied"}
MEMBER_GROUPS = {"management", "phd", "lecturers"}
PHOTO_RE = re.compile(r"^assets/photos/members/[A-Za-z0-9._-]+$")
COVER_RE = re.compile(r"^assets/photos/journals/[A-Za-z0-9._-]+$")
JOURNAL_FILE_RE = re.compile(r"^assets/journals/[A-Za-z0-9._-]+\.pdf$")
PROFILE_RE = re.compile(r"^members/[A-Za-z0-9._-]+\.html$")
UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PDF_TYPE = {".pdf": "application/pdf"}
UPLOAD_MAX = 2 * 1024 * 1024
PDF_MAX = 20 * 1024 * 1024
lock = threading.Lock()


def load_env() -> None:
    if os.environ.get("VERCEL"):
        return
    path = ROOT / ".env"
    if not path.exists():
        example = ROOT / ".env.example"
        if example.exists():
            path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env()

if os.environ.get("VERCEL"):
    DATA = Path("/tmp/iccpp-data")
    DATA.mkdir(parents=True, exist_ok=True)
else:
    DATA = PACKAGED_DATA

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL") or os.environ.get("PRODUCTION"))
if os.environ.get("VERCEL") or os.environ.get("PRODUCTION"):
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "iccpp-admin")


def data_path(name: str) -> Path:
    return DATA / name


def read_json(name: str, default):
    path = data_path(name)
    if not path.exists():
        seed = PACKAGED_DATA / name
        if seed.exists():
            with seed.open(encoding="utf-8") as handle:
                return json.load(handle)
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(name: str, payload) -> None:
    path = data_path(name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def clean_photo(value) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    return path if PHOTO_RE.match(path) else ""


def clean_profile(value) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    return path if PROFILE_RE.match(path) else ""


def clean_cover(value) -> str:
    path = str(value or "").replace("\\", "/").strip()
    if path.startswith("https://"):
        return path
    path = path.lstrip("/")
    return path if COVER_RE.match(path) else ""


def clean_journal_file(value) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    return path if JOURNAL_FILE_RE.match(path) else ""


def clean_http_url(value) -> str:
    url = str(value or "").strip()
    return url if url.startswith("https://") else ""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/admin/login.html")
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def guard_admin():
    path = request.path
    if path in ("/admin/login.html", "/admin/css/admin.css", "/admin/js/admin.js"):
        return None
    if path == "/api/admin/login" and request.method == "POST":
        return None
    if path.startswith("/api/admin") or path.startswith("/admin"):
        if not session.get("user"):
            if path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/admin/login.html")
    return None


# --- Public content APIs ---


@app.get("/api/content/news")
def public_news():
    items = [item for item in read_json("news.json", []) if item.get("published")]
    return jsonify(items)


@app.get("/api/content/members")
def public_members():
    data = read_json("members.json", {"leadership": [], "directory": [], "reviewers": []})
    return jsonify(
        {
            "leadership": [row for row in data.get("leadership", []) if row.get("visible", True)],
            "directory": [row for row in data.get("directory", []) if row.get("visible", True)],
            "reviewers": [row for row in data.get("reviewers", []) if row.get("visible", True)],
        }
    )


@app.get("/api/content/partners")
def public_partners():
    data = read_json("partners.json", {"featured": [], "directory": []})
    return jsonify(
        {
            "featured": [row for row in data.get("featured", []) if row.get("visible", True)],
            "directory": [row for row in data.get("directory", []) if row.get("visible", True)],
        }
    )


@app.get("/api/content/internships")
def public_internships():
    return jsonify(read_json("internships.json", {"open": True, "facts": [], "coursework": []}))


@app.get("/api/content/donate")
def public_donate():
    data = read_json("donate.json", {"paypalUrl": "https://www.paypal.com/donate"})
    url = str(data.get("paypalUrl") or "").strip()
    if not url.startswith("https://"):
        url = "https://www.paypal.com/donate"
    return jsonify({"paypalUrl": url})


@app.get("/api/content/journals")
def public_journals():
    data = read_json("journals.json", {"issues": []})
    issues = []
    for row in data.get("issues") or []:
        if not isinstance(row, dict) or not row.get("visible", True):
            continue
        item = {
            "id": row.get("id") or "",
            "number": row.get("number") or "",
            "label": row.get("label") or "",
            "url": clean_http_url(row.get("url")),
        }
        cover = clean_cover(row.get("cover"))
        if cover:
            item["cover"] = cover
        file_path = clean_journal_file(row.get("file"))
        if file_path:
            item["file"] = file_path
        issues.append(item)
    return jsonify({"issues": issues})


@app.post("/api/inquiries")
def create_inquiry():
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("type") or "").strip().lower()
    fields = payload.get("fields") or {}
    if kind not in INQUIRY_TYPES or not isinstance(fields, dict):
        return jsonify({"error": "Invalid inquiry."}), 400

    cleaned = {str(key): str(value).strip() for key, value in fields.items() if value is not None}
    email = cleaned.get("email", "")
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    if kind == "newsletter":
        required = ("first", "last", "email", "country")
    elif kind == "internship":
        required = ("name", "email", "status", "message")
    else:
        required = ("first", "last", "email", "message")

    missing = [key for key in required if not cleaned.get(key)]
    if missing:
        return jsonify({"error": "Please complete the required fields."}), 400

    record = {
        "id": new_id("inq"),
        "type": kind,
        "status": "new",
        "created": now_iso(),
        "fields": cleaned,
    }
    with lock:
        items = read_json("inquiries.json", [])
        items.insert(0, record)
        write_json("inquiries.json", items)
    return jsonify({"ok": True, "id": record["id"]})


# --- Admin APIs ---


@app.post("/api/admin/login")
def admin_login():
    payload = request.get_json(silent=True) or {}
    user = str(payload.get("user") or "")
    password = str(payload.get("password") or "")
    user_ok = hmac.compare_digest(user.encode("utf-8"), ADMIN_USER.encode("utf-8")) if len(user) == len(ADMIN_USER) else False
    pass_ok = hmac.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")) if len(password) == len(ADMIN_PASSWORD) else False
    if user_ok and pass_ok:
        session["user"] = ADMIN_USER
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid username or password."}), 401


@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/admin/me")
@login_required
def admin_me():
    return jsonify({"user": session.get("user")})


@app.get("/api/admin/stats")
@login_required
def admin_stats():
    items = read_json("inquiries.json", [])
    counts = {kind: 0 for kind in INQUIRY_TYPES}
    new_count = 0
    for item in items:
        kind = item.get("type")
        if kind in counts:
            counts[kind] += 1
        if item.get("status") == "new":
            new_count += 1
    return jsonify({"total": len(items), "new": new_count, "byType": counts, "recent": items[:8]})


@app.get("/api/admin/inquiries")
@login_required
def admin_inquiries():
    items = read_json("inquiries.json", [])
    kind = request.args.get("type", "").strip().lower()
    status = request.args.get("status", "").strip().lower()
    query = request.args.get("q", "").strip().lower()
    if kind in INQUIRY_TYPES:
        items = [item for item in items if item.get("type") == kind]
    if status in INQUIRY_STATUSES:
        items = [item for item in items if item.get("status") == status]
    if query:
        items = [item for item in items if query in json.dumps(item.get("fields", {}), ensure_ascii=False).lower()]
    return jsonify(items)


@app.patch("/api/admin/inquiries/<item_id>")
@login_required
def admin_inquiry_update(item_id: str):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").strip().lower()
    if status not in INQUIRY_STATUSES:
        return jsonify({"error": "Invalid status."}), 400
    with lock:
        items = read_json("inquiries.json", [])
        found = None
        for item in items:
            if item.get("id") == item_id:
                item["status"] = status
                found = item
                break
        if not found:
            return jsonify({"error": "Not found."}), 404
        write_json("inquiries.json", items)
    return jsonify(found)


@app.delete("/api/admin/inquiries/<item_id>")
@login_required
def admin_inquiry_delete(item_id: str):
    with lock:
        items = read_json("inquiries.json", [])
        next_items = [item for item in items if item.get("id") != item_id]
        if len(next_items) == len(items):
            return jsonify({"error": "Not found."}), 404
        write_json("inquiries.json", next_items)
    return jsonify({"ok": True})


@app.get("/api/admin/inquiries.csv")
@login_required
def admin_inquiries_csv():
    items = read_json("inquiries.json", [])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "type", "status", "created", "name", "email", "country", "status_field", "message"])
    for item in items:
        fields = item.get("fields") or {}
        name = fields.get("name") or " ".join(part for part in (fields.get("first"), fields.get("last")) if part)
        writer.writerow(
            [
                item.get("id"),
                item.get("type"),
                item.get("status"),
                item.get("created"),
                name,
                fields.get("email", ""),
                fields.get("country", ""),
                fields.get("status", ""),
                fields.get("message", ""),
            ]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=iccpp-inquiries.csv"},
    )


@app.get("/api/admin/news")
@login_required
def admin_news_get():
    return jsonify(read_json("news.json", []))


@app.put("/api/admin/news")
@login_required
def admin_news_put():
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        return jsonify({"error": "Expected a list of news items."}), 400
    cleaned = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or []
        if isinstance(body, str):
            body = [part.strip() for part in body.split("\n\n") if part.strip()]
        cleaned.append(
            {
                "id": item.get("id") or new_id("n"),
                "date": str(item.get("date") or "").strip(),
                "kicker": str(item.get("kicker") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "body": [str(part).strip() for part in body if str(part).strip()],
                "email": str(item.get("email") or "").strip(),
                "published": bool(item.get("published")),
            }
        )
    write_json("news.json", cleaned)
    return jsonify(cleaned)


@app.get("/api/admin/members")
@login_required
def admin_members_get():
    return jsonify(read_json("members.json", {"leadership": [], "directory": [], "reviewers": []}))


@app.put("/api/admin/members")
@login_required
def admin_members_put():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected members object."}), 400
    leadership = []
    for row in payload.get("leadership") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        item = {
            "id": row.get("id") or new_id("l"),
            "name": str(row.get("name")).strip(),
            "initials": str(row.get("initials") or "").strip()[:3],
            "bio": str(row.get("bio") or "").strip(),
            "email": str(row.get("email") or "").strip(),
            "alt": bool(row.get("alt")),
            "visible": bool(row.get("visible", True)),
        }
        photo = clean_photo(row.get("photo"))
        if photo:
            item["photo"] = photo
        profile = clean_profile(row.get("profile"))
        if profile:
            item["profile"] = profile
        leadership.append(item)
    directory = []
    for row in payload.get("directory") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        group = str(row.get("group") or "lecturers")
        if group not in MEMBER_GROUPS:
            group = "lecturers"
        item = {
            "id": row.get("id") or new_id("d"),
            "name": str(row.get("name")).strip(),
            "role": str(row.get("role") or "").strip(),
            "group": group,
            "visible": bool(row.get("visible", True)),
        }
        photo = clean_photo(row.get("photo"))
        if photo:
            item["photo"] = photo
        profile = clean_profile(row.get("profile"))
        if profile:
            item["profile"] = profile
        directory.append(item)
    reviewers = []
    for row in payload.get("reviewers") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        reviewers.append(
            {
                "id": row.get("id") or new_id("r"),
                "name": str(row.get("name")).strip(),
                "bio": str(row.get("bio") or "").strip(),
                "visible": bool(row.get("visible", True)),
            }
        )
    data = {"leadership": leadership, "directory": directory, "reviewers": reviewers}
    write_json("members.json", data)
    return jsonify(data)


@app.post("/api/admin/upload")
@login_required
def admin_upload():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Please choose a file."}), 400
    kind = str(request.form.get("kind") or "photo").strip().lower()
    ext = Path(uploaded.filename).suffix.lower()
    if kind == "journal-file":
        if ext not in PDF_TYPE:
            return jsonify({"error": "Please upload a PDF."}), 400
        data = uploaded.read(PDF_MAX + 1)
        if len(data) > PDF_MAX:
            return jsonify({"error": "PDF must be 20 MB or smaller."}), 400
        if not data:
            return jsonify({"error": "Please choose a PDF."}), 400
        filename = f"{new_id('jf')}.pdf"
        dest_dir = ROOT / "assets" / "journals"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / filename).write_bytes(data)
        return jsonify({"path": f"assets/journals/{filename}"})
    if ext not in UPLOAD_TYPES:
        return jsonify({"error": "Please upload a JPG, PNG, or WebP image."}), 400
    data = uploaded.read(UPLOAD_MAX + 1)
    if len(data) > UPLOAD_MAX:
        return jsonify({"error": "Image must be 2 MB or smaller."}), 400
    if not data:
        return jsonify({"error": "Please choose an image."}), 400
    filename = f"{new_id('p')}{'.jpg' if ext == '.jpeg' else ext}"
    if kind == "journal-cover":
        dest_dir = ROOT / "assets" / "photos" / "journals"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / filename).write_bytes(data)
        return jsonify({"path": f"assets/photos/journals/{filename}"})
    dest_dir = ROOT / "assets" / "photos" / "members"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(data)
    return jsonify({"path": f"assets/photos/members/{filename}"})


@app.get("/api/admin/partners")
@login_required
def admin_partners_get():
    return jsonify(read_json("partners.json", {"featured": [], "directory": []}))


@app.put("/api/admin/partners")
@login_required
def admin_partners_put():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected partners object."}), 400
    featured = []
    for row in payload.get("featured") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        featured.append(
            {
                "id": row.get("id") or new_id("f"),
                "name": str(row.get("name")).strip(),
                "blurb": str(row.get("blurb") or "").strip(),
                "visible": bool(row.get("visible", True)),
            }
        )
    directory = []
    for row in payload.get("directory") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        directory.append(
            {
                "id": row.get("id") or new_id("p"),
                "name": str(row.get("name")).strip(),
                "visible": bool(row.get("visible", True)),
            }
        )
    data = {"featured": featured, "directory": directory}
    write_json("partners.json", data)
    return jsonify(data)


@app.get("/api/admin/internships")
@login_required
def admin_internships_get():
    return jsonify(read_json("internships.json", {"open": True, "facts": [], "coursework": []}))


@app.put("/api/admin/internships")
@login_required
def admin_internships_put():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected internships object."}), 400
    facts = []
    for row in payload.get("facts") or []:
        if isinstance(row, dict) and (row.get("value") or row.get("label")):
            facts.append({"value": str(row.get("value") or "").strip(), "label": str(row.get("label") or "").strip()})
    coursework = []
    raw = payload.get("coursework") or []
    if isinstance(raw, str):
        raw = [line.strip() for line in raw.splitlines()]
    for line in raw:
        text = str(line).strip()
        if text:
            coursework.append(text)
    data = {"open": bool(payload.get("open")), "facts": facts, "coursework": coursework}
    write_json("internships.json", data)
    return jsonify(data)


@app.get("/api/admin/journals")
@login_required
def admin_journals_get():
    return jsonify(read_json("journals.json", {"issues": []}))


@app.put("/api/admin/journals")
@login_required
def admin_journals_put():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected journals object."}), 400
    issues = []
    for row in payload.get("issues") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        number = str(row.get("number") or "").strip()
        if not label and not number:
            continue
        item = {
            "id": row.get("id") or new_id("j"),
            "number": number,
            "label": label or f"Nr. {number}",
            "url": clean_http_url(row.get("url")),
            "visible": bool(row.get("visible", True)),
        }
        cover = clean_cover(row.get("cover"))
        if cover:
            item["cover"] = cover
        file_path = clean_journal_file(row.get("file"))
        if file_path:
            item["file"] = file_path
        issues.append(item)
    data = {"issues": issues}
    write_json("journals.json", data)
    return jsonify(data)


# --- Pages ---


@app.get("/admin")
@app.get("/admin/")
@login_required
def admin_index():
    return send_from_directory(ADMIN, "index.html")


@app.get("/admin/<path:filename>")
def admin_file(filename: str):
    return send_from_directory(ADMIN, filename)


@app.get("/")
def root():
    return send_from_directory(ROOT, "index.html")


@app.get("/<path:path>")
def public_file(path: str):
    first = path.split("/", 1)[0]
    if first in BLOCKED_PREFIXES or path.startswith(".") or ".." in path:
        return ("Not found", 404)
    target = ROOT / path
    if not target.resolve().is_relative_to(ROOT.resolve()):
        return ("Not found", 404)
    if target.is_file():
        return send_from_directory(ROOT, path)
    if (ROOT / path / "index.html").is_file():
        return send_from_directory(ROOT / path, "index.html")
    return ("Not found", 404)


@app.after_request
def no_store_api(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", "8000"))
    print(f"ICCPP site:  http://127.0.0.1:{port}/")
    print(f"Admin panel: http://127.0.0.1:{port}/admin")
    print(f"Login: {ADMIN_USER} / (password from .env)")
    app.run(host="127.0.0.1", port=port, debug=False)
