import streamlit as st
import requests
import subprocess
import tempfile
import os
import time
import base64

st.set_page_config(page_title="Whale Pipeline", page_icon="🐋", layout="centered")

WS_API = "https://api.wavespeed.ai/api/v3"
HIKER_API  = "https://api.hikerapi.com/v2/media/info/by/url"
APIFY_BASE = "https://api.apify.com/v2"
APIFY_ACTOR = "apify~instagram-reel-scraper"   # Official, free with credits, no rental needed

GRAIN_PROMPT = (
    "Add subtle 1% natural film grain texture across all frames uniformly. "
    "Camera sensor noise, warm tone. Preserve ALL motion, faces, and composition exactly."
)

MODELS = {
    "Seedance 2.0 (γρήγορο)": "seedance",
    "WAN 2.7 (υψηλή ποιότητα)": "wan",
    "Kling v3 Pro (motion control)": "kling",
}

# ──────────────────────────────────────────────────────────
# SESSION STATE
# ──────────────────────────────────────────────────────────
defaults = {
    "step": 0,
    "video_path": None,
    "video_dur": 10.0,
    "frame_options": [],
    "frame_b64": None,
    "swapped_url": None,
    "gen_url": None,
    "final_path": None,
    "model": "Seedance 2.0 (γρήγορο)",
    "ig_url": "",
    "motion_video_path": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ──────────────────────────────────────────────────────────
# KEYS — από Streamlit Secrets (Settings → Secrets στο Cloud)
# ──────────────────────────────────────────────────────────
def get_key(secret_name, label):
    val = st.secrets.get(secret_name, "")
    if val:
        return val
    return st.sidebar.text_input(label, type="password", key=f"k_{secret_name}")


with st.sidebar:
    st.markdown("### ⚙️ Settings")
    WS_KEY = get_key("WAVESPEED_KEY", "Wavespeed API Key")
    HIKER_KEY = get_key("HIKER_KEY", "HikerAPI Key (προαιρετικό)")
    APIFY_KEY = get_key("APIFY_KEY", "Apify Key (backup, προαιρετικό)")

    st.markdown("---")
    st.markdown("**Creator photo**")
    creator_file = st.file_uploader("Upload φωτό", type=["jpg", "jpeg", "png"], key="creator_upload")
    if creator_file:
        st.session_state["creator_bytes"] = creator_file.read()
        st.image(st.session_state["creator_bytes"], width=120)
    elif "creator_bytes" in st.session_state:
        st.image(st.session_state["creator_bytes"], width=120)
        st.caption("✓ Creator photo loaded")

    st.markdown("---")
    if st.button("🔄 Restart pipeline"):
        for k in list(st.session_state.keys()):
            if k != "creator_bytes":
                del st.session_state[k]
        st.rerun()


def to_b64(image_bytes, mime="image/jpeg"):
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


# ──────────────────────────────────────────────────────────
# WAVESPEED HELPERS
# ──────────────────────────────────────────────────────────
def ws_submit(endpoint, payload):
    r = requests.post(
        f"{WS_API}/{endpoint}",
        headers={"Authorization": f"Bearer {WS_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    pred_id = data.get("data", {}).get("id")
    if not pred_id:
        raise RuntimeError(f"Wavespeed: {data}")
    return pred_id


def ws_poll(pred_id, status_box):
    for i in range(150):
        time.sleep(4)
        r = requests.get(
            f"{WS_API}/predictions/{pred_id}/result",
            headers={"Authorization": f"Bearer {WS_KEY}"},
            timeout=30,
        )
        d = r.json().get("data", {})
        status = d.get("status", "running")
        status_box.text(f"⏳ {status}... {(i + 1) * 4}s")
        if status == "completed":
            outputs = d.get("outputs", [])
            return outputs[0] if outputs else None
        if status == "failed":
            raise RuntimeError(d.get("error", "Wavespeed generation failed"))
    raise TimeoutError("Wavespeed timeout (10 λεπτά)")


# ──────────────────────────────────────────────────────────
# INSTAGRAM DOWNLOAD — HikerAPI πρώτα, Apify backup
# ──────────────────────────────────────────────────────────
def hiker_get_video_url(ig_url):
    # Try header first (documented method), then query param fallback
    for attempt, kwargs in [
        ("header", {"headers": {"x-access-key": HIKER_KEY, "accept": "application/json"}}),
        ("param",  {"headers": {"accept": "application/json"}, "params": {"url": ig_url, "access_key": HIKER_KEY}}),
    ]:
        try:
            r = requests.get(
                HIKER_API,
                params={"url": ig_url} if attempt == "header" else None,
                timeout=30,
                **kwargs
            )
            if r.status_code == 401:
                continue  # try next method
            if r.status_code == 404:
                raise RuntimeError("HikerAPI: post δεν βρέθηκε (deleted/private)")
            r.raise_for_status()
            data = r.json()
            candidates = [
                data.get("video_url"),
                (data.get("video_versions") or [{}])[0].get("url"),
                (data.get("media", {}).get("video_versions") or [{}])[0].get("url"),
                ((data.get("items") or [{}])[0].get("video_versions") or [{}])[0].get("url"),
            ]
            for c in candidates:
                if c:
                    return c
            raise RuntimeError(f"HikerAPI: no video URL. Fields: {list(data.keys())}")
        except RuntimeError:
            raise
        except Exception as e:
            continue
    raise RuntimeError("HikerAPI 401: ο access key είναι λάθος. Επιβεβαίωσε το key στο hikerapi.com dashboard.")


def apify_get_video_url(ig_url):
    # Start async run
    r = requests.post(
        f"{APIFY_BASE}/acts/{APIFY_ACTOR}/runs",
        params={"token": APIFY_KEY},
        json={
            "urls": [ig_url],
            "resultsLimit": 1,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        },
        timeout=30,
    )
    if r.status_code == 403:
        raise RuntimeError("Apify 403: ο actor χρειάζεται rental ή ο λογαριασμός δεν έχει πρόσβαση.")
    if r.status_code == 401:
        raise RuntimeError("Apify 401: λάθος API token.")
    r.raise_for_status()

    run_id = r.json()["data"]["id"]
    dataset_id = r.json()["data"]["defaultDatasetId"]

    # Poll for completion (max 3 minutes)
    for i in range(60):
        time.sleep(3)
        st_r = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}", params={"token": APIFY_KEY}, timeout=10)
        status = st_r.json()["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run {status}")

    # Get results
    items_r = requests.get(f"{APIFY_BASE}/datasets/{dataset_id}/items", params={"token": APIFY_KEY}, timeout=15)
    items = items_r.json()
    if not items:
        raise RuntimeError("Apify: κενό αποτέλεσμα (το reel μπορεί να είναι private)")
    item = items[0]

    # apify/instagram-reel-scraper returns 'videoUrl' directly
    video_url = (
        item.get("videoUrl")
        or item.get("video_url")
        or (item.get("videoPlaybackQualityToUrlMap") or {}).get("HD")
        or (item.get("videoPlaybackQualityToUrlMap") or {}).get("SD")
    )
    if not video_url:
        raise RuntimeError(f"Apify: δεν βρέθηκε videoUrl. Fields: {list(item.keys())}")
    return video_url


def download_video_url(url):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


# ──────────────────────────────────────────────────────────
# FFMPEG HELPERS
# ──────────────────────────────────────────────────────────
def get_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except Exception:
        return 10.0


def extract_frame(video_path, timestamp):
    out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path],
        capture_output=True,
    )
    return out_path


