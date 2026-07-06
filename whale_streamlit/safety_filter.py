"""
safety_filter.py — T-WHALES Post-Scrub Verification & Fail-Fast Safety Filter

Acts as the final checkpoint before any video is downloaded or uploaded.
Scans scrubbed MP4 files for leftover metadata using two independent methods:
  1. ffprobe JSON scan  — surfaces named tags in format + stream blocks
  2. Raw binary scan    — detects C2PA/XMP/EXIF signatures that ffprobe
                          does not surface as named tags (hidden atoms,
                          JUMBF boxes, XMP packets embedded in the bytestream)

Usage
-----
    from safety_filter import verify_batch

    result = verify_batch(["sofia_clean.mp4", "melina_clean.mp4"])
    # result = {
    #   "approved":    ["sofia_clean.mp4"],
    #   "quarantined": [{"original_path": "melina_clean.mp4",
    #                    "quarantine_path": "quarantine/melina_clean.mp4",
    #                    "violations": {"stream[0]:encoder": "encoder='Lavc libx264'"}}]
    # }

    safe_paths = result["approved"]
"""

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Union


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# MP4 ftyp-box fields that ffprobe surfaces as tags but are required
# structural atoms — never flag these regardless of their value.
_STRUCTURAL_TAGS = frozenset({
    "major_brand",
    "minor_version",
    "compatible_brands",
})

# Tag key substrings (case-insensitive) that indicate tracking/privacy metadata.
# Any tag whose key contains one of these is a violation.
_FORBIDDEN_KEY_PATTERNS: List[str] = [
    "encoder",           # Lavc/Lavf fingerprints
    "handler_name",      # VideoHandler / SoundHandler
    "creation_time",     # recording timestamp
    "date",              # any date field
    "xmp",               # Adobe XMP block
    "c2pa",              # Content Credentials / C2PA manifest
    "iptc",              # IPTC press metadata
    "exif",              # EXIF camera data
    "gps",               # GPS coordinates
    "location",          # location string
    "geo",               # geolocation variants
    "latitude",
    "longitude",
    "coordinate",
    "software",          # software/app name
    "tool",              # processing tool name
    "comment",
    "description",
    "copyright",
    "artist",
    "author",
    "title",
    "album",
    "uuid",              # UUID boxes (used by C2PA)
    "manifest",          # any manifest blob
]

