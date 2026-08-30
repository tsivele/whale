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

    T-WHALES / [Creator] / [Device] / [Date YYYY-MM-DD] / [Ώρα HH:MM] / final_video.mp4

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

# Listed in ΚΙΝΗΤΟ 1..5 order — the numbering the phones are known by.
DEVICE_MAP = {
    "SOFIA": [
        "iPhoneXs-Μαυρο με 70 ευρο ταμπελακι",
        "iPhoneSE-Καλη κατασταση μαυρο",
    ],
    "MELINA": [
        "iPhone8-Ασπρο Ροζε",                          # ΚΙΝΗΤΟ 1
        "iPhoneXs-Το κινητο με το Μ πισω το σπασμενο",  # ΚΙΝΗΤΟ 2
        "iPhone11-Με θυκη",                            # ΚΙΝΗΤΟ 3
        "iPhoneSE(Μαυρο με κουμπι)",                   # ΚΙΝΗΤΟ 4
        "iPhoneXs(7ευρο λεει πισω)",                   # ΚΙΝΗΤΟ 5
    ],
}

# ── POSTING HOURS ────────────────────────────────────────────────────────────
# Each phone posts at its OWN two hours, and the hour IS the Drive folder:
#     T-WHALES/Melina/iPhone8-Ασπρο Ροζε/2026-09-01/13:00/whale_42.mp4
# (This replaced the old generic Μερα/Νυχτα folders.)
DEVICE_TIMES = {
    "iPhone8-Ασπρο Ροζε":                          ["13:00", "19:00"],
    "iPhoneXs-Το κινητο με το Μ πισω το σπασμενο":  ["13:00", "00:00"],
    "iPhone11-Με θυκη":                            ["22:00", "10:00"],
    "iPhoneSE(Μαυρο με κουμπι)":                   ["10:00", "23:00"],
    "iPhoneXs(7ευρο λεει πισω)":                   ["22:00", "10:00"],
}

# The Instagram account each phone posts from (display only — never a folder).
DEVICE_ACCOUNT = {
    "iPhone8-Ασπρο Ροζε":                          "melin_ioannou",
    "iPhoneXs-Το κινητο με το Μ πισω το σπασμενο":  "melinaki.ioann",
    "iPhone11-Με θυκη":                            "melin.ioannou",
    "iPhoneSE(Μαυρο με κουμπι)":                   "yourcutemel",
    "iPhoneXs(7ευρο λεει πισω)":                   "ikoritsara",
}

# Fallback for any phone with no hours of its own (e.g. the SOFIA devices).
DEFAULT_TIMES = ["13:00", "22:00"]

# Old folder names — still accepted on upload so anything already sitting in
# Drive under Μερα/Νυχτα keeps validating.
LEGACY_TIMES = ["Μερα", "Νυχτα"]
TIMES_OF_DAY = LEGACY_TIMES          # back-compat alias for older callers

# The phones for auto-distribution, in fill order. Single source of truth =
# DEVICE_MAP["MELINA"] so the manual dropdown and the scheduler never diverge.
PHONES = DEVICE_MAP["MELINA"]

PER_DEVICE_PER_DAY = 2   # exactly 2 videos/device/date — one per posting hour


def device_times(device) -> list:
    """The two posting hours for `device` (its own, or the default pair)."""
    return list(DEVICE_TIMES.get(device, DEFAULT_TIMES))


def _hour_key(hour: str):
    """Sort key that reads a day the way a person does: 10:00 → 13:00 → 19:00
    → 23:00 → 00:00. Anything before 06:00 is LATE night, so it sorts at the
    end of its date instead of jumping to the front."""
    try:
        h, m = (int(x) for x in str(hour).split(":")[:2])
    except (ValueError, TypeError):
        return (99, 99)
    return (h + 24, m) if h < 6 else (h, m)


ALL_TIMES = sorted({t for d in PHONES for t in device_times(d)}, key=_hour_key)


def device_label(device) -> str:
    """'ΚΙΝΗΤΟ 3 · melin.ioannou · 22:00/10:00' — for the pickers, so a phone is
    recognisable without decoding its folder name."""
    _hrs = "/".join(device_times(device))
    _acc = DEVICE_ACCOUNT.get(device)
    try:
        _num = f"ΚΙΝΗΤΟ {PHONES.index(device) + 1} · "
    except ValueError:
        _num = ""
    return f"{_num}{_acc + ' · ' if _acc else ''}{device} · {_hrs}"


