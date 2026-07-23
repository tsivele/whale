"""
drive_exporter.py — T-WHALES Google Drive Export via rclone

Why rclone (and not a custom Google Cloud OAuth app):
  A self-made OAuth app stays in "Testing" until Google verifies it, so every
  consent returns 403 access_denied unless each account is a registered test
  user — and on org-managed Google accounts the Cloud Console itself blocks
  managing that config (Principal Access Boundary). rclone ships with its OWN
  Google-VERIFIED OAuth client, so authorization is a normal "Allow" screen
  with no verification/testing wall. We only need the resulting token.

Uploads approved & scrubbed videos into a strict, dynamically-created
hierarchy inside the user's own Google Drive:

    T-WHALES / [Creator] / [Device] / [Date YYYY-MM-DD] / [Time of Day] / final_video.mp4

Setup (one-time):
  1. Locally:  rclone authorize "drive"   → click Allow → copy the token JSON.
  2. Build an rclone.conf remote named `whale` and paste it into Streamlit
     secrets under key `rclone_conf` (a single multi-line string):

         rclone_conf = '''
         [whale]
         type = drive
         scope = drive
         token = {"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}
         '''

  3. Add `rclone` to packages.txt so Streamlit Cloud installs the binary.

rclone refreshes the token automatically using its bundled client — no
client_id/secret needed in the app.
"""

import os
import shutil
import subprocess
import tempfile
import threading

# ─────────────────────────────────────────────────────────────────────────────
# METADATA ROUTING — the single source of truth for the folder taxonomy
# ─────────────────────────────────────────────────────────────────────────────

ROOT_FOLDER_NAME = "T-WHALES"
REMOTE_NAME = "whale"          # must match the [whale] section in rclone_conf

DRIVE_CREATOR_FOLDER = {
    "SOFIA":  "Sofia",
    "MELINA": "Melina",
}

DEVICE_MAP = {
    "SOFIA": [
        "iPhoneXs-Μαυρο με 70 ευρο ταμπελακι",
        "iPhoneSE-Καλη κατασταση μαυρο",
    ],
    "MELINA": [
        "iPhone11-Με θυκη",
        "iPhoneXs-Το κινητο με το Μ πισω το σπασμενο",
        "iPhone8-Ασπρο Ροζε",
        "iPhoneSE",
        "iPhoneXs(Καινουργιο)",
    ],
}

TIMES_OF_DAY = ["Μερα", "Νυχτα"]

# The phones for auto-distribution, in fill order. Single source of truth =
# DEVICE_MAP["MELINA"] so the manual dropdown and the scheduler never diverge.
PHONES = DEVICE_MAP["MELINA"]

PER_DEVICE_PER_DAY = 2   # exactly 2 videos/device/date: 1 Μερα + 1 Νυχτα


def plan_distribution(n_videos, start_date, phones=None):
    """Round-robin by DATE. Each device gets exactly 2 videos per date — one
    'Μερα' (day) and one 'Νυχτα' (night). ALL devices are filled for a date
    (day+night each) BEFORE the date is incremented by 1.

    Example — 18 videos, start 2026-07-27, [iPhone11, iPhoneXS, iPhone8]:
        07-27: iPhone11(day,night) iPhoneXS(day,night) iPhone8(day,night)
        07-28: …same…   07-29: …same…   (6 videos/date → 3 dates)

    Returns [{device, date_str, time_of_day, day_index}, …], one per video.
    """
    from datetime import timedelta
    phones = phones or PHONES
    per_date = len(phones) * PER_DEVICE_PER_DAY     # 3 × 2 = 6 videos/date
    plan = []
    for i in range(n_videos):
        day_off   = i // per_date
        within    = i % per_date
        phone_idx = within // PER_DEVICE_PER_DAY    # device: 0,0,1,1,2,2
        tod       = TIMES_OF_DAY[within % PER_DEVICE_PER_DAY]   # day,night,day,night…
        plan.append({
            "device":      phones[phone_idx],
            "date_str":    (start_date + timedelta(days=day_off)).strftime("%Y-%m-%d"),
            "time_of_day": tod,
            "day_index":   day_off,
        })
    return plan

import re as _re
_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")

_lock = threading.Lock()


class DriveExportError(RuntimeError):
    """Raised for any validation/rclone failure — message is UI-ready."""


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_metadata(creator: str, device: str, date_str: str, time_of_day: str):
    """Strict pre-upload validation. Returns normalized
    (creator_folder, device, date_str, time_of_day) or raises."""
    _c = (creator or "").strip().upper()
    if _c not in DRIVE_CREATOR_FOLDER:
        raise DriveExportError(
            f"Άγνωστος creator {creator!r} — επιτρέπονται: {list(DRIVE_CREATOR_FOLDER)}")
    if device not in DEVICE_MAP[_c]:
        raise DriveExportError(
            f"Η συσκευή {device!r} δεν αντιστοιχεί στη {creator} — "
            f"επιτρέπονται: {DEVICE_MAP[_c]}")
    if not _DATE_RE.match(date_str or ""):
        raise DriveExportError(
            f"Μη έγκυρη ημερομηνία {date_str!r} — μορφή YYYY-MM-DD (π.χ. 2026-07-20)")
    if time_of_day not in TIMES_OF_DAY:
        raise DriveExportError(
            f"Μη έγκυρο Time of Day {time_of_day!r} — επιτρέπονται: {TIMES_OF_DAY}")
    return DRIVE_CREATOR_FOLDER[_c], device, date_str, time_of_day


