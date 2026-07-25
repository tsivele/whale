"""
discovery.py — T-WHALES auto-Discovery pipeline

Finds high-potential (likely-viral) solo-creator Reels in a niche, straight
from seed accounts — no manual URLs.

FLOW:  seeds → related accounts + hashtags → pull Reels → VIRALITY score
       → DURATION filter (5-15s) → VISION filter (solo / lighting / no podcast)
       → clean list of reel URLs ready for the existing download pipeline.

APIs used:
  • HikerAPI (Instagram data)  — key = x-access-key header (same as app.py)
  • A vision LLM (OpenAI gpt-4o-mini by default, or Gemini 1.5 Flash) for framing

All thresholds live in CONFIG below — tune them freely. Every network call is
defensive: one bad account/clip never crashes the batch.
"""

import time
import json
import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — tune here
# ─────────────────────────────────────────────────────────────────────────────

HIKER_BASE = "https://api.hikerapi.com"

SEED_ACCOUNTS = [
    "irooxzo", "jenephiebaby", "katerina_pavx", "natalakiiiii", "iroulakass",
    "rena.trela", "wild_mommy_", "marilialuvv", "katerina.urfav",
    "itsalexandraluv", "kasounitsa",
]

# Level A — metadata
MIN_DURATION = 5.0      # seconds (inclusive)
MAX_DURATION = 15.0     # seconds (inclusive)

# Virality thresholds (heuristic — tune to your niche)
VIEW_RATIO_VIRAL   = 2.0    # views ≥ 2× followers → viral candidate
VIEW_RATIO_FULL    = 5.0    # views ≥ 5× followers → max score on this axis
VELOCITY_FULL      = 300.0  # (likes+comments)/hour that scores full
ENGAGEMENT_FULL    = 0.06   # (likes+comments)/views = 6% scores full
MIN_SCORE_KEEP     = 45.0   # drop clips below this before the (paid) vision step

# Crawl budget (each call costs HikerAPI credits — keep these sane)
MAX_ACCOUNTS       = 25     # seeds + related, total
MAX_CLIPS_ACCOUNT  = 12     # newest/top reels pulled per account
MAX_VISION_CHECKS  = 40     # cap the (paid) vision calls per run

VISION_PROMPT = (
    "You are a strict content QA for short vertical Reels. Look at the frame(s) "
    "and return ONLY a compact JSON object with these boolean keys: "
    '{"is_solo": <exactly one person visible>, '
    '"good_lighting": <bright, well-exposed, not dark/underexposed, not blurry>, '
    '"is_podcast": <podcast / interview / studio-desk / split-screen / 2+ people>, '
    '"pass": <true ONLY if is_solo AND good_lighting AND NOT is_podcast>}. '
    "No prose, JSON only."
)


class DiscoveryError(RuntimeError):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# HikerAPI client
# ─────────────────────────────────────────────────────────────────────────────

def _hiker_get(path: str, params: dict, key: str, timeout: int = 30) -> dict:
    """One GET against HikerAPI. Returns parsed JSON (dict) or raises."""
    r = requests.get(
        f"{HIKER_BASE}{path}",
        params=params,
        headers={"x-access-key": key, "accept": "application/json"},
        timeout=timeout,
    )
    if r.status_code == 401:
        raise DiscoveryError("HikerAPI 401 — λάθος access key")
    if r.status_code == 402:
        raise DiscoveryError("HikerAPI 402 — τελείωσαν τα credits")
    r.raise_for_status()
    return r.json()


def get_user(username: str, key: str) -> dict:
    """/v2/user/by/username → {user_id, username, follower_count}."""
    data = _hiker_get("/v2/user/by/username", {"username": username}, key)
    u = data.get("user") or data.get("data") or data
    return {
        "user_id": str(u.get("pk") or u.get("id") or u.get("pk_id") or ""),
        "username": u.get("username") or username,
        "follower_count": int(u.get("follower_count") or 0),
    }


def get_related_users(user_id: str, key: str) -> list:
    """/v2/user/suggested/profiles → similar accounts in the same niche."""
    try:
        data = _hiker_get("/v2/user/suggested/profiles",
                          {"user_id": user_id, "expand_suggestion": "true"}, key)
    except Exception:
        return []
    users = (data.get("users") or data.get("suggested") or
             data.get("data") or [])
    out = []
    for u in users if isinstance(users, list) else []:
        uid = str(u.get("pk") or u.get("id") or "")
        if uid:
            out.append({"user_id": uid,
                        "username": u.get("username") or "",
                        "follower_count": int(u.get("follower_count") or 0)})
    return out


