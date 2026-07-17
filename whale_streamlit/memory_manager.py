"""
memory_manager.py — SQLite persistence for the T-WHALES pipeline.

CONNECTION DISCIPLINE (critical):
    `with sqlite3.connect(...) as c:` only manages the TRANSACTION —
    it never closes the connection, which leaks handles and causes
    "database is locked" crashes on Streamlit Cloud.
    Therefore EVERY function here follows the strict pattern:

        conn = _conn()
        try:
            with _lock:
                ...
                conn.commit()
        finally:
            conn.close()

    Extra lock protection: connect(timeout=30) waits for a busy DB
    instead of raising instantly, and WAL journal mode lets readers
    and the writer coexist without blocking each other.
"""

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

CREATE TABLE IF NOT EXISTS pipeline_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ig_url          TEXT    NOT NULL,
    creator         TEXT    NOT NULL DEFAULT 'SOFIA',
    status          TEXT    NOT NULL DEFAULT 'downloaded',
    video_path      TEXT,
    frame_path      TEXT,
    faceswap_url    TEXT,
    faceswap_pred   TEXT,
    gen_url         TEXT,
    gen_pred        TEXT,
    gen_path        TEXT,
    scrubbed_path   TEXT,
    error_msg       TEXT,
    model_key       TEXT    DEFAULT 'seedance',
    prompt          TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""
# pipeline_items.status flow (review-based — nothing advances without user action):
#   downloaded → swapping → pending_photo_review
#   pending_photo_review → (Approve) → approved_photo → generating → generated_pending_scrub
#   pending_photo_review → (Recreate) → swapping
#   generated_pending_scrub → (Send to Scrub) → scrubbing → scrubbed
#   generated_pending_scrub → (Recreate Video) → generating
#   any → error → (Retry) → back to appropriate stage


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    conn = _conn()
    try:
        with _lock:
            conn.executescript(_SCHEMA)
            # WAL: readers never block the writer (poller thread vs UI thread)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            # Migration: add gen_cost (real WaveSpeed price) to older DBs
            _cols = {r[1] for r in conn.execute(
                "PRAGMA table_info(pipeline_items)").fetchall()}
            if "gen_cost" not in _cols:
                conn.execute("ALTER TABLE pipeline_items ADD COLUMN gen_cost REAL")
            conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Assets (legacy vault table)
# ─────────────────────────────────────────────────────────────────────────────

def save_asset(creator, asset_type, status,
               source_url=None, file_path=None, ig_url=None) -> int:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with _lock:
            cur = conn.execute(
                "INSERT INTO assets "
                "(creator, asset_type, status, source_url, file_path, ig_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (creator, asset_type, status, source_url, file_path, ig_url, now, now),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_all_assets(status=None, asset_type=None) -> list:
    conn = _conn()
    try:
        with _lock:
            q, p = "SELECT * FROM assets WHERE 1=1", []
            if status:
                q += " AND status=?"; p.append(status)
            if asset_type:
                q += " AND asset_type=?"; p.append(asset_type)
            q += " ORDER BY created_at DESC"
            return [dict(r) for r in conn.execute(q, p).fetchall()]
    finally:
        conn.close()


def update_asset_status(asset_id: int, status: str, file_path=None):
    now = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with _lock:
            c = conn.cursor()
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
            conn.commit()
    finally:
        conn.close()


def purge_asset(asset_id: int):
    conn = _conn()
    try:
        with _lock:
            row = conn.execute(
                "SELECT file_path FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
            if row and row["file_path"]:
                try:
                    if os.path.exists(row["file_path"]):
                        os.remove(row["file_path"])
                except OSError:
                    pass
            conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
            conn.commit()
    finally:
        conn.close()


def get_asset(asset_id: int):
    conn = _conn()
    try:
        with _lock:
            row = conn.execute(
                "SELECT * FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Items — 4-tab pipeline tracking
# ─────────────────────────────────────────────────────────────────────────────

def add_pipeline_item(ig_url: str, creator: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with _lock:
            cur = conn.execute(
                "INSERT INTO pipeline_items (ig_url, creator, status, created_at, updated_at) "
                "VALUES (?, ?, 'downloaded', ?, ?)",
                (ig_url, creator, now, now),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_pipeline_items(status=None, creator=None) -> list:
    conn = _conn()
    try:
        with _lock:
            q, p = "SELECT * FROM pipeline_items WHERE 1=1", []
            if status is not None:
                if isinstance(status, (list, tuple)):
                    q += " AND status IN ({})".format(",".join("?" * len(status)))
                    p.extend(status)
                else:
                    q += " AND status=?"; p.append(status)
            if creator:
                q += " AND creator=?"; p.append(creator)
            q += " ORDER BY created_at ASC"
            return [dict(r) for r in conn.execute(q, p).fetchall()]
    finally:
        conn.close()


def get_pipeline_item(item_id: int):
    conn = _conn()
    try:
        with _lock:
            row = conn.execute(
                "SELECT * FROM pipeline_items WHERE id=?", (item_id,)
            ).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def update_pipeline_item(item_id: int, **kwargs):
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join("{}=?".format(k) for k in kwargs)
    vals = list(kwargs.values()) + [item_id]
    conn = _conn()
    try:
        with _lock:
            conn.execute("UPDATE pipeline_items SET {} WHERE id=?".format(cols), vals)
            conn.commit()
    finally:
        conn.close()


def claim_pipeline_item(item_id: int, from_status: str, to_status: str) -> bool:
    """Atomic compare-and-swap status transition.

    Returns True only if the item was in `from_status` and is now `to_status`.
    This is the double-submit lock: two clicks (or two tabs) racing on the
    same item — only ONE claim succeeds, the other gets False and must not
    call any paid API.
    """
    now = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with _lock:
            cur = conn.execute(
                "UPDATE pipeline_items SET status=?, updated_at=? "
                "WHERE id=? AND status=?",
                (to_status, now, item_id, from_status),
            )
            conn.commit()
            return cur.rowcount == 1
    finally:
        conn.close()


def delete_pipeline_item(item_id: int):
    """Purge: delete DB row + remove local files not shared with other items."""
    conn = _conn()
    try:
        with _lock:
            row = conn.execute(
                "SELECT video_path, frame_path, gen_path, scrubbed_path "
                "FROM pipeline_items WHERE id=?",
                (item_id,),
            ).fetchone()
            conn.execute("DELETE FROM pipeline_items WHERE id=?", (item_id,))
            conn.commit()
            if row:
                for fld in ("video_path", "frame_path", "gen_path", "scrubbed_path"):
                    fp = row[fld]
                    if not fp:
                        continue
                    # SOFIA+MELINA items share video/frame files — only remove
                    # from disk when no surviving row still references the path
                    still_used = conn.execute(
                        "SELECT COUNT(*) FROM pipeline_items "
                        "WHERE video_path=? OR frame_path=? OR gen_path=? OR scrubbed_path=?",
                        (fp, fp, fp, fp),
                    ).fetchone()[0]
                    if still_used == 0:
                        try:
                            if os.path.exists(fp):
                                os.remove(fp)
                        except OSError:
                            pass
    finally:
        conn.close()


def get_active_preds() -> list:
    """Items with status 'swapping' or 'generating' that have a pred_id saved."""
    conn = _conn()
    try:
        with _lock:
            rows = conn.execute(
                "SELECT id, status, faceswap_pred, gen_pred FROM pipeline_items "
                "WHERE status IN ('swapping','generating')"
            ).fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()
