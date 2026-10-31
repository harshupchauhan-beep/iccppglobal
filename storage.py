"""JSON documents and uploaded files.

Uses Postgres when DATABASE_URL is set so Vercel instances share one store.
Otherwise reads and writes files on disk.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT: Path | None = None
DATA: Path | None = None
PACKAGED: Path | None = None

_conn = None
_db_error = ""
_file_lock = threading.Lock()


def configure(root: Path, data: Path, packaged: Path) -> None:
    global ROOT, DATA, PACKAGED
    ROOT = root
    DATA = data
    PACKAGED = packaged


def database_url() -> str:
    return str(os.environ.get("DATABASE_URL") or "").strip()


def db_error() -> str:
    return _db_error


def using_postgres() -> bool:
    return db_conn() is not None


def db_conn():
    global _conn, _db_error
    url = database_url()
    if not url:
        return None
    if _conn is not None and not _conn.closed:
        return _conn
    try:
        import psycopg
    except ImportError as exc:
        _db_error = "psycopg is not installed."
        raise RuntimeError(_db_error) from exc
    try:
        _conn = psycopg.connect(url, autocommit=True)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iccpp_documents (
                name TEXT PRIMARY KEY,
                body JSONB NOT NULL
            )
            """
        )
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iccpp_files (
                path TEXT PRIMARY KEY,
                content BYTEA NOT NULL,
                content_type TEXT NOT NULL
            )
            """
        )
        _db_error = ""
        return _conn
    except Exception as exc:
        _conn = None
        _db_error = str(exc)
        return None


class StoreLock:
    """Serialize document updates on this process and, with Postgres, across instances."""

    def __enter__(self):
        _file_lock.acquire()
        self._conn = db_conn()
        if self._conn is not None:
            self._conn.execute("SELECT pg_advisory_lock(874213)")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.execute("SELECT pg_advisory_unlock(874213)")
        finally:
            _file_lock.release()
        return False


def _seed(name: str):
    if PACKAGED is None:
        return None
    path = PACKAGED / name
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_json(name: str, default):
    conn = db_conn()
    if conn is not None:
        row = conn.execute("SELECT body FROM iccpp_documents WHERE name = %s", (name,)).fetchone()
        if row is not None:
            return row[0]
        seeded = _seed(name)
        if seeded is not None:
            write_json(name, seeded)
            return seeded
        return default
    if DATA is None:
        return default
    path = DATA / name
    if not path.exists():
        seeded = _seed(name)
        return seeded if seeded is not None else default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(name: str, payload) -> None:
    conn = db_conn()
    if conn is not None:
        from psycopg.types.json import Json

        conn.execute(
            """
            INSERT INTO iccpp_documents (name, body) VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body
            """,
            (name, Json(payload)),
        )
        return
    if DATA is None:
        raise RuntimeError("Storage is not configured.")
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def save_blob(rel_path: str, data: bytes, content_type: str) -> None:
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    conn = db_conn()
    if conn is not None:
        conn.execute(
            """
            INSERT INTO iccpp_files (path, content, content_type) VALUES (%s, %s, %s)
            ON CONFLICT (path) DO UPDATE SET content = EXCLUDED.content, content_type = EXCLUDED.content_type
            """,
            (rel_path, data, content_type),
        )
        return
    if DATA is None:
        raise RuntimeError("Storage is not configured.")
    dest = DATA / "blobs" / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def open_blob(rel_path: str) -> tuple[bytes, str] | None:
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    conn = db_conn()
    if conn is not None:
        row = conn.execute(
            "SELECT content, content_type FROM iccpp_files WHERE path = %s",
            (rel_path,),
        ).fetchone()
        if row is not None:
            content = bytes(row[0]) if not isinstance(row[0], bytes) else row[0]
            return content, row[1]
    if DATA is not None:
        path = DATA / "blobs" / rel_path
        if path.is_file():
            kind = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
            return path.read_bytes(), kind
    return None