# ─────────────────────────────────────────────────────────────────────────────
# rclone plumbing
# ─────────────────────────────────────────────────────────────────────────────

def _rclone_bin() -> str:
    """Locate rclone. Order: PATH → known paths → cached self-download.
    The self-download makes Drive export work on Streamlit Cloud even when
    packages.txt wasn't (re)deployed — it fetches the static binary once and
    caches it, so the '`rclone` not found' error can no longer block uploads."""
    p = shutil.which("rclone")
    if p:
        return p
    for cand in ("/usr/bin/rclone", "/usr/local/bin/rclone", "/opt/homebrew/bin/rclone"):
        if os.path.exists(cand):
            return cand
    _cache = os.path.join(tempfile.gettempdir(), "whale_rclone")
    _cached = os.path.join(_cache, "rclone")
    if os.path.exists(_cached) and os.access(_cached, os.X_OK):
        return _cached
    return _download_rclone(_cache)


def _download_rclone(cache_dir: str) -> str:
    """Fetch the official static rclone binary for this OS/arch, cache it."""
    import urllib.request, zipfile, platform, stat
    os.makedirs(cache_dir, exist_ok=True)
    _sys = platform.system().lower()          # linux / darwin
    _mach = platform.machine().lower()
    _os = "osx" if _sys == "darwin" else "linux"
    _arch = "arm64" if _mach in ("aarch64", "arm64") else "amd64"
    url = f"https://downloads.rclone.org/rclone-current-{_os}-{_arch}.zip"
    zip_path = os.path.join(cache_dir, "rclone.zip")
    out = os.path.join(cache_dir, "rclone")
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            _member = next((n for n in z.namelist() if n.endswith("/rclone") or n == "rclone"), None)
            if not _member:
                raise DriveExportError("Το κατεβασμένο rclone zip δεν περιέχει binary.")
            with z.open(_member) as src, open(out, "wb") as dst:
                dst.write(src.read())
        os.chmod(out, os.stat(out).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return out
    except DriveExportError:
        raise
    except Exception as e:
        raise DriveExportError(
            f"Το rclone δεν βρέθηκε και το auto-download απέτυχε ({e}). "
            f"Πρόσθεσε `rclone` στο packages.txt και κάνε reboot το app.")
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass


def _write_conf(rclone_conf_text: str) -> str:
    if not (rclone_conf_text and rclone_conf_text.strip()):
        raise DriveExportError(
            "Λείπει το rclone_conf από τα Streamlit secrets — δες οδηγίες στο drive_exporter.py")
    fd, path = tempfile.mkstemp(suffix=".conf", prefix="rclone_")
    with os.fdopen(fd, "w") as f:
        f.write(rclone_conf_text.strip() + "\n")
    return path


def upload_video(
    file_path: str,
    creator: str,
    device: str,
    date_str: str,
    time_of_day: str,
    rclone_conf: str = None,
    filename: str = "final_video.mp4",
    progress_cb=None,
) -> dict:
    """Validate → rclone copyto into T-WHALES/Creator/Device/Date/ToD.
    rclone auto-creates parent folders. Returns {"remote_path", "folder_path"}."""
    creator_folder, device, date_str, time_of_day = validate_metadata(
        creator, device, date_str, time_of_day)

    if not (file_path and os.path.exists(file_path)):
        raise DriveExportError(f"Το αρχείο δεν βρέθηκε στο δίσκο: {file_path!r}")

    conf_text = rclone_conf or os.environ.get("RCLONE_CONF", "")
    rclone = _rclone_bin()

    with _lock:
        conf_path = _write_conf(conf_text)
        try:
            rel = f"{ROOT_FOLDER_NAME}/{creator_folder}/{device}/{date_str}/{time_of_day}/{filename}"
            remote_path = f"{REMOTE_NAME}:{rel}"
            if progress_cb:
                try: progress_cb(0.1)
                except Exception: pass
            r = subprocess.run(
                [rclone, "--config", conf_path, "copyto", file_path, remote_path,
                 "--drive-chunk-size", "8M"],
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                _err = (r.stderr or r.stdout or "").strip()[-500:]
                raise DriveExportError(f"rclone upload απέτυχε:\n{_err}")
            if progress_cb:
                try: progress_cb(1.0)
                except Exception: pass
            return {"remote_path": remote_path, "folder_path": rel}
        finally:
            try:
                os.remove(conf_path)
            except OSError:
                pass