def strip_metadata(in_path):
    out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_path, "-map_metadata", "-1", "-c", "copy", out_path],
        capture_output=True,
    )
    return out_path


# ──────────────────────────────────────────────────────────
# UI — STEP BAR
# ──────────────────────────────────────────────────────────
st.title("🐋 Whale Pipeline")
st.caption("AI Video Generation · Cloud · Wavespeed + HikerAPI")

steps = ["Setup", "Download", "Review", "Face Swap", "Video", "Done"]
cols = st.columns(len(steps))
for i, (col, name) in enumerate(zip(cols, steps)):
    with col:
        if i < st.session_state.step:
            st.markdown(f"✅ **{name}**")
        elif i == st.session_state.step:
            st.markdown(f"🔵 **{name}**")
        else:
            st.markdown(f"⚪ {name}")
st.divider()


# ──────────────────────────────────────────────────────────
# STEP 0 — SETUP
# ──────────────────────────────────────────────────────────
if st.session_state.step == 0:
    st.subheader("Βήμα 0 — Ρύθμιση")
    st.write("Βάλε τα API keys στο sidebar (αριστερά) και ανέβασε creator photo.")

    ready = bool(WS_KEY) and (bool(HIKER_KEY) or bool(APIFY_KEY)) and "creator_bytes" in st.session_state

    if not WS_KEY:
        st.warning("⚠️ Χρειάζεσαι Wavespeed API key")
    if not HIKER_KEY and not APIFY_KEY:
        st.warning("⚠️ Χρειάζεσαι HikerAPI ή Apify key (για auto-download)")
    if "creator_bytes" not in st.session_state:
        st.warning("⚠️ Ανέβασε creator photo στο sidebar")

    if st.button("Ξεκίνα Pipeline →", disabled=not ready, type="primary"):
        st.session_state.step = 1
        st.rerun()


