"""
cost_engine.py — T-WHALES API Cost Engine

Central source of truth for per-generation video costs, so the UI can show
what each video costs, advise Quality-vs-Price, and total the session spend.

⚠️ PLACEHOLDER PRICES — update MODEL_COST with your real WaveSpeed per-call
   prices whenever you have them. Everything else derives from this dict.
"""

# Cost in USD per successful video generation call.
# Real WaveSpeed prices (confirmed 2026-07-16 from the model pages).
MODEL_COST = {
    "kling":    0.84,    # kwaivgi/kling-v3.0-pro/motion-control
    "seedance": 0.675,   # bytedance/seedance-2.0/video-edit (discounted from 0.75)
}

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
