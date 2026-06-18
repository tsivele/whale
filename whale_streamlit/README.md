# 🐋 Whale Pipeline

Cloud-based AI video pipeline: Instagram reel → face swap → AI video generation → anti-detection cleanup.

## Setup στο Streamlit Cloud

1. Πήγαινε στο [share.streamlit.io](https://share.streamlit.io) → Sign in με GitHub
2. **New app** → επίλεξε αυτό το repo → main file: `app.py` → **Deploy**
3. Μετά το πρώτο deploy: app **Settings (⋮) → Secrets** → επικόλλησε:

```toml
WAVESPEED_KEY = "wsk_live_..."
HIKER_KEY = "your-hikerapi-key"
APIFY_KEY = "your-apify-token"
```

4. Save → το app κάνει restart αυτόματα με τα keys σου

## API Keys

- **Wavespeed**: [wavespeed.ai/accesskey](https://wavespeed.ai/accesskey)
- **HikerAPI** (συνιστώμενο, 100 δωρεάν requests): [hikerapi.com](https://hikerapi.com)
- **Apify** (backup, $11.99/μήνα για dedicated downloader): [apify.com](https://apify.com)

## Pipeline

1. **Download** — Instagram reel → HikerAPI (ή Apify backup) → local video file
2. **Review** — auto-extracted frames + custom timestamp scrubber
3. **Face Swap** — Wavespeed Qwen 2.0 Pro Edit, human approval
4. **Video Generation** — Seedance 2.0 / WAN 2.7 / Kling v3 Pro, human approval
5. **Post-Processing** — AI watermark removal + film grain + C2PA metadata strip
