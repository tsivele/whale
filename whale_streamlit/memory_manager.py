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

-- PERMANENT MONEY LEDGER — one row per PAID WaveSpeed call (photo swap or
-- video generation). Rows are NEVER deleted: WaveSpeed charges the moment a
-- job is dispatched, so purging the pipeline item must not erase the spend.
-- `pred_id` (the WaveSpeed prediction id) is UNIQUE → replays/backfills can
-- INSERT OR IGNORE without ever double-counting the same call.
CREATE TABLE IF NOT EXISTS spend_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pred_id     TEXT    UNIQUE,
    item_id     INTEGER,
    kind        TEXT    NOT NULL DEFAULT 'video',   -- 'photo' | 'video'
    model_key   TEXT,
    amount      REAL    NOT NULL DEFAULT 0,
    is_real     INTEGER NOT NULL DEFAULT 0,         -- 1 = price reported by WaveSpeed
    created_at  TEXT    NOT NULL
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
            # Migrations for older DBs
            _cols = {r[1] for r in conn.execute(
                "PRAGMA table_info(pipeline_items)").fetchall()}
            if "gen_cost" not in _cols:
                conn.execute("ALTER TABLE pipeline_items ADD COLUMN gen_cost REAL")
            if "drive_path" not in _cols:      # Drive folder a scrubbed clip was distributed to
                conn.execute("ALTER TABLE pipeline_items ADD COLUMN drive_path TEXT")
            # MULTI-FRAME REFERENCES — Seedance locks identity far better with
            # 3-4 swapped face/scene refs than with a single frame. These hold
            # the JSON lists; the legacy single-value columns (frame_path,
            # faceswap_url, faceswap_pred) keep holding the ANCHOR, so every
            # existing reader keeps working unchanged.
            for _c, _t in (("frame_paths",    "TEXT"),      # JSON [paths] extracted
                           ("faceswap_preds", "TEXT"),      # JSON [pred ids] in flight
                           ("faceswap_urls",  "TEXT"),      # JSON [swapped image urls]
                           ("ref_video_path", "TEXT"),      # 2nd source video (extra refs)
                           ("ingest_meta",    "TEXT"),      # JSON counters for the job report
                           # LAYERED FACE SWAP — each layer re-swaps the PREVIOUS
                           # approved output, so the identity gets stronger with
                           # every pass. swap_layer = how many are approved so far.
                           ("swap_layer",     "INTEGER DEFAULT 0"),
                           ("target_layers",  "INTEGER DEFAULT 4"),
                           ("layer_urls",     "TEXT")):     # JSON [url per approved layer]
                if _c not in _cols:
                    conn.execute(f"ALTER TABLE pipeline_items ADD COLUMN {_c} {_t}")
            # BACKFILL: older DBs tracked spend only on the pipeline row, so
            # anything already dispatched must be lifted into the permanent
            # ledger. UNIQUE(pred_id) + INSERT OR IGNORE makes this idempotent —
            # it can run on every boot and never double-counts.
            _now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO spend_ledger "
                "(pred_id, item_id, kind, model_key, amount, is_real, created_at) "
                "SELECT gen_pred, id, 'video', COALESCE(model_key,?), "
                "       COALESCE(gen_cost,?), 0, COALESCE(created_at,?) "
                "FROM pipeline_items WHERE gen_pred IS NOT NULL AND gen_pred<>''",
                (DEFAULT_VIDEO_MODEL, DEFAULT_VIDEO_COST, _now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO spend_ledger "
                "(pred_id, item_id, kind, model_key, amount, is_real, created_at) "
                "SELECT faceswap_pred, id, 'photo', 'faceswap', ?, 0, "
                "       COALESCE(created_at,?) "
                "FROM pipeline_items WHERE faceswap_pred IS NOT NULL AND faceswap_pred<>''",
                (DEFAULT_PHOTO_COST, _now),
            )
            conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Spend ledger (permanent — survives purge/delete of the pipeline item)
# ─────────────────────────────────────────────────────────────────────────────
# WaveSpeed bills at DISPATCH, not at download. Deleting a photo or a video
# gives no money back, so the ledger is written the moment a paid call leaves
# the app and is never touched by delete_pipeline_item().

