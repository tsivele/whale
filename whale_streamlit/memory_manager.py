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
# pipeline_items.status flow (review-based â€” nothing advances without user action):
#   downloaded â†’ swapping â†’ pending_photo_review
#   pending_photo_review â†’ (Approve) â†’ approved_photo â†’ generating â†’ generated_pending_scrub
#   pending_photo_review â†’ (Recreate) â†’ swapping
#   generated_pending_scrub â†’ (Send to Scrub) â†’ scrubbing â†’ scrubbed
#   generated_pending_scrub â†’ (Recreate Video) â†’ generating
#   any â†’ error â†’ (Retry) â†’ back to appropriate stage


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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Pipeline Items â€” 4-tab pipeline tracking
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_pipeline_item(ig_url: str, creator: str) -> int:
    now = datetime.utcnow().isoformat()
    with _lock:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO pipeline_items (ig_url, creator, status, created_at, updated_at) "
                "VALUES (?, ?, 'downloaded', ?, ?)",
                (ig_url, creator, now, now),
            )
            return cur.lastrowid


def get_pipeline_items(status=None, creator=None) -> list[dict]:
    with _lock:
        with _conn() as c:
            q, p = "SELECT * FROM pipeline_items WHERE 1=1", []
            if status is not None:
                if isinstance(status, (list, tuple)):
                    q += f" AND status IN ({','.join('?'*len(status))})"
                    p.extend(status)
                else:
                    q += " AND status=?"; p.append(status)
            if creator:
                q += " AND creator=?"; p.append(creator)
            q += " ORDER BY created_at ASC"
            return [dict(r) for r in c.execute(q, p).fetchall()]


def get_pipeline_item(item_id: int) -> "dict | None":
    with _lock:
        with _conn() as c:
            row = c.execute(
                "SELECT * FROM pipeline_items WHERE id=?", (item_id,)
            ).fetchone()
            return dict(row) if row else None


def update_pipeline_item(item_id: int, **kwargs):
    if not kwargs:
        return
    now = datetime.utcnow().isoformat()
    kwargs["updated_at"] = now
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [item_id]
    with _lock:
        with _conn() as c:
            c.execute(f"UPDATE pipeline_items SET {cols} WHERE id=?", vals)


def claim_pipeline_item(item_id: int, from_status: str, to_status: str) -> bool:
    """Atomic compare-and-swap status transition.

    Returns True only if the item was in `from_status` and is now `to_status`.
    This is the double-submit lock: two clicks (or two tabs) racing on the
    same item â€” only ONE claim succeeds, the other gets False and must not
    call any paid API.
    """
    now = datetime.utcnow().isoformat()
    with _lock:
        with _conn() as c:
            cur = c.execute(
                "UPDATE pipeline_items SET status=?, updated_at=? "
                "WHERE id=? AND status=?",
                (to_status, now, item_id, from_status),
            )
            return cur.rowcount == 1


def delete_pipeline_item(item_id: int):
    """Purge: delete DB row + remove local files not shared with other items."""
    with _lock:
        with _conn() as c:
            row = c.execute(
                "SELECT video_path, frame_path, gen_path, scrubbed_path "
                "FROM pipeline_items WHERE id=?",
                (item_id,),
            ).fetchone()
            c.execute("DELETE FROM pipeline_items WHERE id=?", (item_id,))
            if row:
                for fld in ("video_path", "frame_path", "gen_path", "scrubbed_path"):
                    fp = row[fld]
                    if not fp:
                        continue
                    # SOFIA+MELINA items share video/frame files â€” only remove
                    # from disk when no surviving row still references the path
                    still_used = c.execute(
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


def get_active_preds() -> list[dict]:
    """Items with status 'swapping' or 'generating' that have a pred_id saved."""
    with _lock:
        with _conn() as c:
            rows = c.execute(
                "SELECT id, status, faceswap_pred, gen_pred FROM pipeline_items "
                "WHERE status IN ('swapping','generating')"
            ).fetchall()
            return [dict(r) for r in rows]
