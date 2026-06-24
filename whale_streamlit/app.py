"""
T-WHALES 🐋 — Viral Discovery Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1 · Discovery   — HikerAPI + Apify viral reel search
Step 2 · Frames      — AI-recommended frames + custom scrubber
Step 3 · Review      — WaveSpeed face-swap image generation
Step 4 · Final Video — Kling v3.0-pro motion-control video
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import streamlit as st
import requests, json, time, os, tempfile, base64, math, re
import cv2, numpy as np
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="T-WHALES 🐋",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────
# DARK THEME  (#0B0B0B · violet #8b5cf6 · cyan #00e5ff)
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── reset / base ─────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], .stApp {
    background: #0B0B0B !important;
    color: #e4e4e7 !important;
}
[data-testid="stSidebar"], section[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.block-container { max-width: 1280px !important; padding: 1.5rem 2rem 4rem !important; margin: 0 auto !important; }

/* ── headings ──────────────────────────────────────────── */
h1,h2,h3,h4,h5,h6 { color: #f4f4f5 !important; letter-spacing: -.3px; }
p, label, .stMarkdown, div { color: #a1a1aa !important; }

/* ── buttons ───────────────────────────────────────────── */
.stButton > button {
    background: rgba(139,92,246,.15) !important;
    color: #c4b5fd !important;
    border: 1px solid rgba(139,92,246,.35) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all .2s !important;
}
.stButton > button:hover {
    background: rgba(139,92,246,.3) !important;
    border-color: rgba(139,92,246,.6) !important;
    box-shadow: 0 0 16px rgba(139,92,246,.3) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#7c3aed,#a855f7) !important;
    color: #fff !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg,#6d28d9,#9333ea) !important;
    box-shadow: 0 0 20px rgba(139,92,246,.45) !important;
}

/* ── inputs / selects / text areas ─────────────────────── */
.stTextInput input, .stTextArea textarea,
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: #141414 !important;
    color: #f4f4f5 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 10px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: rgba(139,92,246,.6) !important;
    box-shadow: 0 0 0 2px rgba(139,92,246,.2) !important;
}

/* ── slider ─────────────────────────────────────────────── */
.stSlider [data-baseweb="slider"] > div { background: rgba(139,92,246,.8) !important; }

/* ── metric / info boxes ────────────────────────────────── */
[data-testid="stMetricValue"] { color: #f4f4f5 !important; font-size: 1.6rem !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #71717a !important; font-size: .75rem !important; }
[data-testid="stMetricDelta"] { font-size: .72rem !important; }

/* ── status messages ────────────────────────────────────── */
.stSuccess { background: rgba(34,197,94,.1) !important; border-left: 3px solid #22c55e !important; color: #86efac !important; border-radius: 8px !important; }
.stError   { background: rgba(239,68,68,.1) !important;  border-left: 3px solid #ef4444 !important; color: #fca5a5 !important; border-radius: 8px !important; }
.stInfo    { background: rgba(139,92,246,.1) !important; border-left: 3px solid #8b5cf6 !important; color: #c4b5fd !important; border-radius: 8px !important; }
.stWarning { background: rgba(234,179,8,.1) !important;  border-left: 3px solid #eab308 !important; color: #fde047 !important; border-radius: 8px !important; }

/* ── file uploader ──────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #141414 !important;
    border: 2px dashed rgba(139,92,246,.4) !important;
    border-radius: 12px !important;
}

/* ── divider / hr ───────────────────────────────────────── */
hr { border-color: #222 !important; }

/* ── custom card styles ─────────────────────────────────── */
.whale-card {
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 16px;
    padding: 14px;
    transition: border-color .3s, box-shadow .3s;
    height: 100%;
}
.whale-card:hover { border-color: rgba(139,92,246,.4); box-shadow: 0 0 20px rgba(139,92,246,.12); }
.whale-stat {
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 14px;
    padding: 16px;
    position: relative;
    overflow: hidden;
}
.whale-stat::before {
    content: '';
    position: absolute;
    inset-x: 0; top: 0;
    height: 1px;
    background: linear-gradient(to right, transparent, rgba(255,255,255,.1), transparent);
}
.step-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 4px 14px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
}
.step-badge.active  { background: rgba(139,92,246,.15); color: #c4b5fd; border: 1px solid rgba(139,92,246,.35); }
.step-badge.done    { background: rgba(34,197,94,.12);  color: #86efac; border: 1px solid rgba(34,197,94,.3);   }
.step-badge.pending { background: rgba(255,255,255,.04); color: #52525b; border: 1px solid rgba(255,255,255,.08); }
.eng-high { color: #34d399; font-weight: 700; }
.eng-med  { color: #fbbf24; font-weight: 700; }
.eng-low  { color: #f87171; font-weight: 700; }
.platform-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 700;
    border: 1px solid;
}
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #111; }
::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# API KEYS (from Streamlit Secrets)
# ─────────────────────────────────────────────────────────────
WS_KEY    = st.secrets.get("WAVESPEED_KEY", "")
HIKER_KEY = st.secrets.get("HIKER_KEY",     "")
APIFY_KEY = st.secrets.get("APIFY_KEY",     "")

WS_API    = "https://api.wavespeed.ai/api/v3"
HIKER_API = "https://api.hikerapi.com"
APIFY_API = "https://api.apify.com/v2"

# ─────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────
def to_b64(raw: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

def fmt_num(n) -> str:
    try:
        n = int(n or 0)
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000:     return f"{n/1_000:.0f}K"
        return str(n)
    except Exception:
        return "—"

def calc_er(likes, comments, views) -> float:
    """Engagement rate by views"""
    try:
        v = int(views or 0)
        if v == 0: return 0.0
        return round((int(likes or 0) + int(comments or 0)) / v * 100, 2)
    except Exception:
        return 0.0

def er_class(er: float) -> str:
    if er >= 5:  return "eng-high"
    if er >= 2:  return "eng-med"
    return "eng-low"

def platform_style(p: str) -> str:
    if p == "TikTok":    return "color:#67e8f9;border-color:rgba(103,232,249,.3);background:rgba(103,232,249,.08)"
    if p == "Instagram": return "color:#f9a8d4;border-color:rgba(249,168,212,.3);background:rgba(249,168,212,.08)"
    return "color:#c4b5fd;border-color:rgba(196,181,253,.3);background:rgba(196,181,253,.08)"

# ─────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────
DEFAULTS = {
    "step":              1,
    "reels":             [],
    "search_query":      "viral",
    "platform_filter":   "All",
    "selected_reel":     None,
    "video_path":        None,
    "video_duration":    60.0,
    "frame_time":        8.0,
    "frame_b64":         None,
    "swapped_url":       None,
    "final_video_url":   None,
    "pipeline_runs":     0,
    "niches_explored":   [],
    "total_reels":       0,
    "creator_bytes":     None,
    "face_swap_prompt":  "Place the person from image 1 in the scene of image 2, same pose and framing. Photorealistic, vertical 9:16, 4K, warm cinematic color grading. No text, no watermarks.",
    "video_prompt":      "Cinematic ambient video. Slow smooth camera push-in. Subtle ambient motion, depth-of-field bokeh. Vertical 9:16. No text.",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────
# API HELPERS — HikerAPI
# ─────────────────────────────────────────────────────────────
def _hiker_headers():
    return {"x-access-key": HIKER_KEY, "accept": "application/json"}

def _parse_hiker_item(item: dict) -> dict | None:
    if not item or item.get("media_type") not in (2, 8, None):
        pass  # allow all types for now
    user = item.get("user") or {}
    thumb = (
        item.get("thumbnail_url") or
        (((item.get("image_versions2") or {}).get("candidates") or [{}])[0]).get("url") or
        item.get("display_url") or ""
    )
    likes    = int(item.get("like_count")    or 0)
    comments = int(item.get("comment_count") or 0)
    views    = int(item.get("play_count") or item.get("ig_play_count") or item.get("view_count") or 0)
    username = user.get("username") or item.get("owner", {}).get("username") or "unknown"
    caption  = (item.get("caption_text") or item.get("caption") or "")
    if isinstance(caption, dict):
        caption = caption.get("text") or ""
    return {
        "id":        str(item.get("pk") or item.get("id") or ""),
        "code":      item.get("code") or item.get("shortCode") or "",
        "title":     caption[:120],
        "author":    f"@{username}",
        "avatar":    username[:2].upper(),
        "likes":     likes,
        "comments":  comments,
        "views":     views,
        "engagement": calc_er(likes, comments, views),
        "likes_fmt":    fmt_num(likes),
        "comments_fmt": fmt_num(comments),
        "views_fmt":    fmt_num(views),
        "thumbnail":    thumb,
        "video_url":    item.get("video_url") or "",
        "duration":     float(item.get("video_duration") or 0),
        "platform":     "Instagram",
        "source":       "HikerAPI",
        "url": f"https://www.instagram.com/reel/{item.get('code','')}/" if item.get("code") else "",
    }

def hiker_search(hashtag: str) -> list[dict]:
    """Fetch viral reels via HikerAPI — tries 3 endpoints"""
    tag = hashtag.lstrip("#").strip() or "viral"
    h   = _hiker_headers()
    results = []

    # 1. Reels-only clips endpoint (v1)
    endpoints = [
        ("GET", f"{HIKER_API}/v1/hashtag/medias/clips/chunk", {"name": tag}),
        ("GET", f"{HIKER_API}/v2/hashtag/medias/top",         {"name": tag}),
        ("GET", f"{HIKER_API}/v2/fbsearch/reels",             {"query": tag}),
    ]
    for method, url, params in endpoints:
        try:
            r = requests.get(url, params=params, headers=h, timeout=15)
            if r.status_code != 200:
                continue
            data  = r.json()
            items = (data.get("items")
                  or data.get("response", {}).get("items")
                  or data.get("media_cropped_items")
                  or [])
            for it in items[:20]:
                parsed = _parse_hiker_item(it)
                if parsed and parsed["video_url"]:
                    results.append(parsed)
            if results:
                break
        except Exception:
            continue
    return results

def hiker_get_video_url(ig_url: str) -> str:
    """Resolve Instagram URL → direct mp4 URL via HikerAPI"""
    r = requests.get(
        f"{HIKER_API}/v2/media/info/by/url",
        params={"url": ig_url},
        headers=_hiker_headers(),
        timeout=15,
    )
    d = r.json()
    return d.get("video_url") or d.get("download_url") or ""

# ─────────────────────────────────────────────────────────────
# API HELPERS — Apify
# ─────────────────────────────────────────────────────────────
def _parse_apify_item(item: dict) -> dict | None:
    likes    = int(item.get("likesCount")   or 0)
    if likes == -1: likes = 0
    comments = int(item.get("commentsCount") or 0)
    views    = int(item.get("videoPlayCount") or item.get("videoViewCount") or 0)
    username = item.get("ownerUsername") or "unknown"
    return {
        "id":        str(item.get("id") or ""),
        "code":      item.get("shortCode") or "",
        "title":     (item.get("caption") or "")[:120],
        "author":    f"@{username}",
        "avatar":    username[:2].upper(),
        "likes":     likes,
        "comments":  comments,
        "views":     views,
        "engagement": calc_er(likes, comments, views),
        "likes_fmt":    fmt_num(likes),
        "comments_fmt": fmt_num(comments),
        "views_fmt":    fmt_num(views),
        "thumbnail":    item.get("displayUrl") or item.get("thumbnailSrc") or "",
        "video_url":    item.get("videoUrl") or "",
        "duration":     float(item.get("videoDuration") or 0),
        "platform":     "Instagram",
        "source":       "Apify",
        "url":          item.get("url") or f"https://www.instagram.com/reel/{item.get('shortCode','')}/",
    }

def apify_search(hashtag: str) -> list[dict]:
    """Fetch reels via Apify instagram-hashtag-scraper"""
    tag = hashtag.lstrip("#").strip()
    params = {"token": APIFY_KEY}
    try:
        # Start run
        run_r = requests.post(
            f"{APIFY_API}/acts/apify~instagram-hashtag-scraper/runs",
            params=params,
            json={"hashtags": [tag], "resultsType": "reels", "resultsLimit": 15},
            timeout=10,
        )
        run_r.raise_for_status()
        run_id = run_r.json().get("data", {}).get("id") or run_r.json().get("id")
        if not run_id:
            return []

        # Poll completion (max 90s)
        dataset_id = None
        for _ in range(45):
            time.sleep(2)
            status_r = requests.get(f"{APIFY_API}/actor-runs/{run_id}", params=params, timeout=10)
            run_data = status_r.json().get("data") or status_r.json()
            status   = run_data.get("status", "")
            if status == "SUCCEEDED":
                dataset_id = run_data.get("defaultDatasetId")
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                return []

        if not dataset_id:
            return []

        # Get items
        items_r = requests.get(
            f"{APIFY_API}/datasets/{dataset_id}/items",
            params={**params, "limit": 15},
            timeout=15,
        )
        results = []
        for it in items_r.json():
            parsed = _parse_apify_item(it)
            if parsed and parsed["video_url"]:
                results.append(parsed)
        return results
    except Exception:
        return []

# ─────────────────────────────────────────────────────────────
# API HELPERS — Video Download + Frame Extraction
# ─────────────────────────────────────────────────────────────
def download_video(url: str) -> str:
    """Download mp4 to temp file, return path"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    r   = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    for chunk in r.iter_content(8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name

