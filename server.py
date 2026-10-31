"""ICCPP local server: public site + /admin panel."""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
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
from storage import StoreLock, configure, db_error, open_blob, read_json, save_blob, using_postgres, write_json

ROOT = Path(__file__).resolve().parent
PACKAGED_DATA = ROOT / "data"
ADMIN = ROOT / "admin"
BLOCKED_PREFIXES = ("admin", "api", "data")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
INQUIRY_TYPES = {"newsletter", "internship", "contact", "feedback", "paper"}
PAPER_FILE_RE = re.compile(r"^assets/papers/[A-Za-z0-9._-]+\.pdf$")
PAPER_PDF_MAX = 4 * 1024 * 1024
INQUIRY_STATUSES = {"new", "read", "replied", "published"}
MEMBER_GROUPS = {"management", "phd", "lecturers"}
PHOTO_RE = re.compile(r"^assets/photos/members/[A-Za-z0-9._-]+$")
COVER_RE = re.compile(r"^assets/photos/journals/[A-Za-z0-9._-]+$")
JOURNAL_FILE_RE = re.compile(r"^assets/journals/[A-Za-z0-9._-]+\.pdf$")
PROFILE_RE = re.compile(r"^members/[A-Za-z0-9._-]+\.html$")
UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PDF_TYPE = {".pdf": "application/pdf"}
UPLOAD_MAX = 2 * 1024 * 1024
PDF_MAX = 20 * 1024 * 1024
DEFAULT_ADMIN_PASSWORD = "iccpp-admin"
RATE_LIMIT = 8


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

configure(ROOT, DATA, PACKAGED_DATA)
lock = StoreLock()

def production_mode() -> bool:
    return bool(os.environ.get("VERCEL") or os.environ.get("PRODUCTION"))


ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or ("" if production_mode() else DEFAULT_ADMIN_PASSWORD)


def session_secret() -> str:
    secret = str(os.environ.get("SECRET_KEY") or "").strip()
    if secret:
        return secret
    if production_mode() and ADMIN_PASSWORD and ADMIN_PASSWORD != DEFAULT_ADMIN_PASSWORD:
        return hashlib.sha256(f"iccpp-session:{ADMIN_PASSWORD}".encode()).hexdigest()
    return secrets.token_hex(32)


app = Flask(__name__, static_folder=None)
app.secret_key = session_secret()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL") or os.environ.get("PRODUCTION"))
if os.environ.get("VERCEL") or os.environ.get("PRODUCTION"):
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CANONICAL_HOST = os.environ.get("CANONICAL_HOST", "iccppglobal.com")


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


def clean_paper_file(value) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    return path if PAPER_FILE_RE.match(path) else ""


def clean_http_url(value) -> str:
    url = str(value or "").strip()
    return url if url.startswith("https://") else ""


def razorpay_keys() -> tuple[str, str]:
    """Razorpay keys from .env locally, or Vercel Environment Variables in production."""
    return str(os.environ.get("RAZORPAY_KEY_ID") or "").strip(), str(os.environ.get("RAZORPAY_KEY_SECRET") or "").strip()


def paper_fee() -> tuple[int, str, str]:
    data = read_json("payments.json", {"paperFeeInr": 5000, "currency": "INR", "label": "Article processing charge"})
    try:
        amount = int(data.get("paperFeeInr") or 5000)
    except (TypeError, ValueError):
        amount = 5000
    if amount < 1:
        amount = 5000
    currency = str(data.get("currency") or "INR").strip().upper() or "INR"
    label = str(data.get("label") or "Article processing charge").strip()
    return amount, currency, label