def plan_distribution(n_videos, start_date, occupied=None, phones=None,
                      hours=None, max_days=730, times=None):
    """Assign n videos to (device, date, hour) slots — EXACTLY ONE video per
    slot. Every phone posts at its OWN two hours (see DEVICE_TIMES), and the
    hour is the Drive folder.

    `occupied` = a set of (device, date_str, hour) that ALREADY holds a video
    (read back from Drive). Those slots are SKIPPED, so re-running never
    double-fills a folder — it just flows to the next free slot / next day.

    `phones` = which devices to fill. None = every device in PHONES. An EMPTY
    list means "no device selected" and returns an empty plan — it must NEVER
    fall back to all phones, or deselecting everything would upload everywhere.

    `hours` = which posting hours to fill, e.g. ["22:00", "23:00"] for the late
    slots only. A phone contributes a slot only for its own hours that are in
    this list. None = every hour. (`times` is the old argument name and still
    works.)

    Fill order inside a date is CHRONOLOGICAL — 10:00, 13:00, 19:00, 22:00,
    23:00, then 00:00 as the late-night slot — so the videos go out in the same
    order a person would post them.

    Example — start 2026-09-01, all 5 phones, nothing occupied:
        09-01 10:00 → ΚΙΝΗΤΟ 3, ΚΙΝΗΤΟ 4, ΚΙΝΗΤΟ 5
        09-01 13:00 → ΚΙΝΗΤΟ 1, ΚΙΝΗΤΟ 2
        09-01 19:00 → ΚΙΝΗΤΟ 1 … and so on, 10 slots/date.

    Returns [{device, date_str, time_of_day, day_index}, …], one per video.
    `time_of_day` holds the hour, so every caller downstream is unchanged.
    """
    from datetime import timedelta
    # None = "not specified" → the full default. [] = "explicitly nothing" →
    # empty plan. Conflating the two would silently post to every phone.
    phones = list(PHONES) if phones is None else list(phones)
    if hours is None:
        hours = times                      # legacy argument name
    hours = list(ALL_TIMES) if hours is None else list(hours)
    if not (phones and hours and n_videos > 0):
        return []
    # every (hour, device) pair this run may use, in chronological order
    slots = [(h, d) for d in phones for h in device_times(d) if h in hours]
    slots.sort(key=lambda hd: (_hour_key(hd[0]), phones.index(hd[1])))
    if not slots:
        return []
    occ = set(occupied or ())
    plan = []
    day_off = 0
    while len(plan) < n_videos and day_off < max_days:
        date_str = (start_date + timedelta(days=day_off)).strftime("%Y-%m-%d")
        for _hour, device in slots:
            if len(plan) >= n_videos:
                break
            if (device, date_str, _hour) in occ:   # slot already has a video
                continue
            plan.append({"device": device, "date_str": date_str,
                         "time_of_day": _hour, "day_index": day_off})
        day_off += 1
    return plan


def slots_per_day(phones=None, hours=None) -> int:
    """How many videos fit in one date for this phone/hour selection."""
    phones = list(PHONES) if phones is None else list(phones)
    hours = list(ALL_TIMES) if hours is None else list(hours)
    return sum(1 for d in phones for h in device_times(d) if h in hours)


def get_occupied_slots(rclone_conf) -> set:
    """Scan Drive (one rclone call) for slots that already contain a video, so
    the scheduler won't reuse them. Returns {(device, date_str, time_of_day)}.
    Survives Streamlit Cloud restarts (the DB is ephemeral, Drive is the truth)."""
    occupied = set()
    try:
        rclone = _rclone_bin()
    except DriveExportError:
        return occupied
    conf_path = _write_conf(rclone_conf)
    try:
        r = subprocess.run(
            [rclone, "--config", conf_path, "lsf", "-R", "--files-only",
             f"{REMOTE_NAME}:{ROOT_FOLDER_NAME}"],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                # relative to T-WHALES: Melina/Device/Date/HH:MM/file.mp4
                parts = line.strip().split("/")
                if len(parts) >= 5:
                    occupied.add((parts[1], parts[2], parts[3]))
    except Exception:
        pass
    finally:
        try:
            os.remove(conf_path)
        except OSError:
            pass
    return occupied

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
    _allowed = device_times(device) + LEGACY_TIMES
    if time_of_day not in _allowed:
        raise DriveExportError(
            f"Μη έγκυρη ώρα {time_of_day!r} για {device!r} — "
            f"επιτρέπονται: {device_times(device)}")
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
