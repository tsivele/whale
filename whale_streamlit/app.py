"""
Fix: Step 2 URL paste fallback when batch empty━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1 · Discovery   — HikerAPI + Apify viral reel search
Step 2 · Frames      — AI-recommended frames + custom scrubber
Step 3 · Review      — WaveSpeed face-swap image generation
Step 4 · Final Video — Kling v3.0-pro motion-control video
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import streamlit as st
import requests, json, time, os, tempfile, base64, math, re, subprocess
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
/* Hide Streamlit & GitHub toolbars */
[data-testid="stToolbar"],[data-testid="stDecoration"],
[data-testid="stStatusWidget"],.stDeployButton,
.viewerBadge_container__r5tak,.viewerBadge_link__qRIco,
header[data-testid="stHeader"], .stApp > header,
#MainMenu, footer, .stAppToolbar,
iframe[title="streamlit_footer"] { display: none !important; }
.stApp { overflow: hidden !important; }
.main .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# API KEYS (from Streamlit Secrets)
# ─────────────────────────────────────────────────────────────
WS_KEY    = st.secrets.get("WAVESPEED_KEY", "wsk_live_9fa52fRA-LqiRiMrTRJX_W_LcN7JhGo7Bza3vhmxI4M")
HIKER_KEY = st.secrets.get("HIKER_KEY",     "zw9us00t8j3aiimwvjvd3600iqelqj8x")
APIFY_KEY = st.secrets.get("APIFY_KEY",     "apify_api_nGZAclYjIoPbEcvTFFVQMcIKCurD2J1uWF9C")

WS_API    = "https://api.wavespeed.ai/api/v3"
HIKER_API = "https://api.hikerapi.com"
APIFY_API = "https://api.apify.com/v2"

QWEN_MODEL  = "wavespeed-ai/qwen-image-2.0-pro/edit"
KLING_MODEL = "kwaivgi/kling-v3.0-pro/motion-control"

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
    "batch_queue":       [],
    "batch_idx":         0,
    "batch_reels":       [],
    "creator_bytes":     None,
    "face_swap_prompt":  "Use Image A as the complete identity reference and Image B as the base/body reference. Replace the person in Image B entirely with the girl from Image A while preserving the exact pose, body position, clothing, framing, camera angle, lighting, background, and scene composition from Image B. The final image must look as if the girl from Image A was originally photographed in the scene of Image B. Match the facial identity from Image A with maximum accuracy, including: * exact face shape * skin tone and texture * hairstyle and hair color * hair length and hairline * eyes, eyebrows, nose, lips, and jawline * makeup style and facial details * expression consistency when possible Do not retain any facial or hair features from Image B. Only use Image B for the body, clothing, pose, environment, and composition. Ensure: * seamless and photorealistic blending * natural lighting adaptation * accurate perspective and head angle alignment * realistic shadows and skin integration * proportional anatomy * ultra-detailed facial realism * no distortions, warping, or uncanny features The output should appear completely natural and indistinguishable from a real photograph. Keep the first hair color and Face Visible and Larger breast no captions no text no font and Bigger breast.NO TATTOOS",
    "video_prompt":      "Animate the character from the reference image using the exact motion from the driving video. The character identity must remain exactly as shown in the reference image throughout every single frame — never drift toward or blend with any person from the driving video. Lip-sync is the top priority: replicate every mouth shape, jaw movement, and lip position frame-by-frame to match the original audio and speech timing with perfect accuracy. Transfer all body movements precisely: shoulder shifts, head tilts, arm gestures, hand positions, and torso motion must mirror the driving video exactly. If the person in the driving video is holding any object — a phone, microphone, drink, prop, or anything else — the character must also be holding that same object in the same hand position throughout. Maintain consistent character appearance, clothing, and all visible features in every frame.",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────
# API HELPERS — HikerAPI
# ─────────────────────────────────────────────────────────────
def _hiker_headers():
    return {"x-access-key": HIKER_KEY, "accept": "application/json"}

def _parse_hiker_item(item: dict) -> "dict | None":
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

def hiker_search(hashtag: str) -> "list[dict]":
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
    media = d.get("media_or_ad") or d
    return (media.get("video_url") or media.get("download_url") or
            ((media.get("video_versions") or [{}])[0]).get("url") or "")

# ─────────────────────────────────────────────────────────────
# API HELPERS — Apify
# ─────────────────────────────────────────────────────────────
def _parse_apify_item(item: dict) -> "dict | None":
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

def apify_search(hashtag: str) -> "list[dict]":
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
def _try_save(url: str, out: str, timeout: int = 90) -> bool:
    """Download url to file, return True if > 50KB"""
    try:
        r = requests.get(url, stream=True, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"})
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "html" in ct or "text/plain" in ct:
            return False
        with open(out, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return os.path.exists(out) and os.path.getsize(out) > 50_000
    except Exception:
        return False

def download_video(url: str) -> str:
    """Download: HikerAPI primary → CDN direct → yt-dlp fallback"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tmp.close()
    out = tmp.name
    errors = []

    # ── Layer 1: HikerAPI (resolves CDN URL — works from any IP) ───────────────────────
    try:
        hk = requests.get(
            f"{HIKER_API}/v2/media/info/by/url",
            params={"url": url},
            headers=_hiker_headers(),
            timeout=20)
        if hk.ok:
            hd = hk.json()
            # HikerAPI wraps media inside 'media_or_ad' key
            media = hd.get("media_or_ad") or hd
            vurl = (media.get("video_url") or media.get("download_url") or
                    ((media.get("video_versions") or [{}])[0]).get("url") or
                    media.get("clips_metadata", {}).get("original_sound_info", {}).get("progressive_download_url"))
            if vurl and _try_save(vurl, out):
                return out
            errors.append(f"hiker:keys={list(media.keys())[:6]}")
        else:
            errors.append(f"hiker:{hk.status_code}")
    except Exception as e:
        errors.append(f"hiker:{e}")

    # ── Layer 2: Direct CDN (pre-resolved discovery URLs) ──────────────────────
    if any(x in url for x in ["cdninstagram", "fbcdn", "tiktokcdn", "akamaized", ".mp4", "scontent"]):
        if _try_save(url, out):
            return out
        errors.append("cdn:small")

    # ── Layer 3: yt-dlp ──────────────────────────────────────────────────────────────────────────
    try:
        r = subprocess.run([
            "yt-dlp", "--no-warnings", "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4", "--no-part", "--no-cache-dir",
            "-o", out, url,
        ], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 50_000:
            return out
        last_err = (r.stderr or "").strip().split("\n")[-1][:80]
        errors.append(f"yt-dlp:rc={r.returncode} {last_err}")
    except Exception as e:
        errors.append(f"yt-dlp:{e}")

    # ── Layer 4: HikerAPI TikTok endpoint ───────────────────────────────────────────────────────
    if "tiktok.com" in url.lower():
        try:
            tk = requests.get(
                f"{HIKER_API}/v1/tiktok/video/by/url",
                params={"url": url},
                headers=_hiker_headers(),
                timeout=20)
            if tk.ok:
                td = tk.json()
                vurl2 = (td.get("video_url") or td.get("download_url") or
                         (td.get("video") or {}).get("download_addr") or
                         (((td.get("video") or {}).get("play_addr") or {}).get("url_list") or [""])[0])
                if vurl2 and _try_save(vurl2, out):
                    return out
                errors.append(f"hiker-tt:{list(td.keys())[:4]}")
            else:
                errors.append(f"hiker-tt:{tk.status_code}")
        except Exception as e:
            errors.append(f"hiker-tt:{e}")

    # ── Layer 5: Plain GET last resort ─────────────────────────────────────────────────────────────────
    if _try_save(url, out, timeout=60):
        return out

    raise RuntimeError(" | ".join(errors))


def get_video_info(path: str) -> "tuple[float, int, int]":
    """Returns (duration_s, width, height) via ffprobe"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(",")
            w   = int(parts[0]) if len(parts) > 0 and parts[0].strip().isdigit() else 720
            h   = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else 1280
            dur = float(parts[2]) if len(parts) > 2 else 60.0
            return dur, w, h
    except Exception:
        pass
    try:
        r2 = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10)
        dur = float(r2.stdout.strip()) if r2.stdout.strip() else 60.0
        return dur, 720, 1280
    except Exception:
        return 60.0, 720, 1280

def extract_frame(path: str, timestamp: float) -> bytes | None:
    """Extract frame: cv2 → ffmpeg fallback. Always tries first frame."""
    import shutil
    ts = max(0.0, timestamp)
    last_err = ""

    # Method 1: cv2 (fastest, no subprocess needed)
    try:
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            dur_v = total / fps if fps > 0 else 60
            safe_ts = min(ts, max(0, dur_v - 0.1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(safe_ts * fps))
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                return buf.tobytes()
            # Try first frame
            cap2 = cv2.VideoCapture(str(path))
            cap2.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret2, frame2 = cap2.read()
            cap2.release()
            if ret2 and frame2 is not None:
                _, buf2 = cv2.imencode(".jpg", frame2, [cv2.IMWRITE_JPEG_QUALITY, 90])
                return buf2.tobytes()
            last_err = "cv2: opened but no frame"
        else:
            last_err = "cv2: cannot open file"
    except Exception as ex:
        last_err = f"cv2:{ex}"

    # Method 2: ffmpeg to temp file
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    for seek_args in [[], ["-ss", "0"], ["-ss", f"{ts:.3f}"], ["-ss", "1"]]:
        try:
            jpg = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            jpg.close()
            cmd = [ffmpeg_bin, "-y"] + seek_args + [
                "-i", str(path), "-frames:v", "1", "-q:v", "2", jpg.name]
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            if r.returncode == 0 and os.path.exists(jpg.name) and os.path.getsize(jpg.name) > 100:
                with open(jpg.name, "rb") as fh:
                    data = fh.read()
                os.unlink(jpg.name)
                return data
            err = r.stderr.decode(errors="ignore")[-120:] if r.stderr else ""
            last_err = f"ffmpeg(seek={seek_args}):{err}"
            if os.path.exists(jpg.name):
                os.unlink(jpg.name)
        except Exception as ex:
            last_err = f"ffmpeg:{ex}"

    # Store error for display
    import streamlit as _st
    try: _st.session_state["_frame_err"] = last_err
    except Exception: pass
    return None
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
    _render_batch_input()
    st.markdown("<div style='height:4px'/>", unsafe_allow_html=True)
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
                if st.button("➕ Add to Batch", key=f"dl_{reel['id']}_{ci}_{row_start}", use_container_width=True):
                    _add_to_batch(reel)

def _process_batch_url(url: str):
    """Download a raw URL and advance to Step 2 (used for batch paste)."""
    # Build a minimal reel-like dict from the URL
    fake_reel = {
        "id": url[-12:], "code": "", "title": url[:60],
        "author": "Direct URL", "avatar": "🔗",
        "likes": 0, "comments": 0, "views": 0,
        "engagement": 0.0, "views_fmt": "—", "likes_fmt": "—",
        "thumbnail": "", "video_url": url,
        "platform": "TikTok" if "tiktok" in url.lower() else "Instagram",
        "url": url,
    }
    _start_pipeline(fake_reel)

def _make_batch_reel(reel: dict, url: str = "") -> dict:
    return {
        "idx": len(st.session_state.batch_reels),
        "url": url or reel.get("url","") or reel.get("video_url",""),
        "reel": reel, "video_path": None, "duration": 60.0,
        "frame_b64": None, "frame_time": 0.0, "custom_prompt": "",
        "swapped_url": None, "final_url": None, "status": "queued", "error": None,
        "thumbnail": reel.get("thumbnail",""), "author": reel.get("author","Unknown"),
        "approved": False,
    }

def _add_to_batch(reel: dict):
    br = _make_batch_reel(reel)
    if br["url"] not in {r["url"] for r in st.session_state.batch_reels}:
        st.session_state.batch_reels.append(br)
    st.rerun()

def _render_batch_input():
    n = len(st.session_state.batch_reels)
    lbl = f"\U0001f4cb Batch Queue ({n} reel{'s' if n!=1 else ''})" if n > 0 else "\U0001f4cb Paste URLs"
    with st.expander(lbl, expanded=True):
        pasted = st.text_area("URLs", height=90, label_visibility="collapsed", key="batch_url_paste",
            placeholder="Paste Instagram or TikTok URLs, one per line")
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            if st.button("\U0001f680 Add & Process All", type="primary", use_container_width=True):
                urls = [u.strip() for u in pasted.splitlines() if u.strip().startswith("http")]
                existing = {r["url"] for r in st.session_state.batch_reels}
                for u in urls:
                    if u not in existing:
                        fake = {"url":u,"video_url":u,"author":u[:40],"title":u[:60],"id":u[-12:],
                                "code":"","thumbnail":"","views":0,"likes":0,"comments":0,"engagement":0,
                                "platform":"TikTok" if "tiktok" in u.lower() else "Instagram"}
                        st.session_state.batch_reels.append(_make_batch_reel(fake, u))
                if not st.session_state.batch_reels:
                    st.warning("\u26a0 Paste at least one URL first.")
                else:
                    st.session_state.step = 2; st.rerun()
        with c2:
            if st.button("\u2795 Add only", use_container_width=True):
                urls = [u.strip() for u in pasted.splitlines() if u.strip().startswith("http")]
                existing = {r["url"] for r in st.session_state.batch_reels}
                for u in urls:
                    if u not in existing:
                        fake = {"url":u,"video_url":u,"author":u[:40],"title":u[:60],"id":u[-12:],
                                "code":"","thumbnail":"","views":0,"likes":0,"comments":0,"engagement":0,
                                "platform":"TikTok" if "tiktok" in u.lower() else "Instagram"}
                        st.session_state.batch_reels.append(_make_batch_reel(fake, u))
                if urls: st.rerun()
        with c3:
            if n > 0 and st.button("\U0001f5d1\ufe0f Clear", use_container_width=True):
                st.session_state.batch_reels = []; st.rerun()
        if n > 0:
            st.markdown(f"**{n} reel{'s' if n!=1 else ''} queued:**")
            for i, br in enumerate(st.session_state.batch_reels):
                icons={"queued":"\u23f3","downloading":"\u2b07\ufe0f","ready":"\u2705",
                       "faceswapping":"\U0001f3ad","reviewing":"\U0001f441\ufe0f","done":"\U0001f389","error":"\u274c"}
                c1,c2=st.columns([5,1])
                with c1: st.markdown(f"{icons.get(br['status'],'\u23f3')} `{br['author']}` \u2014 {br['url'][:60]}")
                with c2:
                    if st.button("\u2715",key=f"rm_{i}",use_container_width=True):
                        st.session_state.batch_reels.pop(i); st.rerun()
            if st.button("\U0001f680 Process All Now", type="primary", use_container_width=True):
                st.session_state.step=2; st.rerun()


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
    _ref = "/tmp/whale_ref_face.jpg"
    if not st.session_state.creator_bytes and os.path.exists(_ref):
        with open(_ref,"rb") as _f: st.session_state.creator_bytes = _f.read()
    if not st.session_state.creator_bytes:
        st.markdown("**\U0001f464 Reference Photo** \u2014 Upload once, saved for all reels")
        _up = st.file_uploader("Upload face", type=["jpg","jpeg","png"],
                               label_visibility="collapsed", key="face_upload")
        if _up:
            _d = _up.read(); st.session_state.creator_bytes = _d
            with open(_ref,"wb") as _f: _f.write(_d)
            st.rerun()
        st.stop()

    batch = st.session_state.batch_reels
    if not batch:
        st.markdown("**\U0001f4cb Paste your URLs here to start**")
        _urls_direct = st.text_area("URLs (one per line)",
            placeholder="https://www.instagram.com/reel/...\nhttps://www.tiktok.com/...",
            height=120, key="direct_url_input")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("\U0001f680 Start Pipeline", type="primary", use_container_width=True):
                urls = [u.strip() for u in _urls_direct.splitlines() if u.strip().startswith("http")]
                for u in urls:
                    fake = {"url":u,"video_url":u,"author":u[:40],"title":u[:60],"id":u[-12:],
                            "code":"","thumbnail":"","views":0,"likes":0,"comments":0,"engagement":0,
                            "platform":"TikTok" if "tiktok" in u.lower() else "Instagram"}
                    st.session_state.batch_reels.append(_make_batch_reel(fake, u))
                if st.session_state.batch_reels:
                    st.rerun()
                else:
                    st.warning("\u26a0\ufe0f Paste at least one valid URL")
        with c2:
            if st.button("\u2190 Back to Discovery", use_container_width=True):
                st.session_state.step=1; st.rerun()
        return

    needs_dl = [br for br in batch if br["status"]=="queued"]
    if needs_dl:
        prog = st.progress(0); ph = st.empty()
        total = len(batch)
        done_n = sum(1 for b in batch if b["status"] not in ("queued","downloading"))
        for br in needs_dl:
            br["status"] = "downloading"
            ph.info(f"\u2b07\ufe0f Downloading {done_n+1}/{total}: {br['author']}")
            try:
                p = download_video(br["url"])
                dur,_,_ = get_video_info(p)
                br["video_path"]=p; br["duration"]=dur; br["status"]="ready"
            except Exception as e:
                br["status"]="error"; br["error"]=str(e)[:120]
            done_n+=1; prog.progress(done_n/total)
        prog.empty(); ph.empty(); st.rerun()

    st.markdown(f"**\U0001f39e Select Frames \u2014 {len(batch)} reel(s)**")
    all_framed = all(br.get("frame_b64") for br in batch if br["status"]!="error")

    for br in batch:
        idx = br["idx"]
        with st.container():
            st.markdown(f"**#{idx+1} \u00b7 {br['author']}**")
            if br["status"]=="error":
                st.error(f"\u274c {br['error']}"); st.markdown("---"); continue
            path = br.get("video_path")
            if not path or not os.path.exists(str(path)):
                st.warning("Video not ready"); st.markdown("---"); continue
            ai = extract_frame(path, 0.0)
            c1,c2 = st.columns([1,3])
            with c1:
                if ai: st.image(ai, width=130, caption="First frame")
                else:  st.caption("\u26a0\ufe0f No frame")
            with c2:
                if ai and not br.get("frame_b64"):
                    br["frame_b64"]=to_b64(ai); br["frame_time"]=0.0
                if br.get("frame_b64"):
                    st.markdown('<div style="color:#34d399;font-size:12px;font-weight:600">\u2705 Frame selected</div>', unsafe_allow_html=True)
                with st.expander("\U0001f3fb Choose different frame", expanded=False):
                    dur = br.get("duration",60.0)
                    ft = st.slider("", 0.0, max(0.1,dur-0.1), float(br.get("frame_time",0.0)),
                                   0.5, format="%.1f s", label_visibility="collapsed", key=f"sl_{idx}")
                    if abs(ft-br.get("frame_time",0.0))>0.09:
                        br["frame_time"]=ft; st.rerun()
                    cfb = extract_frame(path, ft)
                    if cfb:
                        st.image(cfb, width=120, caption=f"@ {ft:.1f}s")
                        if st.button("\u2705 Use", key=f"ucf_{idx}", use_container_width=True):
                            br["frame_b64"]=to_b64(cfb); br["frame_time"]=ft; st.rerun()
            st.markdown("---")

    if st.button("\u2728 Generate All Faceswaps \u2192", type="primary",
                 use_container_width=True, disabled=not all_framed):
        st.session_state.step=3; st.rerun()
    if not all_framed: st.caption("\u26a0\ufe0f All reels need a frame selected")
    st.markdown("<div style='height:6px'/>", unsafe_allow_html=True)
    if st.button("\u2190 Back to Discovery", use_container_width=True):
        st.session_state.step=1; st.rerun()

def render_review():
    batch = st.session_state.batch_reels
    needs_swap = [br for br in batch
                  if br.get("frame_b64") and not br.get("swapped_url")
                  and br["status"] not in ("error","faceswapping","done")]
    if needs_swap:
        prog = st.progress(0); ph = st.empty()
        total_app = len([b for b in batch if b.get("frame_b64")])
        done_n = sum(1 for b in batch if b.get("swapped_url"))
        for br in needs_swap:
            br["status"]="faceswapping"
            ph.info(f"\U0001f3ad Faceswapping {done_n+1}/{total_app}: {br['author']}")
            try:
                base_p = st.session_state.face_swap_prompt
                extra  = br.get("custom_prompt","").strip()
                full_p = (base_p+" "+extra).strip() if extra else base_p
                pid = ws_submit(QWEN_MODEL, {
                    "images": [to_b64(st.session_state.creator_bytes), br["frame_b64"]],
                    "prompt": full_p, "seed": -1})
                res = ws_poll(pid, timeout=240)
                br["swapped_url"]=res; br["status"]="reviewing"
            except Exception as e:
                br["status"]="error"; br["error"]=str(e)[:120]
            done_n+=1; prog.progress(done_n/total_app)
        prog.empty(); ph.empty(); st.rerun()

    st.markdown(f"**\U0001f5bc\ufe0f Review Faceswaps \u2014 {len(batch)} reel(s)**")
    for br in batch:
        idx = br["idx"]
        st.markdown(f"**#{idx+1} \u00b7 {br['author']}**")
        if br["status"]=="error":
            st.error(f"\u274c {br['error']}"); st.markdown("---"); continue
        if not br.get("swapped_url"):
            st.info("\u23f3 Generating faceswap..."); st.markdown("---"); continue
        c1,c2 = st.columns([1,1.6])
        with c1:
            st.image(br["swapped_url"], width=200, caption="\u2728 Faceswap")
        with c2:
            _cp = st.text_input("\u270f\ufe0f Custom addition (optional)",
                value=br.get("custom_prompt",""),
                placeholder="e.g. make hair blonde\u2026",
                key=f"cp_{idx}")
            br["custom_prompt"]=_cp
            ca,cb = st.columns(2)
            with ca:
                if st.button("\U0001f504 Regen", key=f"rg_{idx}", use_container_width=True):
                    br["swapped_url"]=None; br["status"]="ready"; st.rerun()
            with cb:
                approved = br.get("approved",False)
                if st.button("\u2705 Approved" if approved else "\u2610 Approve",
                             key=f"ap_{idx}", use_container_width=True,
                             type="secondary" if approved else "primary"):
                    br["approved"]=not approved; st.rerun()
        st.markdown("---")

    c1,c2 = st.columns(2)
    with c1:
        if st.button("\u2705 Approve All", use_container_width=True):
            for br in batch:
                if br.get("swapped_url"): br["approved"]=True
            st.rerun()
    with c2:
        any_ok = any(br.get("approved") for br in batch)
        if st.button("\U0001f3ac Generate Videos \u2192", type="primary",
                     use_container_width=True, disabled=not any_ok):
            st.session_state.step=4; st.rerun()
    st.markdown("<div style='height:6px'/>", unsafe_allow_html=True)
    if st.button("\u2190 Back to Frames", use_container_width=True):
        st.session_state.step=2; st.rerun()

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
                "prompt": (st.session_state.face_swap_prompt + " " + st.session_state.get("_custom_prompt_add","")).strip(),
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
def _scrub_video(input_path: str, idx: int) -> str:
    """Run FFmpeg scrub & clean on a video file. Returns output path or raises."""
    output_path = f"/tmp/twhales_scrubbed_{idx}.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "noise=c0s=12:c0f=t",
        "-map_metadata", "-1",
        "-bitexact",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="ignore")[-600:])
    return output_path


def _scrub_video(input_path, idx):
    """FFmpeg Scrub & Clean: film grain + strip metadata + remove C2PA."""
    import shutil
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    output_path = f"/tmp/twhales_scrubbed_{idx}.mp4"
    cmd = [
        ffmpeg_bin, "-y", "-i", input_path,
        "-vf", "noise=c0s=12:c0f=t",
        "-map_metadata", "-1",
        "-bitexact",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="ignore")[-600:])
    return output_path


def render_final():
    batch = st.session_state.batch_reels
    to_gen = [br for br in batch
              if br.get("approved") and not br.get("final_url")
              and br["status"] not in ("error",)]
    if to_gen:
        prog=st.progress(0); ph=st.empty()
        total_g=len(to_gen); done_n=0
        for br in to_gen:
            ph.info(f"\U0001f3ac Generating {done_n+1}/{total_g}: {br['author']}")
            try:
                with open(br["video_path"],"rb") as vf:
                    vb64 = to_b64(vf.read(),"video/mp4")
                pid = ws_submit(KLING_MODEL, {
                    "image": br["swapped_url"], "video": vb64,
                    "character_orientation": "video",
                    "prompt": st.session_state.video_prompt})
                res = ws_poll(pid, timeout=360)
                br["final_url"]=res; br["status"]="done"
                st.session_state.pipeline_runs+=1
            except Exception as e:
                br["status"]="error"; br["error"]=str(e)[:120]
            done_n+=1; prog.progress(done_n/total_g)
        prog.empty(); ph.empty(); st.rerun()

    st.markdown("**\U0001f389 Final Videos**")
    done_reels = [br for br in batch if br.get("final_url")]

    for br in done_reels:
        idx = br["idx"]
        st.markdown(f"**#{idx+1} \u00b7 {br['author']}**")
        scrubbed = br.get("scrubbed_path")
        c1, c2 = st.columns([2, 1])
        with c1:
            if scrubbed and os.path.exists(scrubbed):
                st.video(scrubbed)
            else:
                st.video(br["final_url"])
        with c2:
            if scrubbed and os.path.exists(scrubbed):
                with open(scrubbed, "rb") as _sf:
                    st.download_button("\u2b07\ufe0f Download Scrubbed", data=_sf.read(),
                        file_name=f"twhales_clean_{idx+1}.mp4", mime="video/mp4",
                        use_container_width=True, key=f"dl_s_{idx}")
                st.success("\u2705 \u039a\u03b1\u03b8\u03b1\u03c1\u03cc & \u03ad\u03c4\u03bf\u03b9\u03bc\u03bf!")
            else:
                try:
                    import requests as _rq
                    _vb = _rq.get(br["final_url"], timeout=30).content
                    st.download_button("\u2b07\ufe0f Download MP4", data=_vb,
                        file_name=f"twhales_{idx+1}.mp4", mime="video/mp4",
                        use_container_width=True, key=f"dl_{idx}")
                except Exception:
                    st.markdown(f"[\u2b07\ufe0f Download]({br['final_url']})")
        st.markdown("---")

    for br in batch:
        if br["status"] == "error" and br.get("approved"):
            st.error(f"\u274c #{br['idx']+1}: {br['error']}")

    if done_reels:
        st.markdown("---")
        st.markdown("### \U0001f9fc T-WHALES Digital Scrubbing & Cleaning")
        with st.expander("\u0393\u03b9\u03b1\u03c4\u03af \u03b5\u03af\u03bd\u03b1\u03b9 \u03b1\u03c0\u03b1\u03c1\u03b1\u03af\u03c4\u03b7\u03c4\u03bf \u03b1\u03c5\u03c4\u03cc;"):
            st.markdown(
                "\u039c\u03b5 \u03c4\u03b9\u03c2 \u03b5\u03bd\u03c4\u03bf\u03bb\u03ad\u03c2 \u03c0\u03bf\u03c5 \u03c7\u03c1\u03b7\u03c3\u03b9\u03bc\u03bf\u03c0\u03bf\u03b9\u03bf\u03cd\u03bc\u03b5 \u03bc\u03ad\u03c3\u03c9 \u03c4\u03bf\u03c5 FFmpeg, "
                "\u03c0\u03b5\u03c4\u03c5\u03c7\u03b1\u03af\u03bd\u03b5\u03b9\u03c2 \u03ad\u03bd\u03b1\u03bd \u03c0\u03bb\u03ae\u03c1\u03b7 \u00ab\u03c8\u03b7\u03c6\u03b9\u03b1\u03ba\u03cc \u03ba\u03b1\u03b8\u03b1\u03c1\u03b9\u03c3\u03bc\u03cc\u00bb "
                "\u03c4\u03bf\u03c5 \u03c0\u03b5\u03c1\u03b9\u03b5\u03c7\u03bf\u03bc\u03ad\u03bd\u03bf\u03c5 \u03c3\u03bf\u03c5. \u0397 \u03c7\u03c1\u03ae\u03c3\u03b7 \u03b1\u03c5\u03c4\u03ae\u03c2 \u03c4\u03b7\u03c2 \u03b4\u03b9\u03b1\u03b4\u03b9\u03ba\u03b1\u03c3\u03af\u03b1\u03c2 "
                "\u03b5\u03af\u03bd\u03b1\u03b9 \u03ba\u03c1\u03af\u03c3\u03b9\u03bc\u03b7 \u03b3\u03b9\u03b1 \u03c4\u03b7 \u03b4\u03b9\u03b1\u03c7\u03b5\u03af\u03c1\u03b9\u03c3\u03b7 \u03c0\u03b5\u03c1\u03b9\u03b5\u03c7\u03bf\u03bc\u03ad\u03bd\u03bf\u03c5 \u03c3\u03c4\u03b1 social media "
                "\u03ba\u03b1\u03b9 \u03b3\u03b9\u03b1 \u03c4\u03b7\u03bd \u03b1\u03c0\u03bf\u03c6\u03c5\u03b3\u03ae \u03c0\u03b5\u03c1\u03b9\u03bf\u03c1\u03b9\u03c3\u03bc\u03ce\u03bd \u03b1\u03c0\u03cc \u03b1\u03bb\u03b3\u03cc\u03c1\u03b9\u03b8\u03bc\u03bf\u03c5\u03c2 \u03b1\u03bd\u03af\u03c7\u03bd\u03b5\u03c5\u03c3\u03b7\u03c2. "
                "\u0391\u03bd\u03b1\u03bb\u03c5\u03c4\u03b9\u03ba\u03ac:\n\n"
                "* **\u0391\u03c0\u03cc\u03ba\u03c1\u03c5\u03c8\u03b7 \u03a8\u03b7\u03c6\u03b9\u03b1\u03ba\u03bf\u03cd \u0391\u03c0\u03bf\u03c4\u03c5\u03c0\u03ce\u03bc\u03b1\u03c4\u03bf\u03c2 (Fingerprint Scrubbing):** "
                "\u0397 \u03b5\u03bd\u03c4\u03bf\u03bb\u03ae `noise=c0s=12:c0f=t` \u03c0\u03c1\u03bf\u03c3\u03b8\u03ad\u03c4\u03b5\u03b9 \u03b1\u03bd\u03b5\u03c0\u03b1\u03af\u03c3\u03b8\u03b7\u03c4\u03bf \u03b8\u03cc\u03c1\u03c5\u03b2\u03bf. "
                "\u0391\u03c5\u03c4\u03cc \u03b1\u03bb\u03bb\u03ac\u03b6\u03b5\u03b9 \u03bc\u03b1\u03b8\u03b7\u03bc\u03b1\u03c4\u03b9\u03ba\u03ac \u03c4\u03b1 \u03b4\u03b5\u03b4\u03bf\u03bc\u03ad\u03bd\u03b1 \u03ba\u03ac\u03b8\u03b5 pixel, "
                "\u03ba\u03b1\u03b8\u03b9\u03c3\u03c4\u03ce\u03bd\u03c4\u03b1\u03c2 \u03b1\u03b4\u03cd\u03bd\u03b1\u03c4\u03bf \u03b3\u03b9\u03b1 \u03c4\u03bf\u03c5\u03c2 \u03b1\u03bb\u03b3\u03cc\u03c1\u03b9\u03b8\u03bc\u03bf\u03c5\u03c2 \u03bd\u03b1 \u03b1\u03bd\u03b1\u03b3\u03bd\u03c9\u03c1\u03af\u03c3\u03bf\u03c5\u03bd \u03c4\u03bf \u03b2\u03af\u03bd\u03c4\u03b5\u03bf \u03c9\u03c2 \u03b1\u03bd\u03c4\u03af\u03b3\u03c1\u03b1\u03c6\u03bf.\n"
                "* **\u03a0\u03bb\u03ae\u03c1\u03b7\u03c2 \u0391\u03c6\u03b1\u03af\u03c1\u03b5\u03c3\u03b7 \u039c\u03b5\u03c4\u03b1\u03b4\u03b5\u03b4\u03bf\u03bc\u03ad\u03bd\u03c9\u03bd (Metadata Removal):** "
                "\u039c\u03b5 \u03c4\u03bf `-map_metadata -1`, \u03b4\u03b9\u03b1\u03b3\u03c1\u03ac\u03c6\u03bf\u03bd\u03c4\u03b1\u03b9 \u03cc\u03bb\u03b5\u03c2 \u03bf\u03b9 \u03ba\u03c1\u03c5\u03c6\u03ad\u03c2 \u03c0\u03bb\u03b7\u03c1\u03bf\u03c6\u03bf\u03c1\u03af\u03b5\u03c2 (EXIF data, \u03b7\u03bc\u03b5\u03c1\u03bf\u03bc\u03b7\u03bd\u03af\u03b1, \u03ba\u03ac\u03bc\u03b5\u03c1\u03b1, GPS).\n"
                "* **\u0391\u03c0\u03b5\u03bd\u03b5\u03c1\u03b3\u03bf\u03c0\u03bf\u03af\u03b7\u03c3\u03b7 \u03a8\u03b7\u03c6\u03b9\u03b1\u03ba\u03ce\u03bd \u03a0\u03b9\u03c3\u03c4\u03bf\u03c0\u03bf\u03b9\u03b7\u03c4\u03b9\u03ba\u03ce\u03bd (C2PA):** "
                "\u0391\u03c6\u03b1\u03b9\u03c1\u03bf\u03cd\u03bd\u03c4\u03b1\u03b9 \u03c4\u03b1 \u03c0\u03c1\u03cc\u03c3\u03b8\u03b5\u03c4\u03b1 \u03b4\u03b5\u03b4\u03bf\u03bc\u03ad\u03bd\u03b1 \u03c0\u03c1\u03bf\u03ad\u03bb\u03b5\u03c5\u03c3\u03b7\u03c2 \u03bc\u03b5 \u03c4\u03bf `-bitexact`.\n"
                "* **\u0392\u03b5\u03bb\u03c4\u03b9\u03c3\u03c4\u03bf\u03c0\u03bf\u03af\u03b7\u03c3\u03b7 \u03b3\u03b9\u03b1 \u03c4\u03bf T-WHALES \U0001f40b:** "
                "\u0395\u03be\u03b1\u03c3\u03c6\u03b1\u03bb\u03af\u03b6\u03b5\u03b9 \u03cc\u03c4\u03b9 \u03c4\u03bf \u03c5\u03bb\u03b9\u03ba\u03cc \u03b5\u03af\u03bd\u03b1\u03b9 '\u03c6\u03c1\u03ad\u03c3\u03ba\u03bf' \u03ba\u03b1\u03b9 \u03c0\u03b5\u03c1\u03bd\u03ac \u03b1\u03c0\u03c1\u03cc\u03c3\u03ba\u03bf\u03c0\u03c4\u03b1 \u03c4\u03b1 \u03c6\u03af\u03bb\u03c4\u03c1\u03b1 \u03c0\u03c1\u03bf\u03c3\u03c4\u03b1\u03c3\u03af\u03b1\u03c2."
            )

        for br in done_reels:
            if not br.get("local_final_path"):
                try:
                    import requests as _rq2
                    _r2 = _rq2.get(br["final_url"], timeout=60)
                    _lp = f"/tmp/twhales_final_{br['idx']}.mp4"
                    with open(_lp, "wb") as _f2: _f2.write(_r2.content)
                    br["local_final_path"] = _lp
                except Exception:
                    br["local_final_path"] = None

        all_scrubbed = all(br.get("scrubbed_path") for br in done_reels)
        can_scrub = any(br.get("local_final_path") and not br.get("scrubbed_path") for br in done_reels)

        if not all_scrubbed:
            if st.button("\U0001f9fc Run Scrub & Clean \U0001f40b", type="primary", use_container_width=True, disabled=not can_scrub):
                with st.spinner("\U0001f9fc Scrubbing & Cleaning all videos..."):
                    for br in done_reels:
                        _lp2 = br.get("local_final_path")
                        if _lp2 and os.path.exists(_lp2) and not br.get("scrubbed_path"):
                            try:
                                br["scrubbed_path"] = _scrub_video(_lp2, br["idx"])
                            except Exception as _se:
                                st.error(f"\u274c FFmpeg error #{br['idx']+1}: {_se}")
                st.rerun()
        else:
            st.success("\u2705 \u03a4\u03bf \u03b2\u03af\u03bd\u03c4\u03b5\u03bf \u03b5\u03af\u03bd\u03b1\u03b9 \u03ba\u03b1\u03b8\u03b1\u03c1\u03cc \u03ba\u03b1\u03b9 \u03ad\u03c4\u03bf\u03b9\u03bc\u03bf!")

        st.markdown("<div style='height:10px'/>", unsafe_allow_html=True)
        if st.button("\U0001f504 Start New Batch", type="primary", use_container_width=True):
            st.session_state.batch_reels = []; st.session_state.step = 1; st.rerun()
    else:
        if st.button("\u2190 Back to Review", use_container_width=True):
            st.session_state.step = 3; st.rerun()

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