def razorpay_signature_ok(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def save_paper_pdf(uploaded) -> str:
    if uploaded is None or not uploaded.filename:
        return ""
    ext = Path(uploaded.filename).suffix.lower()
    if ext not in PDF_TYPE:
        raise ValueError("Please upload a PDF.")
    data = uploaded.read(PAPER_PDF_MAX + 1)
    if not data:
        return ""
    if len(data) > PAPER_PDF_MAX:
        raise ValueError("PDF must be 4 MB or smaller on this form. Email the full file to iccppglobal@gmail.com with your payment id.")
    filename = f"{new_id('paper')}.pdf"
    rel = f"assets/papers/{filename}"
    save_blob(rel, data, "application/pdf")
    return rel


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def client_ip() -> str:
    forwarded = str(request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or str(request.remote_addr or "")


def too_many_requests(ip: str) -> bool:
    if not ip:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = 0
    for name in ("inquiries.json", "drafts.json"):
        for item in read_json(name, []):
            if not isinstance(item, dict) or item.get("ip") != ip:
                continue
            try:
                created = datetime.strptime(str(item.get("created") or ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if created >= cutoff:
                recent += 1
    return recent >= RATE_LIMIT


def send_notice(to: str, subject: str, body: str) -> None:
    to = str(to or "").strip()
    if not to:
        return
    mail_from = str(os.environ.get("MAIL_FROM") or "ICCPP <onboarding@resend.dev>").strip()
    resend = str(os.environ.get("RESEND_API_KEY") or "").strip()
    try:
        if resend:
            payload = json.dumps({"from": mail_from, "to": [to], "subject": subject, "text": body}).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={"Authorization": f"Bearer {resend}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12):
                return
        host = str(os.environ.get("SMTP_HOST") or "").strip()
        if not host:
            return
        import smtplib
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        port = int(os.environ.get("SMTP_PORT") or "587")
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            user = str(os.environ.get("SMTP_USER") or "").strip()
            password = str(os.environ.get("SMTP_PASSWORD") or "").strip()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
    except (OSError, ValueError):
        return


def public_base() -> str:
    return str(request.host_url or "https://iccppglobal.com/").rstrip("/")


_HEADER = ""
_FOOTER = ""
_SEARCH = None


def chrome_parts() -> tuple[str, str]:
    global _HEADER, _FOOTER
    if not _HEADER:
        _HEADER = (ROOT / "partials" / "header.html").read_text(encoding="utf-8")
        _FOOTER = (ROOT / "partials" / "footer.html").read_text(encoding="utf-8")
    return _HEADER, _FOOTER


def lazy_images(html: str) -> str:
    def repl(match: re.Match) -> str:
        tag = match.group(0)
        if "loading=" in tag.lower():
            return tag
        if tag.endswith("/>"):
            return tag[:-2] + ' loading="lazy" decoding="async" />'
        return tag[:-1] + ' loading="lazy" decoding="async">'

    return re.sub(r"<img\b[^>]*>", repl, html, flags=re.IGNORECASE)


def decorate_html(raw: str, rel: str) -> str:
    prefix = "../" if "/" in rel else ""
    if 'class="site-header"' not in raw and "</main>" in raw:
        header, footer = chrome_parts()
        header = header.replace("__ROOT__", prefix)
        footer = footer.replace("__ROOT__", prefix)
        raw = raw.replace(
            '<a class="skip-link" href="#main">Skip to content</a>',
            '<a class="skip-link" href="#main">Skip to content</a>\n' + header,
            1,
        )
        raw = raw.replace("</main>", "</main>\n" + footer, 1)
    raw = lazy_images(raw)
    raw = re.sub(r"js/chrome\.js\?v=\d+", "js/chrome.js?v=20", raw)
    raw = re.sub(r"js/i18n\.js\?v=\d+", "js/i18n.js?v=14", raw)
    raw = re.sub(r"js/main\.js\?v=\d+", "js/main.js?v=13", raw)
    raw = re.sub(r"js/content\.js\?v=\d+", "js/content.js?v=14", raw)
    raw = re.sub(r"js/paper\.js\?v=\d+", "js/paper.js?v=2", raw)
    raw = re.sub(r"css/styles\.css\?v=\d+", "css/styles.css?v=22", raw)
    return raw


def send_html(rel: str):
    text = (ROOT / rel).read_text(encoding="utf-8")
    return Response(decorate_html(text, rel), mimetype="text/html; charset=utf-8")


def search_index() -> list:
    global _SEARCH
    if _SEARCH is not None:
        return _SEARCH
    items = []
    for path in ROOT.rglob("*.html"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("admin/", "partials/")):
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        title = re.search(r"<title>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
        desc = re.search(r'name="description"\s+content="(.*?)"', raw, flags=re.IGNORECASE | re.DOTALL)
        heading = re.search(r"<h1>(.*?)</h1>", raw, flags=re.IGNORECASE | re.DOTALL)

        def clean(value: str) -> str:
            text = re.sub(r"<[^>]+>", " ", value or "")
            return re.sub(r"\s+", " ", text).strip()

        items.append(
            {
                "url": "/" if rel == "index.html" else "/" + rel,
                "title": clean(title.group(1) if title else rel),
                "summary": clean(desc.group(1) if desc else (heading.group(1) if heading else "")),
            }
        )
    _SEARCH = items
    return items


def find_inquiry_by_payment(payment_id: str):
    for item in read_json("inquiries.json", []):
        if isinstance(item, dict) and (item.get("fields") or {}).get("payment_id") == payment_id:
            return item
    return None


def promote_draft(draft: dict, payment_id: str) -> dict:
    existing = find_inquiry_by_payment(payment_id)
    if existing:
        return existing
    fields = {
        "name": draft.get("name") or "",
        "email": draft.get("email") or "",
        "title": draft.get("title") or "",
        "abstract": draft.get("abstract") or "",
        "payment_id": payment_id,
        "order_id": draft.get("order_id") or "",
    }
    if draft.get("file"):
        fields["file"] = draft["file"]
    record = {
        "id": new_id("inq"),
        "type": "paper",
        "status": "new",
        "created": now_iso(),
        "ip": draft.get("ip") or "",
        "fields": fields,
    }
    items = read_json("inquiries.json", [])
    items.insert(0, record)
    write_json("inquiries.json", items)
    drafts = read_json("drafts.json", [])
    for row in drafts:
        if isinstance(row, dict) and row.get("id") == draft.get("id"):
            row["status"] = "paid"
            row["inquiry_id"] = record["id"]
    write_json("drafts.json", drafts)
    send_notice(
        fields["email"],
        "ICCPP received your paper",
        (
            f"Thank you. We received your paid submission “{fields['title']}”.\n"
            f"Reference: {record['id']}\n"
            f"Track the status: {public_base()}/paper-status.html\n"
        ),
    )
    return record


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
def force_apex_host():
    if not (os.environ.get("VERCEL") or os.environ.get("PRODUCTION")):
        return None
    host = (request.host or "").split(":")[0].lower()
    if host != f"www.{CANONICAL_HOST}":
        return None
    target = request.url.replace(f"://{host}", f"://{CANONICAL_HOST}", 1)
    return redirect(target, code=301)


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


@app.get("/api/payments/paper")
def public_paper_payment():
    amount, currency, label = paper_fee()
    key_id, secret = razorpay_keys()
    return jsonify(
        {
            "amount": amount,
            "currency": currency,
            "label": label,
            "keyId": key_id,
            "configured": bool(key_id and secret),
        }
    )


def start_razorpay_order(receipt: str, notes: dict) -> tuple[str, str]:
    key_id, secret = razorpay_keys()
    amount, currency, _label = paper_fee()
    payload = json.dumps(
        {
            "amount": amount * 100,
            "currency": currency,
            "receipt": receipt[:40],
            "payment_capture": 1,
            "notes": notes,
        }
    ).encode("utf-8")
    auth = base64.b64encode(f"{key_id}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        "https://api.razorpay.com/v1/orders",
        data=payload,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:240]
        return "", detail or "Could not start payment."
    except OSError:
        return "", "Could not reach Razorpay."
    return str(body.get("id") or ""), ""


@app.post("/api/payments/paper/order")
def create_paper_order():
    key_id, secret = razorpay_keys()
    if not key_id or not secret:
        return jsonify({"error": "Paper payment is not configured yet."}), 503
    amount, currency, _label = paper_fee()
    order_id, detail = start_razorpay_order(new_id("rcpt"), {"purpose": "paper"})
    if not order_id:
        return jsonify({"error": "Could not start payment.", "detail": detail}), 502
    return jsonify({"orderId": order_id, "amount": amount, "currency": currency, "keyId": key_id})


@app.post("/api/payments/paper/draft")
def create_paper_draft():
    key_id, secret = razorpay_keys()
    if not key_id or not secret:
        return jsonify({"error": "Paper payment is not configured yet."}), 503
    ip = client_ip()
    if too_many_requests(ip):
        return jsonify({"error": "Too many submissions from this network. Please try again later."}), 429
    form = request.form
    name = str(form.get("name") or "").strip()
    email = str(form.get("email") or "").strip()
    title = str(form.get("title") or "").strip()
    abstract = str(form.get("abstract") or "").strip()
    if not all((name, email, title, abstract)):
        return jsonify({"error": "Please complete the required fields."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    try:
        pdf_path = save_paper_pdf(request.files.get("file"))
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    draft_id = new_id("draft")
    order_id, detail = start_razorpay_order(draft_id, {"purpose": "paper", "draft_id": draft_id})
    if not order_id:
        return jsonify({"error": "Could not start payment.", "detail": detail}), 502
    draft = {
        "id": draft_id,
        "status": "pending",
        "created": now_iso(),
        "ip": ip,
        "name": name,
        "email": email,
        "title": title,
        "abstract": abstract,
        "order_id": order_id,
    }
    if pdf_path:
        draft["file"] = pdf_path
    with lock:
        drafts = read_json("drafts.json", [])
        drafts.insert(0, draft)
        write_json("drafts.json", drafts)
    amount, currency, _label = paper_fee()
    return jsonify({"orderId": order_id, "amount": amount, "currency": currency, "keyId": key_id, "draftId": draft_id})


@app.post("/api/payments/paper/submit")
def submit_paid_paper():
    key_id, secret = razorpay_keys()
    if not key_id or not secret:
        return jsonify({"error": "Paper payment is not configured yet."}), 503
    form = request.form
    name = str(form.get("name") or "").strip()
    email = str(form.get("email") or "").strip()
    title = str(form.get("title") or "").strip()
    abstract = str(form.get("abstract") or "").strip()
    order_id = str(form.get("razorpay_order_id") or "").strip()
    payment_id = str(form.get("razorpay_payment_id") or "").strip()
    signature = str(form.get("razorpay_signature") or "").strip()
    if not all((name, email, title, abstract, order_id, payment_id, signature)):
        return jsonify({"error": "Please complete the required fields and finish payment."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    if not razorpay_signature_ok(order_id, payment_id, signature, secret):
        return jsonify({"error": "Payment could not be verified."}), 400
    try:
        pdf_path = save_paper_pdf(request.files.get("file"))
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    fields = {
        "name": name,
        "email": email,
        "title": title,
        "abstract": abstract,
        "payment_id": payment_id,
        "order_id": order_id,
    }
    if pdf_path:
        fields["file"] = pdf_path
    with lock:
        existing = find_inquiry_by_payment(payment_id)
        if existing:
            return jsonify({"ok": True, "id": existing["id"], "file": (existing.get("fields") or {}).get("file") or ""})
        drafts = read_json("drafts.json", [])
        draft = next((row for row in drafts if isinstance(row, dict) and row.get("order_id") == order_id), None)
        if isinstance(draft, dict):
            draft["name"] = name
            draft["email"] = email
            draft["title"] = title
            draft["abstract"] = abstract
            if pdf_path:
                draft["file"] = pdf_path
            record = promote_draft(draft, payment_id)
            return jsonify({"ok": True, "id": record["id"], "file": (record.get("fields") or {}).get("file") or ""})
        record = {
            "id": new_id("inq"),
            "type": "paper",
            "status": "new",
            "created": now_iso(),
            "ip": client_ip(),
            "fields": fields,
        }
        items = read_json("inquiries.json", [])
        items.insert(0, record)
        write_json("inquiries.json", items)
    send_notice(
        email,
        "ICCPP received your paper",
        (
            f"Thank you. We received your paid submission “{title}”.\n"
            f"Reference: {record['id']}\n"
            f"Track the status: {public_base()}/paper-status.html\n"
        ),
    )
    return jsonify({"ok": True, "id": record["id"], "file": pdf_path})


@app.post("/api/payments/razorpay/webhook")
def razorpay_webhook():
    secret = str(os.environ.get("RAZORPAY_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return jsonify({"error": "Webhook secret is not configured."}), 503
    body = request.get_data() or b""
    signature = str(request.headers.get("X-Razorpay-Signature") or "")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return jsonify({"error": "Invalid signature."}), 400
    try:
        event = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid payload."}), 400
    if event.get("event") != "payment.captured":
        return jsonify({"ok": True})
    payment = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    payment_id = str(payment.get("id") or "")
    order_id = str(payment.get("order_id") or "")
    if not payment_id or not order_id:
        return jsonify({"ok": True})
    with lock:
        if find_inquiry_by_payment(payment_id):
            return jsonify({"ok": True})
        drafts = read_json("drafts.json", [])
        draft = next((row for row in drafts if isinstance(row, dict) and row.get("order_id") == order_id), None)
        if isinstance(draft, dict):
            promote_draft(draft, payment_id)
    return jsonify({"ok": True})


@app.post("/api/payments/paper/status")
def paper_status():
    payload = request.get_json(silent=True) or {}
    item_id = str(payload.get("id") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not item_id or not EMAIL_RE.match(email):
        return jsonify({"error": "Enter the reference and the email used on the form."}), 400
    labels = {"new": "Received", "read": "In review", "replied": "In review", "published": "Published"}
    for item in read_json("inquiries.json", []):
        if not isinstance(item, dict) or item.get("id") != item_id or item.get("type") != "paper":
            continue
        fields = item.get("fields") or {}
        if str(fields.get("email") or "").strip().lower() != email:
            break
        return jsonify({"ok": True, "status": labels.get(item.get("status"), "Received"), "title": fields.get("title") or ""})
    return jsonify({"error": "No submission matches that reference and email."}), 404


@app.get("/api/search")
def public_search():
    query = request.args.get("q", "").strip().lower()
    if len(query) < 2:
        return jsonify([])
    hits = []
    for item in search_index():
        if query in f"{item['title']} {item['summary']}".lower():
            hits.append(item)
        if len(hits) >= 20:
            break
    return jsonify(hits)


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


@app.get("/api/content/papers")
def public_papers():
    items = []
    for row in read_json("papers.json", []):
        if not isinstance(row, dict) or not row.get("visible", True):
            continue
        title = str(row.get("title") or "").strip()
        author = str(row.get("author") or "").strip()
        if not title or not author:
            continue
        item = {
            "id": row.get("id") or "",
            "title": title,
            "author": author,
            "abstract": str(row.get("abstract") or "").strip(),
            "published": str(row.get("published") or "").strip(),
        }
        file_path = clean_paper_file(row.get("file"))
        if file_path:
            item["file"] = file_path
        items.append(item)
    return jsonify(items)


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

    if kind == "paper":
        return jsonify({"error": "Please submit the paper through the journal payment form."}), 400
    if kind == "newsletter":
        required = ("first", "last", "email", "country")
    elif kind == "internship":
        required = ("name", "email", "status", "message")
    else:
        required = ("first", "last", "email", "message")

    missing = [key for key in required if not cleaned.get(key)]
    if missing:
        return jsonify({"error": "Please complete the required fields."}), 400

    ip = client_ip()
    if too_many_requests(ip):
        return jsonify({"error": "Too many submissions from this network. Please try again later."}), 429

    record = {
        "id": new_id("inq"),
        "type": kind,
        "status": "new",
        "created": now_iso(),
        "ip": ip,
        "fields": cleaned,
    }
    with lock:
        items = read_json("inquiries.json", [])
        items.insert(0, record)
        write_json("inquiries.json", items)
    kind_label = {"newsletter": "newsletter request", "internship": "internship application", "contact": "message", "feedback": "feedback"}.get(kind, "message")
    send_notice(
        email,
        f"ICCPP received your {kind_label}",
        f"Thank you. Centre staff have received your {kind_label}.\nReference: {record['id']}\n",
    )
    return jsonify({"ok": True, "id": record["id"]})


# --- Admin APIs ---


@app.post("/api/admin/login")
def admin_login():
    payload = request.get_json(silent=True) or {}
    user = str(payload.get("user") or "")
    password = str(payload.get("password") or "")
    if production_mode() and ADMIN_PASSWORD in ("", DEFAULT_ADMIN_PASSWORD):
        return jsonify({"error": "Set ADMIN_PASSWORD and SECRET_KEY in the hosting environment before signing in."}), 503
    if not ADMIN_PASSWORD:
        return jsonify({"error": "Set ADMIN_PASSWORD before signing in."}), 503
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
    return jsonify(
        {
            "total": len(items),
            "new": new_count,
            "byType": counts,
            "recent": items[:8],
            "storage": "postgres" if using_postgres() else "files",
            "storageError": db_error(),
            "production": production_mode(),
        }
    )


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


@app.post("/api/admin/inquiries/<item_id>/publish")
@login_required
def admin_inquiry_publish(item_id: str):
    with lock:
        items = read_json("inquiries.json", [])
        found = None
        for item in items:
            if item.get("id") == item_id:
                found = item
                break
        if not found:
            return jsonify({"error": "Not found."}), 404
        if found.get("type") != "paper":
            return jsonify({"error": "Only paid paper submissions can be published."}), 400
        fields = found.get("fields") or {}
        title = str(fields.get("title") or "").strip()
        author = str(fields.get("name") or "").strip()
        abstract = str(fields.get("abstract") or "").strip()
        if not title or not author:
            return jsonify({"error": "This submission is missing a title or author."}), 400
        papers = read_json("papers.json", [])
        if not isinstance(papers, list):
            papers = []
        for paper in papers:
            if isinstance(paper, dict) and paper.get("inquiryId") == item_id:
                found["status"] = "published"
                write_json("inquiries.json", items)
                return jsonify({"ok": True, "paper": paper, "inquiry": found})
        paper = {
            "id": new_id("paper"),
            "inquiryId": item_id,
            "title": title,
            "author": author,
            "abstract": abstract,
            "published": now_iso(),
            "visible": True,
        }
        file_path = clean_paper_file(fields.get("file"))
        if file_path:
            paper["file"] = file_path
        papers.insert(0, paper)
        write_json("papers.json", papers)
        found["status"] = "published"
        write_json("inquiries.json", items)
    return jsonify({"ok": True, "paper": paper, "inquiry": found})


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
        rel = f"assets/journals/{filename}"
        save_blob(rel, data, "application/pdf")
        return jsonify({"path": rel})
    if ext not in UPLOAD_TYPES:
        return jsonify({"error": "Please upload a JPG, PNG, or WebP image."}), 400
    data = uploaded.read(UPLOAD_MAX + 1)
    if len(data) > UPLOAD_MAX:
        return jsonify({"error": "Image must be 2 MB or smaller."}), 400
    if not data:
        return jsonify({"error": "Please choose an image."}), 400
    filename = f"{new_id('p')}{'.jpg' if ext == '.jpeg' else ext}"
    content_type = UPLOAD_TYPES[ext]
    if kind == "journal-cover":
        rel = f"assets/photos/journals/{filename}"
    else:
        rel = f"assets/photos/members/{filename}"
    save_blob(rel, data, content_type)
    return jsonify({"path": rel})


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
    return send_html("index.html")


@app.get("/<path:path>")
def public_file(path: str):
    first = path.split("/", 1)[0]
    if first in BLOCKED_PREFIXES or path.startswith(".") or ".." in path:
        return ("Not found", 404)
    target = ROOT / path
    if not target.resolve().is_relative_to(ROOT.resolve()):
        return ("Not found", 404)
    if target.is_file():
        if target.suffix.lower() == ".html":
            return send_html(target.relative_to(ROOT).as_posix())
        return send_from_directory(ROOT, path)
    blob = open_blob(path)
    if blob:
        return Response(blob[0], mimetype=blob[1])
    if (ROOT / path / "index.html").is_file():
        return send_html(f"{path}/index.html")
    return ("Not found", 404)


@app.after_request
def cache_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        return response
    ext = Path(request.path).suffix.lower()
    static = {".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".pdf", ".woff2"}
    if ext in static:
        if request.args.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400"
    elif ext == ".html" or request.path in ("/", ""):
        response.headers["Cache-Control"] = "public, max-age=120"
    return response


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", "8000"))
    print(f"ICCPP site:  http://127.0.0.1:{port}/")
    print(f"Admin panel: http://127.0.0.1:{port}/admin")
    print(f"Login: {ADMIN_USER} / (password from .env)")
    app.run(host="127.0.0.1", port=port, debug=False)