# ──────────────────────────────────────────────────────────
# STEP 1 — DOWNLOAD
# ──────────────────────────────────────────────────────────
elif st.session_state.step == 1:
    st.subheader("Βήμα 1 — Κατέβασμα Instagram Video")
    ig_url = st.text_input("Instagram Reel URL", value=st.session_state.ig_url,
                            placeholder="https://www.instagram.com/reel/...")
    st.session_state.ig_url = ig_url

    if st.button("⬇ Download", type="primary", disabled=not ig_url):
        status = st.empty()
        try:
            video_url = None
            if HIKER_KEY:
                status.info("Δοκιμάζω HikerAPI...")
                try:
                    video_url = hiker_get_video_url(ig_url)
                except Exception as e:
                    st.warning(f"HikerAPI: {e}")

            if not video_url and APIFY_KEY:
                status.info("Δοκιμάζω Apify (backup)...")
                video_url = apify_get_video_url(ig_url)

            if not video_url:
                st.error("Δεν βρέθηκε video. Δοκίμασε άλλο link ή έλεγξε τα API keys.")
            else:
                status.info("Κατεβάζω το video...")
                path = download_video_url(video_url)
                st.session_state.video_path = path
                st.session_state.video_dur = get_duration(path)
                # Auto-extract 5 candidate frames
                dur = st.session_state.video_dur
                times = [max(0.3, p * dur) for p in [0.05, 0.2, 0.4, 0.6, 0.8]]
                frames = []
                status.info("Εξάγω frames...")
                for t in times:
                    fp = extract_frame(path, min(t, dur - 0.2))
                    frames.append((t, fp))
                st.session_state.frame_options = frames
                status.empty()
                st.session_state.step = 2
                st.rerun()
        except Exception as e:
            st.error(f"Σφάλμα: {e}")

    if st.button("← Πίσω"):
        st.session_state.step = 0
        st.rerun()