def get_user_clips(user_id: str, key: str, amount: int = MAX_CLIPS_ACCOUNT) -> list:
    """/v2/user/clips → newest Reels for a user. Returns raw media dicts.
    (Alternative: /gql/user/clips?sort_by_views=true for view-sorted.)"""
    out, page_id = [], None
    while len(out) < amount:
        params = {"user_id": user_id}
        if page_id:
            params["page_id"] = page_id
        try:
            data = _hiker_get("/v2/user/clips", params, key)
        except Exception:
            break
        items = _media_items(data)
        if not items:
            break
        out.extend(items)
        page_id = data.get("next_page_id") or data.get("page_id")
        if not page_id:
            break
    return out[:amount]


def get_hashtag_top(name: str, key: str, amount: int = 20) -> list:
    """/v2/hashtag/medias/top → top medias for a hashtag."""
    try:
        data = _hiker_get("/v2/hashtag/medias/top",
                          {"name": name.lstrip("#")}, key)
    except Exception:
        return []
    return _media_items(data)[:amount]


def _media_items(data: dict) -> list:
    """Pull the media list out of the many shapes HikerAPI v2 can return."""
    if isinstance(data, list):
        return data
    for k in ("items", "medias", "response", "data"):
        v = data.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for kk in ("items", "medias"):
                if isinstance(v.get(kk), list):
                    return v[kk]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Clip normalisation + virality
# ─────────────────────────────────────────────────────────────────────────────

def parse_clip(media: dict, fallback_followers: int = 0) -> dict:
    """Normalise a raw HikerAPI media dict into the fields we score on."""
    m = media.get("media") if isinstance(media.get("media"), dict) else media
    code = m.get("code") or m.get("shortcode") or ""
    user = m.get("user") or {}
    followers = int(user.get("follower_count") or fallback_followers or 0)
    views = int(m.get("play_count") or m.get("ig_play_count")
                or m.get("view_count") or 0)
    thumb = ""
    iv = m.get("image_versions2") or {}
    cands = iv.get("candidates") if isinstance(iv, dict) else None
    if cands:
        thumb = cands[0].get("url", "")
    vids = m.get("video_versions") or []
    video_url = vids[0].get("url", "") if vids else ""
    return {
        "code": code,
        "url": f"https://www.instagram.com/reel/{code}/" if code else "",
        "username": user.get("username") or "",
        "follower_count": followers,
        "duration": float(m.get("video_duration") or 0.0),
        "views": views,
        "likes": int(m.get("like_count") or 0),
        "comments": int(m.get("comment_count") or 0),
        "taken_at": int(m.get("taken_at") or 0),
        "is_video": (m.get("media_type") == 2) or bool(video_url),
        "thumbnail_url": thumb,
        "video_url": video_url,
    }


def passes_duration(clip: dict) -> bool:
    """Level A: keep ONLY 5s ≤ duration ≤ 15s."""
    return MIN_DURATION <= clip.get("duration", 0.0) <= MAX_DURATION


def virality_score(clip: dict, now: float = None) -> dict:
    """0-100 score + component breakdown + is_viral flag.
    Axes: view/follower ratio (50%), engagement velocity (30%),
    engagement rate (20%)."""
    now = now or time.time()
    followers = max(clip.get("follower_count", 0), 1)
    views = max(clip.get("views", 0), 0)
    inter = clip.get("likes", 0) + clip.get("comments", 0)
    age_h = max((now - clip.get("taken_at", now)) / 3600.0, 1.0)

    view_ratio      = views / followers
    velocity        = inter / age_h
    engagement_rate = (inter / views) if views else 0.0

    r_norm = min(view_ratio / VIEW_RATIO_FULL, 1.0)
    v_norm = min(velocity / VELOCITY_FULL, 1.0)
    e_norm = min(engagement_rate / ENGAGEMENT_FULL, 1.0)
    score = round(100 * (0.50 * r_norm + 0.30 * v_norm + 0.20 * e_norm), 1)

    return {
        "score": score,
        "is_viral": view_ratio >= VIEW_RATIO_VIRAL,
        "view_ratio": round(view_ratio, 2),
        "velocity_per_h": round(velocity, 1),
        "engagement_rate": round(engagement_rate, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Level B — Vision framing filter
# ─────────────────────────────────────────────────────────────────────────────

def vision_check(image_urls, api_key: str, provider: str = "openai",
                 model: str = None) -> dict:
    """Send 1-2 frames (URLs) to a vision LLM; return
    {is_solo, good_lighting, is_podcast, pass}. Never raises — on any error
    returns pass=False with an 'error' field so the clip is simply skipped."""
    if isinstance(image_urls, str):
        image_urls = [image_urls]
    image_urls = [u for u in image_urls if u][:2]
    if not image_urls:
        return {"pass": False, "error": "no frame url"}
    try:
        if provider == "gemini":
            return _vision_gemini(image_urls, api_key, model or "gemini-1.5-flash")
        return _vision_openai(image_urls, api_key, model or "gpt-4o-mini")
    except Exception as e:
        return {"pass": False, "error": str(e)[:200]}


def _vision_openai(image_urls, api_key, model) -> dict:
    content = [{"type": "text", "text": VISION_PROMPT}]
    for u in image_urls:
        content.append({"type": "image_url", "image_url": {"url": u, "detail": "low"}})
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": content}],
              "response_format": {"type": "json_object"}, "max_tokens": 120,
              "temperature": 0},
        timeout=45,
    )
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"]
    return _coerce_verdict(json.loads(txt))


