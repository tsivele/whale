"""
cost_engine.py — T-WHALES API Cost Engine

Real WaveSpeed pricing (confirmed 2026-07-16 from the model pages). Cost is
NOT flat — it scales with the video DURATION, which is why a long clip can
cost many dollars. We compute the exact per-video price from the duration so
the UI shows the true number, not a misleading flat estimate.

SEEDANCE 2.0 video-edit — billed per second on (input + output) duration,
  input clamped to 2–15 s, output = input for video-edit → billed = 2×dur:
      720p  $0.15/s → cost = 0.15 × 2 × dur   (5 s → $1.50, 15 s → $4.50)
      1080p $0.375/s, 480p $0.075/s, 4k $0.75/s
KLING v3 motion-control — tiered by OUTPUT seconds ($0.168/s, min 3 s, 5-s
  blocks): 5 s → $0.84, 10 s → $1.68, 20 s → $3.36.
"""

import math

# Per-second rate by resolution for Seedance video-edit.
SEEDANCE_RATE = {"480p": 0.075, "720p": 0.15, "1080p": 0.375, "4k": 0.750}
SEEDANCE_RES  = "720p"           # the app locks Seedance to 720p
_DUR_MIN, _DUR_MAX = 2.0, 15.0   # WaveSpeed clamps input duration to this range
KLING_OUT_SECONDS = 5            # the app requests 5-s Kling outputs

# Rough per-video reference (used only when duration is unknown).
MODEL_COST = {
    "kling":    0.84,    # 5-s Kling output
    "seedance": 1.50,    # ~5-s 720p video-edit
}


def _clamp(d) -> float:
    try:
        d = float(d)
    except (TypeError, ValueError):
        d = 5.0
    return max(_DUR_MIN, min(_DUR_MAX, d))


def seedance_cost(duration_sec, resolution=SEEDANCE_RES) -> float:
    """Exact Seedance video-edit price: rate × (input+output) = rate × 2 × dur."""
    d = _clamp(duration_sec)
    return round(SEEDANCE_RATE.get(resolution, 0.15) * 2 * d, 2)


KLING_MAX = 30.0   # Kling output length is capped at 30 s (video orientation)


def _clamp_kling(d) -> float:
    try:
        d = float(d)
    except (TypeError, ValueError):
        d = 5.0
    return max(3.0, min(KLING_MAX, d))


def kling_cost(duration_sec=5) -> float:
    """Kling motion-control price — scales with OUTPUT length. Kling has NO
    duration input; the output ≈ the driving reel length (up to 30 s), so we
    estimate from the source duration. $0.168/s, min 3 s, billed in 5-s blocks
    (an upper bound — Kling may return a slightly shorter clip)."""
    d = _clamp_kling(duration_sec)
    if d <= 3:
        return 0.504
    return round(0.168 * (math.ceil(d / 5) * 5), 2)


def estimate_cost(model_key, duration_sec=None) -> float:
    """Accurate per-video cost for a model given the source video duration.
    BOTH models scale with duration (Seedance on 2×dur, Kling on output length)."""
    if model_key == "kling":
        return kling_cost(duration_sec)
    return seedance_cost(duration_sec)


def breakdown(model_key, duration_sec=None) -> str:
    """Short 'analytical' breakdown shown on the card so you see WHY it costs that."""
    if model_key == "kling":
        d = _clamp_kling(duration_sec)
        return f"~{d:.0f}s output (Kling, max 30s)"
    d = _clamp(duration_sec)
    return f"{d:.0f}s ×2 (in+out) @ {SEEDANCE_RES}"

# Human labels (used in the model selector).
MODEL_LABEL = {
    "kling":    "Kling v3 Pro (motion control)",
    "seedance": "Seedance 2.0 Video-Edit (v2v)",
}

# Quality-vs-Cost advisor: (headline, hex color) per model.
MODEL_ADVICE = {
    "kling":    ("Ultra Quality · Ακριβότερο",       "#f87171"),
    "seedance": ("Άριστη ποιότητα · ~20% φθηνότερο", "#4ade80"),
}

DEFAULT_MODEL = "seedance"


def cost_of(model_key) -> float:
    """USD cost for one generation with `model_key` (0 if unknown)."""
    return MODEL_COST.get(model_key or "", 0.0)


def fmt(amount) -> str:
    """Format a USD amount for display."""
    return f"${amount:.2f}"


def advice(model_key):
    """(headline, color) Quality-vs-Cost advisor text for `model_key`."""
    return MODEL_ADVICE.get(model_key, ("—", "#9b8dc4"))


def is_real(item) -> bool:
    """True if WaveSpeed reported the actual charged price for this item."""
    rc = item.get("gen_cost")
    return isinstance(rc, (int, float)) and rc > 0


def cost_of_item(item) -> float:
    """The REAL WaveSpeed price for this item if it was captured, otherwise
    the flat per-model estimate. This is what makes per-video costs accurate
    (the real price scales with duration/resolution, the estimate doesn't)."""
    if is_real(item):
        return float(item["gen_cost"])
    return cost_of(item.get("model_key") or DEFAULT_MODEL)


def session_spend(items) -> float:
    """Total spend across every item that dispatched a paid generation call —
    real price where WaveSpeed reported it, estimate otherwise. Computed live
    from the DB, so it's immediate (gen_pred set at dispatch), self-correcting
    (swaps to the real price when the job finishes), and survives restarts.
    Cancelled/deleted items are gone from the DB, so they never count."""
    total = 0.0
    for it in items:
        if it.get("gen_pred") or it.get("gen_path") or it.get("gen_url"):
            total += cost_of_item(it)
    return round(total, 2)
