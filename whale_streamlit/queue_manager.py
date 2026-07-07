"""
queue_manager.py — T-WHALES Batch Orchestrator

Accepts a multiline string of Instagram URLs (copy-paste from UI) and runs
every URL through the full pipeline:
  Generation → Scrub (processor.py) → Verify (safety_filter.py)

Design principles
-----------------
- Decoupled: queue_manager knows nothing about HOW videos are generated.
  The caller passes a `generate_fn` callable — this keeps the orchestrator
  independent of Wavespeed, Streamlit state, or any specific API.
- Fault-isolated: each URL runs inside its own try/except. One failure
  never crashes the rest of the batch.
- Transparent: every stage logs exactly what happened and why.
"""

import logging
import os
from typing import Callable, Dict, List, Optional, Union

log = logging.getLogger("queue_manager")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# URL Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_url_text(raw_text: str) -> List[str]:
    """
    Parse a multiline string of URLs (from st.text_area copy-paste).

    Rules applied to every line:
      - Strip leading / trailing whitespace (tabs, spaces, \\r)
      - Skip empty lines
      - Skip comment lines starting with '#'

    Example input
    -------------
        https://www.instagram.com/reel/ABC123/
        https://www.instagram.com/reel/DEF456/

        # this line is ignored
        https://www.instagram.com/reel/GHI789/

    Returns
    -------
    ["https://...ABC123/", "https://...DEF456/", "https://...GHI789/"]
    """
    urls: List[str] = []
    for line in raw_text.splitlines():
        url = line.strip()
        if url and not url.startswith("#"):
            urls.append(url)
    log.info("Parsed %d URL(s) from text input", len(urls))
    return urls


def parse_url_file(file_source) -> List[str]:
    """
    Parse a .txt or .csv file — accepts a file path (str/Path) or a
    file-like object (e.g. Streamlit UploadedFile).
    Delegates to parse_url_text after reading the raw content.
    """
    if hasattr(file_source, "read"):
        raw = file_source.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
    else:
        with open(str(file_source), "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()

    # CSV: keep only the first column of every line
    lines = []
    for line in raw.splitlines():
        lines.append(line.split(",", 1)[0] if "," in line else line)
    return parse_url_text("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Batch Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(
    urls: List[str],
    generate_fn: Callable[[str], List[str]],
    quarantine_dir: str = "quarantine",
    progress_cb: Optional[Callable[[int, int, str, str], None]] = None,
) -> Dict:
    """
    Process a pre-parsed list of URLs through the full T-WHALES pipeline.

    Parameters
    ----------
    urls : list[str]
        Clean list of Instagram URLs — use parse_url_text() or
        parse_url_file() to produce this from raw input.
    generate_fn : callable(url: str) -> list[str]
        YOUR generation function. Receives one URL, returns a list of local
        MP4 file paths (1 path for single-creator, 2 for SOFIA+MELINA).
        Must raise an exception on any failure — return value is trusted.
    quarantine_dir : str
        Folder where safety_filter moves files that fail verification.
    progress_cb : callable(current, total, url, stage) | None
        Optional hook for Streamlit progress updates.
        stage ∈ {"generating", "scrubbing", "verifying", "done", "failed"}

    Returns
    -------
    {
        "successful_urls": [{"url": str, "output_paths": list[str]}, ...],
        "failed_urls":     [{"url": str, "stage": str, "reason": str}, ...],
        "summary":         {"total": int, "successful": int, "failed": int}
    }
    """
    from processor import VideoProcessor
    from safety_filter import verify_batch

    total = len(urls)

    if total == 0:
        log.warning("run_batch called with an empty URL list — nothing to process.")
        return {
            "successful_urls": [],
            "failed_urls":     [],
            "summary": {"total": 0, "successful": 0, "failed": 0},
        }

    log.info("═" * 60)
    log.info("T-WHALES BATCH — %d URL(s) queued", total)
    log.info("═" * 60)

    successful: List[Dict] = []
    failed:     List[Dict] = []

    for i, url in enumerate(urls, start=1):
        log.info("─" * 60)
        log.info("[%d/%d] %s", i, total, url)

        # ── Stage 1: Generation ───────────────────────────────────────────
        _notify(progress_cb, i, total, url, "generating")
        try:
            raw_paths = generate_fn(url)
            if not raw_paths:
                raise ValueError("generate_fn returned an empty list")
            if isinstance(raw_paths, str):
                raw_paths = [raw_paths]
            log.info("  [generation] ✓  %d video(s) produced", len(raw_paths))
        except Exception as exc:
            _fail(failed, url, "generation", exc, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        # ── Stage 2: Metadata Scrub ───────────────────────────────────────
        _notify(progress_cb, i, total, url, "scrubbing")
        try:
            scrubbed = VideoProcessor.process(raw_paths)
            if isinstance(scrubbed, str):
                scrubbed = [scrubbed]
            log.info("  [scrub]      ✓  %d file(s) scrubbed", len(scrubbed))
        except Exception as exc:
            _fail(failed, url, "scrub", exc, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        # ── Stage 3: Safety Verification ─────────────────────────────────
        _notify(progress_cb, i, total, url, "verifying")
        try:
            verify_result = verify_batch(scrubbed, quarantine_dir=quarantine_dir)
        except Exception as exc:
            _fail(failed, url, "verify", exc, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        if verify_result["quarantined"]:
            details = "; ".join(
                "{}: [{}]".format(
                    os.path.basename(e["original_path"]),
                    ", ".join(e["violations"].keys()),
                )
                for e in verify_result["quarantined"]
            )
            reason = f"{len(verify_result['quarantined'])} file(s) quarantined — {details}"
            _fail(failed, url, "verify", reason, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        # ── All stages passed ─────────────────────────────────────────────
        log.info("  [verify]     ✓  all clean")
        log.info("  ✅ [%d/%d] SUCCESS — %s", i, total, url)
        successful.append({"url": url, "output_paths": verify_result["approved"]})
        _notify(progress_cb, i, total, url, "done")

    # ── Final report ──────────────────────────────────────────────────────────
    log.info("═" * 60)
    log.info(
        "BATCH COMPLETE — %d/%d successful  |  %d/%d failed",
        len(successful), total, len(failed), total,
    )
    if failed:
        log.warning("Failed URLs:")
        for entry in failed:
            log.warning(
                "  [%s] %s — %s", entry["stage"], entry["url"], entry["reason"]
            )
    log.info("═" * 60)

    return {
        "successful_urls": successful,
        "failed_urls":     failed,
        "summary": {
            "total":      total,
            "successful": len(successful),
            "failed":     len(failed),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fail(
    failed_list: List[Dict],
    url: str,
    stage: str,
    exc_or_msg,
    i: int,
    total: int,
) -> None:
    reason = str(exc_or_msg)
    log.error("  ✗ [%d/%d] stage=%s — %s", i, total, stage, reason)
    failed_list.append({"url": url, "stage": stage, "reason": reason})


def _notify(cb, current, total, url, stage):
    if cb:
        try:
            cb(current, total, url, stage)
        except Exception:
            pass  # progress callbacks must never crash the pipeline