# ──────────────────────────────────────────────────────────
# STEP 2 — REVIEW & FRAME SELECTION
# ──────────────────────────────────────────────────────────
elif st.session_state.step == 2:
    st.subheader("Βήμα 2 — Review & Επιλογή Frame")

    if st.session_state.video_path:
        st.video(st.session_state.video_path)

    st.write("**Auto-extracted frames** — διάλεξε ή πάτα custom timestamp:")
    cols = st.columns(5)
    for i, (t, fp) in enumerate(st.session_state.frame_options):
        with cols[i]:
            st.image(fp, caption=f"{t:.1f}s")
            if st.button("Επιλογή", key=f"frame_{i}"):
                with open(fp, "rb") as f:
                    st.session_state.frame_b64 = to_b64(f.read())
                st.rerun()

    custom_t = st.slider("Ή scrub σε custom χρόνο", 0.0, st.session_state.video_dur, 1.0, 0.1)
    if st.button("📸 Capture custom frame"):
        fp = extract_frame(st.session_state.video_path, custom_t)
        with open(fp, "rb") as f:
            st.session_state.frame_b64 = to_b64(f.read())
        st.rerun()

    if st.session_state.frame_b64:
        st.success("✓ Frame επιλέχθηκε")
        st.image(st.session_state.frame_b64, width=200)
        if st.button("Επόμενο: Face Swap →", type="primary"):
            st.session_state.step = 3
            st.rerun()

    if st.button("← Πίσω"):
        st.session_state.step = 1
        st.rerun()


# ──────────────────────────────────────────────────────────
# STEP 3 — FACE SWAP
# ──────────────────────────────────────────────────────────
elif st.session_state.step == 3:
    st.subheader("Βήμα 3 — Face Swap")

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Viral Frame**")
        st.image(st.session_state.frame_b64)
    with col2:
        st.write("**Creator Photo**")
        st.image(st.session_state["creator_bytes"])

    if not st.session_state.swapped_url:
        if st.button("🎭 Εκτέλεση Face Swap", type="primary"):
            status = st.empty()
            try:
                creator_b64 = to_b64(st.session_state["creator_bytes"])
                pred_id = ws_submit(
                    "wavespeed-ai/qwen-image-2.0-pro/edit",
                    {
                        "images": [creator_b64, st.session_state.frame_b64],
                        "prompt": (
                            "Place the person from image 1 in the scene of image 2, "
                            "same pose and framing. Photorealistic, vertical 9:16, 4K, "
                            "warm cinematic color grading. No text, no watermarks."
                        ),
                        "seed": -1,
                    },
                )
                result = ws_poll(pred_id, status)
                st.session_state.swapped_url = result
                status.empty()
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα: {e}")
    else:
        st.success("👁 Αποτέλεσμα — Εγκρίνεις;")
        st.image(st.session_state.swapped_url)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Εγκρίνω →", type="primary"):
                st.session_state.step = 4
                st.rerun()
        with c2:
            if st.button("✗ Ξανά"):
                st.session_state.swapped_url = None
                st.rerun()

    if st.button("← Πίσω"):
        st.session_state.step = 2
        st.rerun()