def _vision_gemini(image_urls, api_key, model) -> dict:
    # Gemini wants inline base64; fetch the frames then send.
    import base64
    parts = [{"text": VISION_PROMPT}]
    for u in image_urls:
        img = requests.get(u, timeout=20).content
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(img).decode()}})
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json={"contents": [{"parts": parts}],
              "generationConfig": {"response_mime_type": "application/json",
                                   "temperature": 0}},
        timeout=45,
    )
    r.raise_for_status()
    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _coerce_verdict(json.loads(txt))


def _coerce_verdict(v: dict) -> dict:
    def b(x):
        return bool(x) if isinstance(x, bool) else str(x).strip().lower() in ("true", "1", "yes")
    is_solo = b(v.get("is_solo"))
    good = b(v.get("good_lighting"))
    podcast = b(v.get("is_podcast"))
    return {
        "is_solo": is_solo, "good_lighting": good, "is_podcast": podcast,
        "pass": bool(v.get("pass")) if "pass" in v else (is_solo and good and not podcast),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def discover(hiker_key: str, vision_key: str = None, vision_provider: str = "openai",
             seeds: list = None, hashtags: list = None,
             use_vision: bool = True, progress_cb=None) -> list:
    """Run the full pipeline. Returns a list of passing clips (dicts with url,
    score, virality breakdown, vision verdict), sorted by score desc.

    progress_cb(stage: str, done: int, total: int) is optional."""
    seeds = seeds or SEED_ACCOUNTS
    hashtags = hashtags or []

    def _note(stage, done=0, total=0):
        if progress_cb:
            try: progress_cb(stage, done, total)
            except Exception: pass

    # 1) resolve seeds → user_id/followers, gather a pool of accounts
    accounts = {}   # user_id → {username, follower_count}
    for i, name in enumerate(seeds):
        _note("seeds", i + 1, len(seeds))
        try:
            u = get_user(name, hiker_key)
            if u["user_id"]:
                accounts[u["user_id"]] = u
        except Exception:
            continue

    # 2) expand with related/suggested accounts
    for uid in list(accounts.keys()):
        if len(accounts) >= MAX_ACCOUNTS:
            break
        for rel in get_related_users(uid, hiker_key):
            if rel["user_id"] and rel["user_id"] not in accounts:
                accounts[rel["user_id"]] = rel
                if len(accounts) >= MAX_ACCOUNTS:
                    break
    _note("accounts", len(accounts), len(accounts))

    # 3) pull clips from every account + hashtags
    raw = []
    accs = list(accounts.values())[:MAX_ACCOUNTS]
    for i, acc in enumerate(accs):
        _note("clips", i + 1, len(accs))
        for m in get_user_clips(acc["user_id"], hiker_key):
            raw.append((m, acc["follower_count"]))
    for tag in hashtags:
        for m in get_hashtag_top(tag, hiker_key):
            raw.append((m, 0))

    # 4) normalise → duration filter → virality score
    scored = []
    seen = set()
    for m, fb_followers in raw:
        c = parse_clip(m, fb_followers)
        if not c["url"] or c["code"] in seen:
            continue
        seen.add(c["code"])
        if not c["is_video"] or not passes_duration(c):
            continue
        vir = virality_score(c)
        c.update(vir)
        if c["score"] >= MIN_SCORE_KEEP:
            scored.append(c)
    scored.sort(key=lambda x: x["score"], reverse=True)

    # 5) vision framing filter on the strongest candidates
    results = []
    if use_vision and vision_key:
        for i, c in enumerate(scored[:MAX_VISION_CHECKS]):
            _note("vision", i + 1, min(len(scored), MAX_VISION_CHECKS))
            verdict = vision_check(c.get("thumbnail_url"), vision_key, vision_provider)
            c["vision"] = verdict
            if verdict.get("pass"):
                results.append(c)
    else:
        results = scored   # vision disabled → return scored candidates as-is

    return results
