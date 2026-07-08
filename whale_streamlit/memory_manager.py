import sqlite3
import os
import threading
from datetime import datetime

# On Streamlit Cloud the filesystem is ephemeral; for local use this persists.
# Override path via env var: WHALE_DB_PATH=/persistent/path/whale_vault.db
DB_PATH = os.environ.get(
    "WHALE_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "whale_vault.db"),
)

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    creator     TEXT    NOT NULL,
    asset_type  TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    source_url  TEXT,
    file_path   TEXT,
    ig_url      TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""
# asset_type : 'photo' | 'video'
# status     : 'approved_photo' | 'pending_video' | 'approved_video'
#              'scrubbing' | 'scrubbed'


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock:
        with _conn() as c:
            c.executescript(_SCHEMA)


def save_asset(creator, asset_type, status,
               source_url=None, file_path=None, ig_url=None) -> int:
    now = datetime.utcnow().isoformat()
    with _lock:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO assets "
                "(creator, asset_type, status, source_url, file_path, ig_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (creator, asset_type, status, source_url, file_path, ig_url, now, now),
            )
            return cur.lastrowid


def get_all_assets(status=None, asset_type=None) -> list[dict]:
    with _lock:
        with _conn() as c:
            q, p = "SELECT * FROM assets WHERE 1=1", []
            if status:
                q += " AND status=?"; p.append(status)
            if asset_type:
                q += " AND asset_type=?"; p.append(asset_type)
            q += " ORDER BY created_at DESC"
            return [dict(r) for r in c.execute(q, p).fetchall()]


def update_asset_status(asset_id: int, status: str, file_path=None):
    now = datetime.utcnow().isoformat()
    with _lock:
        with _conn() as c:
            if file_path is not None:
                c.execute(
                    "UPDATE assets SET status=?, file_path=?, updated_at=? WHERE id=?",
                    (status, file_path, now, asset_id),
                )
            else:
                c.execute(
                    "UPDATE assets SET status=?, updated_at=? WHERE id=?",
                    (status, now, asset_id),
                )


def purge_asset(asset_id: int):
    with _lock:
        with _conn() as c:
            row = c.execute(
                "SELECT file_path FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
            if row and row["file_path"]:
                try:
                    if os.path.exists(row["file_path"]):
                        os.remove(row["file_path"])
                except OSError:
                    pass
            c.execute("DELETE FROM assets WHERE id=?", (asset_id,))


def get_asset(asset_id: int) -> dict | None:
    with _lock:
        with _conn() as c:
            row = c.execute(
                "SELECT * FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
            return dict(row) if row else None