# Raw byte signatures of hidden metadata that ffprobe does not surface
# as named tags. Searched in the full file bytestream (case-insensitive).
_BINARY_SIGNATURES: Dict[str, bytes] = {
    "C2PA manifest":         b"c2pa",
    "JUMBF box":             b"jumb",        # JPEG Universal Metadata Box Format
    "XMP metadata block":    b"<x:xmpmeta",
    "XMP packet wrapper":    b"<?xpacket",
    "EXIF header":           b"exif\x00\x00",
    "Content Credentials":   b"contentcredentials",
    "Adobe XMP namespace":   b"adobe:ns.adobe.com/xap",
}


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("safety_filter")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_ffprobe() -> str:
    """
    Locate ffprobe binary.
    Priority: PATH → imageio_ffmpeg sibling → hardcoded Debian paths → bare name.
    """
    import shutil as _sh
    p = _sh.which("ffprobe")
    if p:
        return p
    # On Streamlit Cloud, imageio_ffmpeg bundles ffmpeg — ffprobe may sit beside it
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        candidate = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe")
        if os.path.isfile(candidate):
            return candidate
    except Exception:
        pass
    for candidate in ("/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "/bin/ffprobe"):
        if os.path.exists(candidate):
            return candidate
    return "ffprobe"


def _run_ffprobe(path: str, ffprobe: str) -> Optional[dict]:
    """
    Execute ffprobe and return parsed JSON (format + streams).
    Returns None on failure so the caller can fall back to binary-only mode.
    """
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log.error("ffprobe non-zero exit on %r: %s", path, r.stderr[:400])
            return None
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        log.error("ffprobe timed out on %r", path)
    except json.JSONDecodeError as e:
        log.error("ffprobe JSON parse error on %r: %s", path, e)
    except Exception as e:
        log.error("ffprobe unexpected error on %r: %s", path, e)
    return None


def _check_tag(key: str, value: str) -> Optional[str]:
    """
    Evaluate a single tag key/value.
    Returns a human-readable violation string, or None if the tag is clean.

    Rules:
      - Structural tags (major_brand, etc.) → always clean.
      - Tags whose value is empty or whitespace-only → treated as removed → clean.
      - Tags whose key contains a forbidden pattern → violation.
    """
    k_lower = key.lower()

    if k_lower in _STRUCTURAL_TAGS:
        return None

    # Whitespace-only value means the tag was intentionally blanked out
    if not (value or "").strip():
        return None

    for pattern in _FORBIDDEN_KEY_PATTERNS:
        if pattern in k_lower:
            return f"{key}={value!r}"

    return None


def _inspect_tags(ffprobe_data: dict) -> Dict[str, str]:
    """
    Walk every tag in the ffprobe JSON (container + all streams).
    Returns {location_key: violation_description} for each violation found.
    """
    violations: Dict[str, str] = {}

    for k, v in ffprobe_data.get("format", {}).get("tags", {}).items():
        hit = _check_tag(k, v)
        if hit:
            violations[f"container:{k}"] = hit

    for i, stream in enumerate(ffprobe_data.get("streams", [])):
        for k, v in stream.get("tags", {}).items():
            hit = _check_tag(k, v)
            if hit:
                violations[f"stream[{i}]:{k}"] = hit

    return violations


def _scan_binary(path: str) -> Dict[str, str]:
    """
    Read the raw MP4 bytes and search for known metadata signatures that
    ffprobe does not surface as named tags (e.g. C2PA JUMBF boxes, XMP
    packets written directly into the bytestream by recording software).

    Returns {label: description} for each signature found.
    """
    found: Dict[str, str] = {}
    try:
        with open(path, "rb") as f:
            data = f.read()
        data_lower = data.lower()
        for label, sig in _BINARY_SIGNATURES.items():
            if sig.lower() in data_lower:
                found[label] = "binary signature found in raw file bytes"
                log.debug("  Binary hit: %s in %r", label, path)
    except Exception as e:
        log.warning("Binary scan failed for %r: %s", path, e)
    return found


def _quarantine_file(path: str, quarantine_dir: str) -> str:
    """
    Move a bad file into quarantine_dir.
    Appends a timestamp suffix if a file with the same name already exists.
    Returns the new path inside the quarantine folder.
    """
    os.makedirs(quarantine_dir, exist_ok=True)
    basename = os.path.basename(path)
    dest = os.path.join(quarantine_dir, basename)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(basename)
        dest = os.path.join(quarantine_dir, f"{stem}_{int(time.time())}{ext}")
    shutil.move(path, dest)
    return dest


def _log_violations(path: str, violations: Dict[str, str]) -> None:
    log.critical("━━━ METADATA LEAK DETECTED: %r (%d violation(s)) ━━━", path, len(violations))
    for location, detail in violations.items():
        log.critical("    [%s] %s", location, detail)
    log.critical("━" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def verify_batch(
    video_paths: Union[str, "os.PathLike", list],
    quarantine_dir: str = "quarantine",
) -> dict:
    """
    Verify one file or a batch of files for leftover metadata.

    Parameters
    ----------
    video_paths : str | Path | list[str | Path]
        Single file path or a list of file paths to inspect.
    quarantine_dir : str
        Directory where bad files are moved. Created automatically if absent.

    Returns
    -------
    {
        "approved"    : list[str]   — paths of 100% clean files
        "quarantined" : list[dict]  — one entry per bad file:
            {
                "original_path"   : str,
                "quarantine_path" : str,
                "violations"      : {location: description, ...}
            }
    }

    Never raises — one bad file never crashes the entire batch.
    """
    # Normalise input to a flat list of strings
    if isinstance(video_paths, (str, os.PathLike)):
        paths = [str(video_paths)]
    else:
        paths = [str(p) for p in video_paths]

    ffprobe    = _find_ffprobe()
    approved   : List[str]  = []
    quarantined: List[dict] = []

    log.info("Safety filter — inspecting %d file(s)", len(paths))

    for path in paths:
        log.info("── Inspecting: %s", path)

        if not os.path.isfile(path):
            log.error("   File not found — skipping: %s", path)
            continue

        all_violations: Dict[str, str] = {}

        # ── Layer 1: ffprobe named-tag scan ──────────────────────────
        ffprobe_data = _run_ffprobe(path, ffprobe)
        if ffprobe_data is not None:
            tag_violations = _inspect_tags(ffprobe_data)
            all_violations.update(tag_violations)
        else:
            log.warning("   ffprobe unavailable — relying on binary scan only")

        # ── Layer 2: raw binary signature scan ───────────────────────
        binary_violations = _scan_binary(path)
        for label, desc in binary_violations.items():
            all_violations[f"binary:{label}"] = desc

        # ── Verdict ──────────────────────────────────────────────────
        if not all_violations:
            log.info("   ✅ APPROVED — %s", path)
            approved.append(path)
        else:
            _log_violations(path, all_violations)
            try:
                qpath = _quarantine_file(path, quarantine_dir)
                log.warning("   🚨 QUARANTINED → %s", qpath)
            except Exception as move_err:
                log.error(
                    "   Quarantine move failed for %r (%s) — recording in-place",
                    path, move_err,
                )
                qpath = path  # could not move; report original location
            quarantined.append({
                "original_path":   path,
                "quarantine_path": qpath,
                "violations":      all_violations,
            })

    # ── Batch summary ─────────────────────────────────────────────────
    total = len(paths)
    log.info(
        "Safety filter complete — %d/%d approved, %d/%d quarantined",
        len(approved), total, len(quarantined), total,
    )
    return {"approved": approved, "quarantined": quarantined}


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (για manual testing)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python safety_filter.py file1.mp4 [file2.mp4 ...]")
        sys.exit(1)
    result = verify_batch(sys.argv[1:])
    print("\n=== RESULT ===")
    print(f"Approved ({len(result['approved'])}):")
    for p in result["approved"]:
        print(f"  ✅ {p}")
    print(f"Quarantined ({len(result['quarantined'])}):")
    for entry in result["quarantined"]:
        print(f"  🚨 {entry['original_path']} → {entry['quarantine_path']}")
        for loc, detail in entry["violations"].items():
            print(f"       [{loc}] {detail}")
