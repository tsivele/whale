"""
queue_manager.py — T-WHALES Batch Orchestrator

Reads a .txt / .csv file of Instagram URLs and runs every URL through
the full pipeline: Generation → Scrub (processor.py) → Verify (safety_filter.py).

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
# File Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_url_file(file_source) -> List[str]:
    """
    Parse a .txt or .csv file and return a clean list of URLs.

    Accepts:
      - A file path (str / Path)
      - A file-like object (e.g. Streamlit UploadedFile — has a .read() method)

    Rules:
      - Strips leading/trailing whitespace from every line
      - Skips empty lines
      - Skips comment lines starting with '#'
      - For .csv: takes the first column only (splits on comma)
    """
    lines: List[str] = []

    if hasattr(file_source, "read"):
        # Streamlit UploadedFile or any file-like object
        raw = file_source.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        lines = raw.splitlines()
    else:
        with open(str(file_source), "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

    urls: List[str] = []
    for line in lines:
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        # CSV: take first column
        if "," in url:
            url = url.split(",", 1)[0].strip()
        if url:
            urls.append(url)

    log.info("Parsed %d URL(s) from file", len(urls))
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# Batch Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(
    url_file,
    generate_fn: Callable[[str], List[str]],
    quarantine_dir: str = "quarantine",
    progress_cb: Optional[Callable[[int, int, str, str], None]] = None,
) -> Dict:
    """
    Process a list of URLs through the full T-WHALES pipeline.

    Parameters
    ----------
    url_file : str | Path | UploadedFile
        A .txt or .csv file with one Instagram URL per line.
    generate_fn : callable(url: str) -> list[str]
        YOUR generation function. Receives one URL, returns a list of local
        MP4 file paths (1 path for single-creator, 2 for SOFIA+MELINA).
        Must raise an exception on failure — return value is trusted.
    quarantine_dir : str
        Folder where safety_filter moves files that fail verification.
    progress_cb : callable(current, total, url, stage) | None
        Optional hook for live Streamlit progress updates.
        stage ∈ {"generating", "scrubbing", "verifying", "done", "failed"}

    Returns
    -------
    {
        "successful_urls": [
            {"url": str, "output_paths": list[str]},
            ...
        ],
        "failed_urls": [
            {"url": str, "stage": str, "reason": str},
            ...
        ],
        "summary": {
            "total":      int,
            "successful": int,
            "failed":     int,
        }
    }
    """
    from processor import VideoProcessor
    from safety_filter import verify_batch

    urls  = parse_url_file(url_file)
    total = len(urls)

    if total == 0:
        log.warning("No URLs found in file — nothing to process.")
        return {"successful_urls": [], "failed_urls": [],
                "summary": {"total": 0, "successful": 0, "failed": 0}}

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
            result = verify_batch(scrubbed, quarantine_dir=quarantine_dir)
        except Exception as exc:
            _fail(failed, url, "verify", exc, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        if result["quarantined"]:
            details = "; ".join(
                "{}: [{}]".format(
                    os.path.basename(e["original_path"]),
                    ", ".join(e["violations"].keys()),
                )
                for e in result["quarantined"]
            )
            reason = f"{len(result['quarantined'])} file(s) quarantined — {details}"
            _fail(failed, url, "verify", reason, i, total)
            _notify(progress_cb, i, total, url, "failed")
            continue

        # ── All stages passed ─────────────────────────────────────────────
        log.info("  [verify]     ✓  all clean")
        log.info("  ✅ [%d/%d] SUCCESS — %s", i, total, url)
        successful.append({"url": url, "output_paths": result["approved"]})
        _notify(progress_cb, i, total, url, "done")

    # ── Final Report ──────────────────────────────────────────────────────────
    log.info("═" * 60)
    log.info("BATCH COMPLETE — %d/%d successful  |  %d/%d failed",
             len(successful), total, len(failed), total)
    if failed:
        log.warning("Failed URLs:")
        for entry in failed:
            log.warning("  [%s] %s — %s", entry["stage"], entry["url"], entry["reason"])
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