# Fallbacks used only by the backfill above (app passes real numbers at runtime).
DEFAULT_PHOTO_COST  = 0.03
DEFAULT_VIDEO_COST  = 1.50
DEFAULT_VIDEO_MODEL = "seedance"


def record_spend(pred_id, item_id=None, kind="video", model_key=None,
                 amount=0.0, is_real=False) -> None:
    """Log one paid WaveSpeed call. Idempotent on pred_id (a retry of the same
    prediction never charges twice in the ledger)."""
    if not pred_id:
        return
    conn = _conn()
    try:
        with _lock:
            conn.execute(
                "INSERT OR IGNORE INTO spend_ledger "
                "(pred_id, item_id, kind, model_key, amount, is_real, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(pred_id), item_id, kind, model_key, float(amount or 0.0),
                 1 if is_real else 0, datetime.utcnow().isoformat()),
            )
            conn.commit()
    finally:
        conn.close()


def settle_spend(pred_id, amount, is_real=True) -> None:
    """Replace the estimate with the REAL price WaveSpeed reported for this
    prediction. No-op if the call was never recorded."""
    if not pred_id or amount is None:
        return
    conn = _conn()
    try:
        with _lock:
            conn.execute(
                "UPDATE spend_ledger SET amount=?, is_real=? WHERE pred_id=?",
                (float(amount), 1 if is_real else 0, str(pred_id)),
            )
            conn.commit()
    finally:
        conn.close()


def spend_summary() -> dict:
    """Everything ever spent — including photos and anything since deleted."""
    conn = _conn()
    try:
        with _lock:
            rows = conn.execute(
                "SELECT kind, COUNT(*) n, COALESCE(SUM(amount),0) total "
                "FROM spend_ledger GROUP BY kind"
            ).fetchall()
            _real = conn.execute(
                "SELECT COUNT(*) FROM spend_ledger WHERE is_real=1").fetchone()[0]
    finally:
        conn.close()
    out = {"total": 0.0, "photo": 0.0, "video": 0.0,
           "n_photo": 0, "n_video": 0, "n_real": _real}
    for r in rows:
        k = r["kind"] if r["kind"] in ("photo", "video") else "video"
        out[k] += float(r["total"])
        out["n_" + k] += int(r["n"])
        out["total"] += float(r["total"])
    out["total"] = round(out["total"], 2)
    out["photo"] = round(out["photo"], 2)
    out["video"] = round(out["video"], 2)
    return out


def total_spend() -> float:
    return spend_summary()["total"]


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

# ── JSON list columns (multi-frame refs) ─────────────────────────────────────
# Stored as JSON text so the schema stays one table and old rows (NULL) simply
# read back as an empty list.

def jlist(item, field) -> list:
    """Read a JSON-list column off an item dict → always a list."""
    import json as _json
    _v = (item or {}).get(field)
    if not _v:
        return []
    try:
        _p = _json.loads(_v)
        return list(_p) if isinstance(_p, (list, tuple)) else []
    except (ValueError, TypeError):
        return []


def jdump(values) -> str:
    """Serialize a list for a JSON-list column."""
    import json as _json
    return _json.dumps(list(values or []))


def find_item_by_url(ig_url: str):
    """Return the earliest existing pipeline item with this ig_url, or None.
    Used to keep only ONE item per video (no duplicates)."""
    if not ig_url:
        return None
    conn = _conn()
    try:
        with _lock:
            row = conn.execute(
                "SELECT * FROM pipeline_items WHERE ig_url=? ORDER BY id ASC LIMIT 1",
                (ig_url,),
            ).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def add_pipeline_item(ig_url: str, creator: str, status: str = "downloaded") -> int:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with _lock:
            cur = conn.execute(
                "INSERT INTO pipeline_items (ig_url, creator, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ig_url, creator, status, now, now),
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
    """Purge: delete DB row + remove local files not shared with other items.

    The spend_ledger is deliberately NOT touched: WaveSpeed charged the moment
    the job was dispatched, so a deleted photo/video still costs real money and
    must keep counting in the dashboard total."""
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