# ──────────────────────────────────────────────────────────
# STEP 4 — VIDEO GENERATION
# ──────────────────────────────────────────────────────────
elif st.session_state.step == 4:
    st.subheader("Βήμα 4 — Video Generation")
    st.image(st.session_state.swapped_url, width=300)

    model_label = st.selectbox("Μοντέλο video", list(MODELS.keys()),
                                index=list(MODELS.keys()).index(st.session_state.model))
    st.session_state.model = model_label
    model = MODELS[model_label]

    if model == "kling":
        motion_file = st.file_uploader("Motion reference video (για Kling)", type=["mp4", "mov"])
        if motion_file:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tmp.write(motion_file.read())
            tmp.close()
            st.session_state.motion_video_path = tmp.name
            st.video(tmp.name)

    if not st.session_state.gen_url:
        can_generate = model != "kling" or st.session_state.motion_video_path
        if st.button("🎬 Δημιούργησε Video", type="primary", disabled=not can_generate):
            status = st.empty()
            try:
                prompt = (
                    "Cinematic ambient video. Slow smooth camera push-in. "
                    "Subtle ambient motion, gentle light rays, depth-of-field bokeh. "
                    "Vertical 9:16. No text, no overlays."
                )
                if model == "seedance":
                    pred_id = ws_submit(
                        "bytedance/seedance-2.0/image-to-video",
                        {"image": st.session_state.swapped_url, "prompt": prompt,
                         "duration": 5, "resolution": "1080p", "seed": -1},
                    )
                elif model == "wan":
                    pred_id = ws_submit(
                        "alibaba/wan-2.7/image-to-video",
                        {"image": st.session_state.swapped_url, "prompt": prompt,
                         "duration": 5, "resolution": "1080p", "seed": -1},
                    )
                else:  # kling
                    with open(st.session_state.motion_video_path, "rb") as f:
                        motion_b64 = to_b64(f.read(), mime="video/mp4")
                    pred_id = ws_submit(
                        "kwaivgi/kling-v3.0-pro/motion-control",
                        {"image": st.session_state.swapped_url, "motion_video": motion_b64,
                         "prompt": prompt, "duration": "5", "mode": "pro", "seed": -1},
                    )
                result = ws_poll(pred_id, status)
                st.session_state.gen_url = result
                status.empty()
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα: {e}")
    else:
        st.success("👁 Video — Εγκρίνεις;")
        st.video(st.session_state.gen_url)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Εγκρίνω → Post-Process", type="primary"):
                st.session_state.step = 5
                st.rerun()
        with c2:
            if st.button("✗ Ξανά"):
                st.session_state.gen_url = None
                st.rerun()

    if st.button("← Πίσω"):
        st.session_state.step = 3
        st.rerun()


# ──────────────────────────────────────────────────────────
# STEP 5 — POST-PROCESSING & DONE
# ──────────────────────────────────────────────────────────
elif st.session_state.step == 5:
    st.subheader("Βήμα 5 — Post-Processing")
    st.video(st.session_state.gen_url)

    if not st.session_state.final_path:
        st.write("Auto pipeline: AI watermark removal → film grain → C2PA metadata strip")
        if st.button("🛡 Εκτέλεση Post-Processing", type="primary"):
            status = st.empty()
            try:
                current_url = st.session_state.gen_url

                status.info("Αφαιρώ AI watermarks...")
                try:
                    wid = ws_submit("wavespeed-ai/video-watermark-remover", {"video": current_url})
                    cleaned = ws_poll(wid, status)
                    if cleaned:
                        current_url = cleaned
                except Exception as e:
                    st.warning(f"Watermark removal skipped: {e}")

                status.info("Film grain pass...")
                try:
                    gid = ws_submit(
                        "bytedance/seedance-2.0/video-edit",
                        {"video": current_url, "prompt": GRAIN_PROMPT, "seed": -1},
                    )
                    grained = ws_poll(gid, status)
                    if grained:
                        current_url = grained
                except Exception as e:
                    st.warning(f"Grain pass skipped: {e}")

                status.info("Κατεβάζω για C2PA scrub...")
                local_path = download_video_url(current_url)

                status.info("Αφαιρώ metadata (C2PA scrub)...")
                final_path = strip_metadata(local_path)

                st.session_state.final_path = final_path
                status.empty()
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα: {e}")
    else:
        st.success("🎉 Pipeline ολοκληρώθηκε! Καθαρό από AI marks, C2PA metadata, με film grain.")
        st.video(st.session_state.final_path)
        with open(st.session_state.final_path, "rb") as f:
            st.download_button("⬇ Download Final MP4", f, file_name="whale_final.mp4", mime="video/mp4",
                                type="primary")

        if st.button("🔄 Νέο Video"):
            for k in ["video_path", "video_dur", "frame_options", "frame_b64",
                      "swapped_url", "gen_url", "final_path", "ig_url", "motion_video_path"]:
                st.session_state[k] = defaults[k]
            st.session_state.step = 1
            st.rerun()
