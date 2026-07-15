"""
drive_exporter.py — T-WHALES Google Drive Export Module (OAuth / personal Gmail)

Uploads approved & scrubbed videos into a strict, dynamically-created
folder hierarchy inside the USER'S OWN Google Drive:

    T-WHALES / [Creator] / [Device] / [Date YYYY-MM-DD] / [Time of Day] / final_video.mp4

Why OAuth and not a Service Account
-----------------------------------
Service accounts have NO Drive storage quota and Google blocks them from
uploading into a personal Gmail Drive (403 "Service Accounts do not have
storage quota"). OAuth authenticates AS THE USER, so uploaded files are
owned by the user and count against the user's own 15 GB — no cost, no
Workspace needed.

Scope = drive.file (NON-sensitive → no Google verification/publishing review).
The app can only see/manage files IT creates, so it builds its own
`T-WHALES` root folder and everything beneath it. Nothing else in your
Drive is visible to the app.

One-time setup
--------------
  1. Google Cloud Console → same project → "APIs & Services" → "OAuth consent
     screen": User Type = External, fill app name + your email, and either
     add your Gmail as a Test user OR click "Publish app" (recommended, so
     the refresh token never expires; drive.file needs no verification).
  2. "Credentials" → "+ CREATE CREDENTIALS" → "OAuth client ID" →
     Application type = "Desktop app" → download → gives client_id + secret.
  3. Run the one-time auth helper (get_refresh_token below) — it opens a
     browser, you click Allow, and it prints a refresh_token.
  4. Streamlit secrets:

         [gcp_oauth]
         client_id     = "....apps.googleusercontent.com"
         client_secret = "GOCSPX-..."
         refresh_token = "1//0..."

Dependencies (requirements.txt):
    google-api-python-client, google-auth, google-auth-oauthlib

All Google imports are lazy so the rest of the app never crashes when the
libraries or credentials are absent.
"""

import os
import re
import threading

# ─────────────────────────────────────────────────────────────────────────────
# METADATA ROUTING — the single source of truth for the folder taxonomy
# ─────────────────────────────────────────────────────────────────────────────

ROOT_FOLDER_NAME = "T-WHALES"

# App-internal creator keys → Drive folder display names
DRIVE_CREATOR_FOLDER = {
    "SOFIA":  "Sofia",
    "MELINA": "Melina",
}

# Devices depend on the creator
DEVICE_MAP = {
    "SOFIA": [
        "iPhoneXs-Μαυρο με 70 ευρο ταμπελακι",
        "iPhoneSE-Καλη κατασταση μαυρο",
    ],
    "MELINA": [
        "iPhoneXs-Το κινητο με το Μ πισω το σπασμενο",
        "iPhone11-Με θυκη",
        "iPhone8-Ασπρο Ροζε",
    ],
}

TIMES_OF_DAY = ["Μερα", "Νυχτα"]

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FOLDER_MIME = "application/vnd.google-apps.folder"

# googleapiclient service objects are not thread-safe; guard with a lock
_drive_lock = threading.Lock()


class DriveExportError(RuntimeError):
    """Raised for any validation/auth/upload failure — message is UI-ready."""


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_metadata(creator: str, device: str, date_str: str, time_of_day: str):
    """Strict pre-upload validation. Returns the normalized
    (creator_folder, device, date_str, time_of_day) tuple or raises."""
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
# Auth — OAuth user credentials from a refresh token
# ─────────────────────────────────────────────────────────────────────────────