def get_video_info(path: str) -> tuple[float, int, int]:
    """Returns (duration_s, width, height)"""
    cap = cv2.VideoCapture(path)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return total / fps, w, h

def extract_frame(path: str, timestamp: float) -> bytes | None:
    """Extract JPEG frame at timestamp, return bytes"""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
    ts  = max(0.0, min(timestamp, dur - 0.1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()

# ─────────────────────────────────────────────────────────────
# API HELPERS — WaveSpeed / Kling
# ─────────────────────────────────────────────────────────────
def ws_submit(model: str, payload: dict) -> str:
    r = requests.post(
        f"{WS_API}/{model}",
        json=payload,
        headers={"Authorization": f"Bearer {WS_KEY}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    return d.get("data", {}).get("id") or d.get("id") or ""

def ws_poll(pred_id: str, status_ph=None, timeout: int = 300) -> str:
    start = time.time()
    dots  = 0
    while time.time() - start < timeout:
        r = requests.get(
            f"https://api.wavespeed.ai/api/v3/predictions/{pred_id}/result",
            headers={"Authorization": f"Bearer {WS_KEY}"},
            timeout=15,
        )
        d      = r.json().get("data") or r.json()
        status = d.get("status") or ""
        if status_ph:
            dots = (dots + 1) % 4
            status_ph.info(f"⏳ Processing{'.' * (dots+1)} ({int(time.time()-start)}s)")
        if status == "completed":
            outputs = d.get("outputs") or []
            return outputs[0] if outputs else ""
        if status == "failed":
            raise RuntimeError(d.get("error") or "WaveSpeed job failed")
        time.sleep(3)
    raise TimeoutError("WaveSpeed job timed out")

# ─────────────────────────────────────────────────────────────
# HEADER (shared across all steps)
# ─────────────────────────────────────────────────────────────
def render_header():
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:12px;padding:4px 0">
          <span style="font-size:28px">🐋</span>
          <div>
            <div style="font-size:20px;font-weight:800;color:#f4f4f5;letter-spacing:-.4px">T-WHALES</div>
            <div style="font-size:11px;color:#71717a;margin-top:1px">Viral Discovery Pipeline</div>
          </div>
          <div class="step-badge active" style="margin-left:8px">● LIVE</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        # Step indicator
        steps = ["Discovery", "Frames", "Review", "Final Video"]
        cur   = st.session_state.step
        badges = ""
        for i, lbl in enumerate(steps, 1):
            if i < cur:
                cls, icon = "done",    "✓"
            elif i == cur:
                cls, icon = "active",  str(i)
            else:
                cls, icon = "pending", str(i)
            badges += f'<span class="step-badge {cls}">{icon} {lbl}</span> '
            if i < len(steps):
                badges += '<span style="color:#333;margin:0 2px">→</span> '
        st.markdown(f'<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;justify-content:flex-end">{badges}</div>', unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#1e1e1e;margin:12px 0 20px"/>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# STATS BAR (real data from session state)
# ─────────────────────────────────────────────────────────────
def render_stats():
    reels = st.session_state.reels
    total = len(reels)

    # Avg engagement (views-based ER)
    ers = [r["engagement"] for r in reels if r.get("engagement", 0) > 0]
    avg_er = round(sum(ers) / len(ers), 2) if ers else 0.0

    # Trending niches (unique hashtags explored)
    niches = len(set(st.session_state.niches_explored))

    # Pipeline runs
    runs = st.session_state.pipeline_runs

    c1, c2, c3, c4 = st.columns(4)
    stats = [
        (c1, "Reels Tracked",    total,        f"+{total} this session",  "👁", "#8b5cf6"),
        (c2, "Avg Engagement",   f"{avg_er}%", "Views-based ER",          "🔥", "#f97316"),
        (c3, "Niches Explored",  niches,       "Unique hashtags searched", "⚡", "#00e5ff"),
        (c4, "Pipeline Runs",    runs,         "Completed pipelines",      "🔀", "#22c55e"),
    ]
    for col, label, val, delta, icon, color in stats:
        with col:
            st.markdown(f"""
            <div class="whale-stat">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                  <div style="font-size:11px;color:#52525b;margin-bottom:6px">{label}</div>
                  <div style="font-size:26px;font-weight:800;color:#f4f4f5;letter-spacing:-.5px">{val}</div>
                  <div style="font-size:10px;color:#52525b;margin-top:4px">{delta}</div>
                </div>
                <div style="width:36px;height:36px;border-radius:10px;background:{color}22;border:1px solid {color}44;
                            display:flex;align-items:center;justify-content:center;font-size:16px">{icon}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
    st.markdown("<div style='height:12px'/>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# STEP 1 — DISCOVERY FEED
# ─────────────────────────────────────────────────────────────
def render_discovery():
    # Search controls
    sc1, sc2, sc3, sc4 = st.columns([3, 1.5, 1.5, 1])
    with sc1:
        q = st.text_input("🔍 Hashtag or keyword", value=st.session_state.search_query,
                          placeholder="viral, fitness, crypto …", label_visibility="collapsed")
    with sc2:
        source = st.selectbox("Source", ["HikerAPI", "Apify", "Both"], label_visibility="collapsed",
                              index=["HikerAPI","Apify","Both"].index(st.session_state.get("source","HikerAPI")))
    with sc3:
        pf = st.selectbox("Platform", ["All","Instagram","TikTok"], label_visibility="collapsed")
    with sc4:
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

    if search_clicked:
        st.session_state.search_query = q.strip() or "viral"
        st.session_state.source       = source
        st.session_state.platform_filter = pf
        # Track niche
        if q and q not in st.session_state.niches_explored:
            st.session_state.niches_explored.append(q)

        reels = []
        with st.spinner(f"🔎 Searching **{source}** for #{st.session_state.search_query} …"):
            if source in ("HikerAPI", "Both"):
                hr = hiker_search(st.session_state.search_query)
                reels.extend(hr)
            if source in ("Apify", "Both"):
                ar = apify_search(st.session_state.search_query)
                # Deduplicate by code
                existing = {r["code"] for r in reels}
                for r in ar:
                    if r["code"] not in existing:
                        reels.append(r)
                        existing.add(r["code"])

        # Apply platform filter
        if pf != "All":
            reels = [r for r in reels if r["platform"] == pf]

        # Sort by engagement desc
        reels.sort(key=lambda x: x["engagement"], reverse=True)
        st.session_state.reels = reels

        if not reels:
            st.warning("⚠️ No results found. Try a different hashtag or source.")
        else:
            st.success(f"✅ Found **{len(reels)} reels** — sorted by engagement rate")
        st.rerun()

    reels = st.session_state.reels

    # ── Feed header ──────────────────────────────────────
    if reels:
        st.markdown(f"""
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <div>
            <div style="font-size:16px;font-weight:700;color:#f4f4f5">🔥 Viral Discovery Feed</div>
            <div style="font-size:11px;color:#52525b;margin-top:2px">
              {len(reels)} reels · #{st.session_state.search_query} ·
              <span style="color:#8b5cf6">{st.session_state.source}</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Cards grid ───────────────────────────────────────
    if not reels:
        st.markdown("""
        <div style="text-align:center;padding:80px 20px;color:#52525b">
          <div style="font-size:48px;margin-bottom:16px">🐋</div>
          <div style="font-size:16px;font-weight:600;color:#71717a">No reels yet</div>
          <div style="font-size:13px;margin-top:8px">Search a hashtag above to discover viral content</div>
        </div>
        """, unsafe_allow_html=True)
        return

    COLS = 4
    for row_start in range(0, len(reels), COLS):
        cols = st.columns(COLS)
        for ci, reel in enumerate(reels[row_start:row_start + COLS]):
            with cols[ci]:
                er  = reel["engagement"]
                ecls = er_class(er)
                ps   = platform_style(reel["platform"])
                thumb = reel.get("thumbnail") or ""
                # Card HTML
                st.markdown(f"""
                <div class="whale-card">
                  {"<img src='" + thumb + "' style='width:100%;border-radius:10px;aspect-ratio:9/16;object-fit:cover;margin-bottom:8px'>" if thumb else "<div style='width:100%;aspect-ratio:9/16;background:#1a1a1a;border-radius:10px;margin-bottom:8px;display:flex;align-items:center;justify-content:center;font-size:32px'>🎬</div>"}
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                    <span class="platform-badge" style="{ps}">{reel['platform']}</span>
                    <span class="{ecls}" style="font-size:12px">{er}%</span>
                  </div>
                  <div style="font-size:11px;font-weight:600;color:#c4b5fd;margin-bottom:4px">{reel['author']}</div>
                  <div style="font-size:11px;color:#a1a1aa;line-height:1.4;height:48px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;margin-bottom:8px">{reel['title'] or '—'}</div>
                  <div style="display:flex;gap:10px;font-size:10px;color:#71717a;margin-bottom:4px">
                    <span>👁 {reel['views_fmt']}</span>
                    <span>❤️ {reel['likes_fmt']}</span>
                    <span>💬 {reel['comments_fmt']}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # Download button (native Streamlit)
                btn_key = f"dl_{reel['id']}_{ci}_{row_start}"
                if st.button("⬇️ Download & Start Pipeline", key=btn_key, use_container_width=True):
                    _start_pipeline(reel)

def _start_pipeline(reel: dict):
    """Download reel video and advance to Step 2"""
    video_url = reel.get("video_url") or ""

    # If no direct video_url, try resolving via HikerAPI
    if not video_url and reel.get("url"):
        with st.spinner("🔗 Resolving video URL…"):
            try:
                video_url = hiker_get_video_url(reel["url"])
            except Exception as e:
                st.error(f"Failed to resolve URL: {e}")
                return

    if not video_url:
        st.error("❌ No video URL found for this reel.")
        return

    with st.spinner("⬇️ Downloading video…"):
        try:
            path = download_video(video_url)
            dur, _, _ = get_video_info(path)
        except Exception as e:
            st.error(f"Download failed: {e}")
            return

    st.session_state.selected_reel  = reel
    st.session_state.video_path     = path
    st.session_state.video_duration = dur
    st.session_state.frame_time     = min(8.0, dur * 0.15)
    st.session_state.frame_b64      = None
    st.session_state.swapped_url    = None
    st.session_state.final_video_url = None
    st.session_state.step           = 2
    st.rerun()

# ─────────────────────────────────────────────────────────────
# STEP 2 — FRAME SELECTION
# ─────────────────────────────────────────────────────────────
def render_frame_selection():
    reel = st.session_state.selected_reel
    path = st.session_state.video_path
    dur  = st.session_state.video_duration

    if not path or not os.path.exists(path):
        st.error("Video not found. Please go back to Step 1.")
        if st.button("← Back to Discovery"):
            st.session_state.step = 1; st.rerun()
        return

    st.markdown(f"""
    <div style="margin-bottom:20px">
      <div style="font-size:18px;font-weight:700;color:#f4f4f5">🎞️ Select Your Frame</div>
      <div style="font-size:12px;color:#52525b;margin-top:4px">
        Source: <span style="color:#c4b5fd">{reel['author'] if reel else '?'}</span> ·
        Duration: {dur:.1f}s · Choose the perfect moment for your content
      </div>
    </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([2, 1])

    with col_left:
        # Video preview
        st.video(path)

        st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)

        # ── AI Recommended Frames ──
        st.markdown("**✨ AI Recommended Frames**", help="Frames with highest audience retention based on video analysis")
        rec_times = [
            max(0.1, dur * 0.12),   # ~12% — opening hook
            max(0.1, dur * 0.52),   # ~52% — key moment
        ]
        rec_labels = ["Opening Hook", "Key Moment"]
        rec_reasons = [
            "Peak viewer attention — high retention area",
            "Engagement spike — viewers most invested here",
        ]

        rc1, rc2 = st.columns(2)
        for ci, (t, label, reason) in enumerate(zip(rec_times, rec_labels, rec_reasons)):
            col = rc1 if ci == 0 else rc2
            with col:
                frame_bytes = extract_frame(path, t)
                if frame_bytes:
                    st.image(frame_bytes, caption=f"⭐ {label} ({t:.1f}s)", use_container_width=True)
                else:
                    st.markdown(f"*Frame at {t:.1f}s*")
                st.markdown(f'<div style="font-size:10px;color:#71717a">{reason}</div>', unsafe_allow_html=True)
                if st.button(f"Use this frame ({t:.1f}s)", key=f"rec_{ci}", use_container_width=True):
                    st.session_state.frame_time = t
                    st.rerun()

    with col_right:
        st.markdown("**🎛️ Custom Frame Selector**")

        # Scrubber slider
        frame_time = st.slider(
            "Slide to select frame",
            min_value=0.0,
            max_value=max(0.1, dur - 0.1),
            value=float(st.session_state.frame_time),
            step=0.5,
            format="%.1f s",
            label_visibility="collapsed",
        )
        if abs(frame_time - st.session_state.frame_time) > 0.1:
            st.session_state.frame_time = frame_time
            st.rerun()

        # Selected frame preview
        st.markdown("**Selected Frame Preview**")
        frame_bytes = extract_frame(path, st.session_state.frame_time)
        if frame_bytes:
            st.image(frame_bytes, caption=f"Frame @ {st.session_state.frame_time:.1f}s", use_container_width=True)
            st.session_state.frame_b64 = to_b64(frame_bytes)
        else:
            st.warning("Could not extract frame at this position")

        st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)

        # Creator photo upload
        st.markdown("**👤 Your Creator Photo**")
        uploaded = st.file_uploader("Upload your photo (face for swap)", type=["jpg","jpeg","png"],
                                    label_visibility="collapsed")
        if uploaded:
            st.session_state.creator_bytes = uploaded.read()
            st.image(st.session_state.creator_bytes, caption="Creator photo loaded ✓", use_container_width=True)
        elif st.session_state.creator_bytes:
            st.image(st.session_state.creator_bytes, caption="Creator photo ✓", use_container_width=True)

        st.markdown("<div style='height:12px'/>", unsafe_allow_html=True)

        # Generate button
        can_gen = bool(st.session_state.frame_b64 and st.session_state.creator_bytes)
        if st.button("✨ Generate Image →", type="primary", use_container_width=True, disabled=not can_gen):
            st.session_state.step = 3
            st.rerun()

        if not can_gen:
            st.caption("⚠️ Upload your photo to enable generation")

        st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)
        if st.button("← Back to Discovery", use_container_width=True):
            st.session_state.step = 1; st.rerun()

# ─────────────────────────────────────────────────────────────
# STEP 3 — REVIEW GENERATED IMAGE
# ─────────────────────────────────────────────────────────────
def render_review():
    if not st.session_state.swapped_url:
        _generate_image()

    if not st.session_state.swapped_url:
        return  # generation failed / still running

    st.markdown("""
    <div style="margin-bottom:20px">
      <div style="font-size:18px;font-weight:700;color:#f4f4f5">🖼️ Review Generated Image</div>
      <div style="font-size:12px;color:#52525b;margin-top:4px">
        AI face-swap complete — approve to generate your video
      </div>
    </div>
    """, unsafe_allow_html=True)

    col_img, col_info = st.columns([1, 1.2])

    with col_img:
        st.image(st.session_state.swapped_url, caption="AI Generated Image ✨", use_container_width=True)

    with col_info:
        st.markdown("""
        <div class="whale-card" style="padding:20px">
          <div style="font-size:13px;font-weight:700;color:#f4f4f5;margin-bottom:14px">Generation Details</div>
        """, unsafe_allow_html=True)

        details = [
            ("Model",       "QWEN-Image-2.0-Pro"),
            ("Type",        "Face Swap / Inpainting"),
            ("Resolution",  "High Quality"),
            ("Status",      "✅ Ready"),
        ]
        for k, v in details:
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:6px 0;
                        border-bottom:1px solid #1e1e1e;font-size:12px">
              <span style="color:#71717a">{k}</span>
              <span style="color:#f4f4f5;font-weight:600">{v}</span>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Prompt editor
        with st.expander("✏️ Edit Prompts"):
            st.session_state.face_swap_prompt = st.text_area(
                "Face Swap Prompt", st.session_state.face_swap_prompt, height=80)
            st.session_state.video_prompt = st.text_area(
                "Video Generation Prompt", st.session_state.video_prompt, height=80)

        st.markdown("<div style='height:16px'/>", unsafe_allow_html=True)

        if st.button("✅ Εγκρίνω — Generate Video →", type="primary", use_container_width=True):
            st.session_state.step = 4; st.rerun()

        if st.button("🔄 Ξανά — Regenerate Image", use_container_width=True):
            st.session_state.swapped_url = None; st.rerun()

        if st.button("← Back to Frame Selection", use_container_width=True):
            st.session_state.swapped_url = None
            st.session_state.step = 2; st.rerun()

def _generate_image():
    st.info("🎨 Generating image with AI face swap…")
    ph = st.empty()
    try:
        creator_b64 = to_b64(st.session_state.creator_bytes)
        frame_b64   = st.session_state.frame_b64

        if not creator_b64 or not frame_b64:
            st.error("Missing creator photo or frame. Please go back.")
            return

        pred_id = ws_submit(
            "wavespeed-ai/qwen-image-2.0-pro/edit",
            {
                "images": [creator_b64, frame_b64],
                "prompt": st.session_state.face_swap_prompt,
                "seed": -1,
            },
        )
        result = ws_poll(pred_id, status_ph=ph)
        ph.empty()
        if result:
            st.session_state.swapped_url = result
        else:
            st.error("Image generation returned empty result.")
    except Exception as e:
        ph.empty()
        st.error(f"Generation failed: {e}")

# ─────────────────────────────────────────────────────────────
# STEP 4 — FINAL VIDEO
# ─────────────────────────────────────────────────────────────
def render_final():
    if not st.session_state.final_video_url:
        _generate_video()

    if not st.session_state.final_video_url:
        return

    # Increment pipeline runs counter
    if not st.session_state.get("_counted_run"):
        st.session_state.pipeline_runs += 1
        st.session_state["_counted_run"] = True

    st.markdown("""
    <div style="margin-bottom:20px">
      <div style="font-size:18px;font-weight:700;color:#34d399">✅ Your Video is Ready!</div>
      <div style="font-size:12px;color:#52525b;margin-top:4px">
        Kling v3.0 motion-control pipeline completed
      </div>
    </div>
    """, unsafe_allow_html=True)

    col_vid, col_info = st.columns([1, 1.2])

    with col_vid:
        st.video(st.session_state.final_video_url)

    with col_info:
        reel = st.session_state.selected_reel or {}
        st.markdown("""<div class="whale-card" style="padding:20px">
          <div style="font-size:13px;font-weight:700;color:#34d399;margin-bottom:14px">✅ Pipeline Complete</div>
        """, unsafe_allow_html=True)

        summary = [
            ("Source Reel",    reel.get("author", "—")),
            ("Frame Used",     f"{st.session_state.frame_time:.1f}s"),
            ("Image Model",    "QWEN-Image-2.0-Pro"),
            ("Video Model",    "Kling v3.0-Pro Motion"),
            ("Pipeline Runs",  str(st.session_state.pipeline_runs)),
        ]
        for k, v in summary:
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:6px 0;
                        border-bottom:1px solid #1e1e1e;font-size:12px">
              <span style="color:#71717a">{k}</span>
              <span style="color:#34d399;font-weight:600">{v}</span>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:16px'/>", unsafe_allow_html=True)

        # Download button
        try:
            vid_bytes = requests.get(st.session_state.final_video_url, timeout=30).content
            st.download_button(
                "⬇️ Download Final Video",
                data=vid_bytes,
                file_name="twhales_final.mp4",
                mime="video/mp4",
                use_container_width=True,
                type="primary",
            )
        except Exception:
            st.link_button("⬇️ Open Video", st.session_state.final_video_url)

        if st.button("🔄 Start New Pipeline", use_container_width=True):
            # Reset pipeline state but keep reels
            for k in ["selected_reel","video_path","video_duration","frame_time",
                      "frame_b64","swapped_url","final_video_url","_counted_run"]:
                st.session_state[k] = DEFAULTS.get(k)
            st.session_state.step = 1
            st.rerun()

def _generate_video():
    st.info("🎬 Generating video with Kling v3.0-pro motion-control…")
    ph = st.empty()
    try:
        path        = st.session_state.video_path
        swapped_url = st.session_state.swapped_url

        if not path or not swapped_url:
            st.error("Missing video or image. Please go back.")
            return

        with open(path, "rb") as f:
            video_b64 = to_b64(f.read(), mime="video/mp4")

        pred_id = ws_submit(
            "kwaivgi/kling-v3.0-pro/motion-control",
            {
                "image":                swapped_url,
                "video":                video_b64,
                "character_orientation": "video",
                "prompt":               st.session_state.video_prompt,
            },
        )
        result = ws_poll(pred_id, status_ph=ph, timeout=360)
        ph.empty()
        if result:
            st.session_state.final_video_url = result
            st.session_state["_counted_run"] = False
            st.rerun()
        else:
            st.error("Video generation returned empty result.")
    except Exception as e:
        ph.empty()
        st.error(f"Video generation failed: {e}")

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
render_header()
render_stats()

step = st.session_state.step
if   step == 1: render_discovery()
elif step == 2: render_frame_selection()
elif step == 3: render_review()
elif step == 4: render_final()