def get_drive_service(oauth_info: dict = None):
    """Build an authenticated Drive v3 service from OAuth user credentials.

    oauth_info: {"client_id", "client_secret", "refresh_token"} — e.g.
    dict(st.secrets["gcp_oauth"]). Falls back to env vars
    GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        raise DriveExportError(
            "Λείπουν οι βιβλιοθήκες Google — πρόσθεσε στο requirements.txt: "
            "google-api-python-client, google-auth, google-auth-oauthlib"
        ) from e

    info = oauth_info or {}
    client_id     = info.get("client_id")     or os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = info.get("client_secret") or os.environ.get("GDRIVE_CLIENT_SECRET")
    refresh_token = info.get("refresh_token") or os.environ.get("GDRIVE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        raise DriveExportError(
            "Λείπουν τα OAuth credentials — βάλε το [gcp_oauth] block "
            "(client_id / client_secret / refresh_token) στα Streamlit secrets.")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─────────────────────────────────────────────────────────────────────────────
# Folder resolution — Drive works on IDs, not paths
# ─────────────────────────────────────────────────────────────────────────────

def _escape_q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def get_or_create_folder(service, folder_name: str, parent_id: str) -> str:
    """Return the ID of `folder_name` under `parent_id`, creating if absent.
    With drive.file scope, list() only sees app-created items — which is
    exactly our own hierarchy, so lookups are correct and private."""
    q = (
        f"name = '{_escape_q(folder_name)}' "
        f"and '{_escape_q(parent_id)}' in parents "
        f"and mimeType = '{_FOLDER_MIME}' "
        f"and trashed = false"
    )
    resp = service.files().list(q=q, fields="files(id, name)", pageSize=5).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    created = service.files().create(
        body={"name": folder_name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
        fields="id",
    ).execute()
    return created["id"]


def ensure_folder_path(service, segments: list, root_parent: str = "root") -> str:
    """Walk/create the whole hierarchy under `root_parent`; return the
    deepest folder's ID. Default root_parent='root' = the user's My Drive."""
    parent = root_parent
    for seg in segments:
        parent = get_or_create_folder(service, seg, parent)
    return parent


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

def upload_video(
    file_path: str,
    creator: str,
    device: str,
    date_str: str,
    time_of_day: str,
    oauth_info: dict = None,
    filename: str = "final_video.mp4",
    progress_cb=None,
) -> dict:
    """Validate → build T-WHALES/Creator/Device/Date/ToD → resumable upload
    into the user's own Drive. Returns {"file_id","webViewLink","folder_path"}."""
    creator_folder, device, date_str, time_of_day = validate_metadata(
        creator, device, date_str, time_of_day)

    if not (file_path and os.path.exists(file_path)):
        raise DriveExportError(f"Το αρχείο δεν βρέθηκε στο δίσκο: {file_path!r}")

    try:
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
    except ImportError as e:
        raise DriveExportError("Λείπουν οι βιβλιοθήκες Google — δες requirements.txt") from e

    with _drive_lock:
        service = get_drive_service(oauth_info=oauth_info)
        segments = [ROOT_FOLDER_NAME, creator_folder, device, date_str, time_of_day]
        try:
            dest_id = ensure_folder_path(service, segments, "root")
            media = MediaFileUpload(
                file_path, mimetype="video/mp4",
                resumable=True, chunksize=4 * 1024 * 1024,
            )
            request = service.files().create(
                body={"name": filename, "parents": [dest_id]},
                media_body=media,
                fields="id, webViewLink",
            )
            response = None
            while response is None:
                status, response = request.next_chunk(num_retries=3)
                if status and progress_cb:
                    try:
                        progress_cb(min(0.99, status.progress()))
                    except Exception:
                        pass
        except HttpError as he:
            _st = getattr(he, "resp", None) and he.resp.status
            if _st in (401, 403):
                raise DriveExportError(
                    "Πρόβλημα εξουσιοδότησης OAuth — το refresh_token μπορεί να "
                    "έληξε (αν το OAuth app είναι σε 'Testing', λήγει σε 7 μέρες — "
                    "κάνε 'Publish app'). Ξανα-τρέξε το get_refresh_token.") from he
            raise DriveExportError(f"Drive API error: {he}") from he

    if progress_cb:
        try:
            progress_cb(1.0)
        except Exception:
            pass
    return {
        "file_id": response["id"],
        "webViewLink": response.get("webViewLink", ""),
        "folder_path": "/".join(segments) + f"/{filename}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# One-time helper: obtain a refresh token (run locally, opens a browser)
# ─────────────────────────────────────────────────────────────────────────────

def get_refresh_token(client_id: str, client_secret: str) -> str:
    """Run the OAuth installed-app consent flow once and return a refresh
    token to paste into Streamlit secrets. Requires google-auth-oauthlib."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    return creds.refresh_token


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        print("\nREFRESH_TOKEN:\n" + get_refresh_token(sys.argv[1], sys.argv[2]))
    else:
        print("Usage: python drive_exporter.py <client_id> <client_secret>")
