"""
Video post-processing pipeline — 2-stage: re-encode+scrub → verify.

  Stage 1 (FFmpeg, two passes):
    pass 1  libx264 (veryfast, crf 23, High profile) + aac 192k re-encode with
            +bitexact on both encoders and the muxer, so no "Lavc"/"Lavf" string
            is written.
    pass 2  -c copy remux that removes the x264 SEI user-data NAL
            (filter_units remove_types=6 — the "x264 - core … options: …" string),
            drops every container/stream tag, blanks encoder/handler_name and
            moves moov to the front.
  Stage 2 (ffprobe): strict JSON tag check. ffprobe is mandatory — if it cannot
            be found, process() raises instead of skipping verification.

process() accepts a single path OR a list of paths.
When given a list, it encodes+scrubs all files first, then verifies every one of
them and aggregates failures into a single comprehensive error before raising.
Any failure at any stage deletes every output produced so far (fail closed).
"""

import json
import os
import subprocess
import tempfile
from typing import List, Union


# ── ΟΡΙΑ ΧΡΟΝΟΥ ──────────────────────────────────────────────────────────────
# Χωρίς αυτά, ΕΝΑ χαλασμένο αρχείο κρεμάει για πάντα το worker thread του
# Scrub All: το app.py τρέχει τα βίντεο σειριακά σε ΕΝΑ thread, οπότε ένα
# κολλημένο ffmpeg σταματά και όλα τα υπόλοιπα — χωρίς σφάλμα, χωρίς μήνυμα,
# η ουρά απλώς παγώνει. Με timeout το αρχείο βγάζει καθαρό error, ο worker
# προχωράει στο επόμενο. Γενναιόδωρα για shared 1-vCPU: ένα reel 10-20s που
# θέλει πάνω από 5 λεπτά re-encode είναι χαλασμένο, όχι αργό.
ENCODE_TIMEOUT = 300     # pass 1 — libx264, το μόνο CPU-βαρύ βήμα
SCRUB_TIMEOUT  = 120     # pass 2 — stream copy, δεν ξανακωδικοποιεί
PROBE_TIMEOUT  = 60      # ffprobe — μόνο διάβασμα metadata


def _run_bounded(cmd, timeout, what, src):
    """subprocess.run με όριο χρόνου· το timeout γίνεται RuntimeError.

    Το subprocess.run σκοτώνει τη διεργασία πριν σηκώσει TimeoutExpired, οπότε
    δεν μένει ορφανό ffmpeg να τρώει CPU στο παρασκήνιο — αυτό ακριβώς ήταν που
    έριχνε τον container. Το RuntimeError το πιάνει το per-item try/except στο
    app.py, άρα το κακό βίντεο σημειώνεται και η παρτίδα συνεχίζει.
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"FFmpeg {what} ξεπέρασε το όριο χρόνου ({timeout}s) — "
            f"το αρχείο παραλείπεται: {os.path.basename(src)!r}"
        ) from None


# Tags that come from the ftyp box and are required structure (removing them
# corrupts the file) — allowed by KEY, whatever their value.
_STRUCTURAL_TAGS = frozenset({
    "major_brand",
    "minor_version",
    "compatible_brands",
})

# Tags that ffmpeg always writes on streams. They are allowed ONLY with a
# neutral value (empty/whitespace, or the listed defaults). Any other value —
# e.g. a custom handler_name or a real vendor code — is a fingerprint and fails
# verification. Pass 2 sets handler_name to a single space.
_NEUTRAL_ONLY_TAGS = {
    "language":     frozenset({"und"}),
    "handler_name": frozenset(),
    "vendor_id":    frozenset({"[0][0][0][0]"}),
}


def _tag_violation(key: str, value) -> bool:
    """True when a container/stream tag must fail verification."""
    k = key.lower()
    if k in _STRUCTURAL_TAGS:
        return False
    v = ("" if value is None else str(value)).strip()
    if not v:
        return False
    if k in _NEUTRAL_ONLY_TAGS:
        return v not in _NEUTRAL_ONLY_TAGS[k]
    return True


def _find_bin(name: str) -> str:
    """
    Locate ffmpeg with four fallbacks (most reliable first):
      1. imageio_ffmpeg bundled binary  (most reliable on Streamlit Cloud)
      2. PATH search                    (works if packages.txt installed system ffmpeg)
      3. Known fixed paths              (/usr/bin, /usr/local/bin, /bin)
      4. Bare name                      (last resort — subprocess will raise FileNotFoundError)
    ffprobe has its own resolver (_find_ffprobe) because it must never fall
    back to a bare name: a missing ffprobe has to stop the pipeline.
    static_ffmpeg is intentionally skipped — it writes a lock file to the venv
    which is read-only on Streamlit Cloud, causing a Permission denied crash.
    """
    import shutil as _sh

    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            p = imageio_ffmpeg.get_ffmpeg_exe()
            if p and os.path.isfile(str(p)):
                return str(p)
        except Exception:
            pass

    p = _sh.which(name)
    if p:
        return p

    for candidate in (f"/usr/bin/{name}", f"/usr/local/bin/{name}", f"/bin/{name}"):
        if os.path.exists(candidate):
            return candidate

    return name


def _find_ffprobe():
    """
    Locate ffprobe, or return None when it is not installed. Order:
      1. PATH
      2. next to the imageio_ffmpeg binary (imageio bundles ffmpeg only, but a
         deployment may place ffprobe beside it)
      3. /usr/bin, /usr/local/bin, /bin
    """
    import shutil as _sh

    p = _sh.which("ffprobe")
    if p:
        return p

    try:
        import imageio_ffmpeg
        candidate = os.path.join(os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe()), "ffprobe")
        if os.path.isfile(candidate):
            return candidate
    except Exception:
        pass

    for candidate in ("/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "/bin/ffprobe"):
        if os.path.isfile(candidate):
            return candidate

    return None


def _ffbin():
    """Return (ffmpeg_path, ffprobe_path). Raises when ffprobe is missing."""
    ffmpeg = _find_bin("ffmpeg")
    ffprobe = _find_ffprobe()
    if ffprobe is None:
        # Fail closed: without ffprobe the tag check cannot run, and a scrub
        # that cannot be verified must not be reported as clean.
        raise RuntimeError(
            "ffprobe not found (checked PATH, next to the imageio_ffmpeg binary, "
            "/usr/bin, /usr/local/bin, /bin) — cannot verify the scrub, refusing to "
            "process. Install ffmpeg via packages.txt so ffprobe is available."
        )
    return ffmpeg, ffprobe


class VideoProcessor:

    @classmethod
    def process(
        cls,
        src: Union[str, os.PathLike, List[Union[str, os.PathLike]]],
        progress_cb=None,
    ) -> Union[str, List[str]]:
        """
        Full pipeline: re-encode+scrub → strict verify.

        src:
            str | Path            → process one file, return one str path
            list[str | Path]      → process all files, verify all, return list[str]

        Raises if ffprobe is unavailable (verification is mandatory). On any
        encode, scrub or verification failure every output file is deleted
        before raising, so nothing dirty or unverified escapes the pipeline.
        """
        ffmpeg, ffprobe = _ffbin()

        # ── Normalise input ──────────────────────────────────────────────────
        if isinstance(src, (str, os.PathLike)):
            inputs      = [str(src)]
            single_mode = True
        else:
            inputs      = [str(p) for p in src]
            single_mode = False

        n       = len(inputs)
        outputs: List[str] = []   # accumulates clean temp paths

        # ── Stage 1: FFmpeg re-encode + scrub, one file at a time ────────────
        for i, src_path in enumerate(inputs):
            tmp_clean = tempfile.mktemp(suffix="_clean.mp4")

            # Scale this file's 0→1 progress into its share of 0 → 0.90 total.
            if n > 1:
                _slot_start = i       * (0.90 / n)
                _slot_size  = 0.90 / n
                def _cb(p, t, _s=_slot_start, _z=_slot_size):
                    if progress_cb:
                        progress_cb(_s + p * _z, t)
            else:
                _cb = progress_cb

            print(f"[processor] ({i + 1}/{n}) src={src_path!r}")

            try:
                label = (f"[{i+1}/{n}] ⚙️ Re-encode + scrub..."
                         if n > 1 else "⚙️ Re-encode + scrub...")
                if _cb:
                    _cb(0.05, label)

                cls._encode_and_scrub(src_path, tmp_clean, ffmpeg)

                size = os.path.getsize(tmp_clean)
                if size < 1000:
                    raise RuntimeError(
                        f"[{i+1}/{n}] Output suspiciously small: {size} bytes"
                    )

                if _cb:
                    _cb(0.90, label)

                outputs.append(tmp_clean)

            except Exception:
                # Abort: destroy every clean file produced so far
                for o in outputs:
                    if os.path.exists(o):
                        os.remove(o)
                if os.path.exists(tmp_clean):
                    os.remove(tmp_clean)
                raise

        # ── Stage 2: verify ALL outputs — never stop on first failure ────────
        # ffprobe is guaranteed here (_ffbin raised otherwise). Any exception
        # while verifying (ffprobe error, bad JSON…) also destroys every output.
        if progress_cb:
            progress_cb(0.95, "🔍 Επαλήθευση metadata...")

        failures: dict = {}          # {clean_path: {tag_key: tag_value, …}}
        try:
            for path in outputs:
                found = cls._check_tags(path, ffprobe)
                if found:
                    failures[path] = found
                    print(f"[processor] verify FAIL — {os.path.basename(path)!r}: {found}")
                else:
                    print(f"[processor] verify ✓  — {os.path.basename(path)!r} is clean")
        except Exception:
            for o in outputs:
                if os.path.exists(o):
                    os.remove(o)
            raise

        if failures:
            # Fail-fast: destroy ALL outputs before raising
            for o in outputs:
                if os.path.exists(o):
                    os.remove(o)

            # Build comprehensive, per-file error report
            lines = []
            for idx, (path, tags) in enumerate(failures.items()):
                tag_str = "; ".join(f"{k}={v!r}" for k, v in tags.items())
                lines.append(f"  [{idx + 1}] {os.path.basename(path)}: {tag_str}")

            raise ValueError(
                f"[processor] SCRUB VERIFICATION FAILED — "
                f"{len(failures)}/{n} file(s) contain forbidden metadata:\n"
                + "\n".join(lines)
                + "\nPipeline halted. No files were delivered."
            )

        if progress_cb:
            progress_cb(1.0, "✅ Ολοκληρώθηκε!")

        print(f"[processor] pipeline complete — {n} file(s) clean")
        return outputs[0] if single_mode else outputs

    # ── Stage 1: FFmpeg re-encode + metadata scrub (single pass) ─────────────

    @classmethod
    def _encode_and_scrub(cls, src: str, dst: str, ffmpeg: str) -> None:
        """
        Two-pass pipeline — encode then stream-copy-scrub:

          Pass 1 (encode): re-encode to libx264/aac into a temp file.
              -preset veryfast -crf 23  High profile, ~same quality, smaller
                                        than the source (ultrafast without crf
                                        gave Constrained Baseline, ~2.3x larger)
              -threads 1                one frame-buffer set → lower peak RAM
              -flags:v/a +bitexact      the encoders do not write "Lavc…"
              -b:a 192k                 keeps audio rate (bare aac halved it)
              -fflags +bitexact         the muxer does not write "Lavf…"
            The x264 encoder still embeds its settings string ("x264 - core …
            options: …") as an SEI user-data NAL inside mdat; pass 2 removes it.

          Pass 2 (stream-copy scrub): remux the encoded temp file into dst
            with -c copy — no encoder runs, so nothing new is written:
              -bsf:v filter_units=remove_types=6   drop SEI NALs (the x264
                                                   settings string); decodes fine
              -map_metadata -1          drop all container-level input tags
              -map_metadata:s:v -1      drop ALL video-stream input tags
              -map_metadata:s:a -1      drop ALL audio-stream input tags
              -fflags +bitexact         suppress Lavf muxer signature
              -brand mp42               remap ftyp from isom → mp42
              -movflags +faststart      moov before mdat
              -metadata:s:v:0 encoder=          wipe encoder tag, video
              -metadata:s:v:0 handler_name=" "  replace VideoHandler, video
              -metadata:s:a:0 encoder=          wipe encoder tag, audio
              -metadata:s:a:0 handler_name=" "  replace SoundHandler, audio
            (-flags:v/-flags:a +bitexact are not used here: with -c copy no
            encoder runs, so they had no effect.)
        """
        tmp_enc = tempfile.mktemp(suffix="_enc.mp4")
        try:
            # ── Pass 1: encode ───────────────────────────────────────────────
            r1 = _run_bounded(
                [
                    ffmpeg, "-y", "-i", src,
                    # veryfast + crf 23: High profile and ~63% smaller than
                    # ultrafast-without-crf at near-identical quality (SSIM
                    # 0.974 vs 0.977), still fast enough for the 1-vCPU host.
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    # -threads 1: ο container έχει 1 vCPU, οπότε τα πολλά νήματα
                    # δεν δίνουν ταχύτητα — δίνουν όμως ένα σύνολο frame buffers
                    # ανά νήμα. Με ένα νήμα η κορυφή μνήμης του ffmpeg πέφτει
                    # αισθητά, που είναι ακριβώς αυτό που σκότωνε τον container.
                    "-threads", "1",
                    # bitexact on the encoder itself: this is the pass where an
                    # encoder runs, so this is where "Lavc…" is (not) written.
                    "-flags:v", "+bitexact",
                    "-c:a", "aac", "-b:a", "192k", "-flags:a", "+bitexact",
                    "-fflags", "+bitexact",
                    tmp_enc,
                ],
                ENCODE_TIMEOUT, "encode", src,
            )
            if r1.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg encode failed (exit {r1.returncode}):\n{r1.stderr[-2000:]}"
                )

            # ── Pass 2: stream-copy + nuclear metadata wipe ──────────────────
            # handler_name is set to a single space, not empty string.
            # Reason: some FFmpeg builds treat "" as "unset" and fall back to
            # the default "VideoHandler"/"SoundHandler". A literal space is
            # written verbatim into the hdlr box and is not a known fingerprint.
            r2 = _run_bounded(
                [
                    ffmpeg, "-y", "-i", tmp_enc,
                    "-c", "copy",
                    # remove SEI NAL units (type 6) — the x264 settings string
                    # "x264 - core … options: …" lives in one of them
                    "-bsf:v", "filter_units=remove_types=6",
                    # strip all input tags at container and stream level
                    "-map_metadata",     "-1",
                    "-map_metadata:s:v", "-1",
                    "-map_metadata:s:a", "-1",
                    # prevent the muxer writing its own "Lavf…" signature
                    "-fflags",  "+bitexact",
                    # remap ftyp brand
                    "-brand", "mp42",
                    "-movflags", "+faststart",
                    # explicit stream-level wipes (last, so they win)
                    "-metadata:s:v:0", "encoder=",
                    "-metadata:s:v:0", "handler_name= ",
                    "-metadata:s:a:0", "encoder=",
                    "-metadata:s:a:0", "handler_name= ",
                    dst,
                ],
                SCRUB_TIMEOUT, "scrub", src,
            )
            if r2.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg scrub failed (exit {r2.returncode}):\n{r2.stderr[-2000:]}"
                )
        finally:
            if os.path.exists(tmp_enc):
                os.remove(tmp_enc)

        print(f"[processor] encode+scrub ✓ → {os.path.basename(dst)!r}")

    # ── Stage 2 helpers ───────────────────────────────────────────────────────

    @classmethod
    def _check_tags(cls, path: str, ffprobe: str) -> dict:
        """
        Run ffprobe on one file.
        Returns a dict of forbidden tags found — empty dict means clean.
        ftyp tags pass by key; language/handler_name/vendor_id pass only with
        neutral values (see _NEUTRAL_ONLY_TAGS); every other non-empty tag fails.
        Never raises on metadata findings (caller decides what to do); raises
        if ffprobe itself fails, and a timeout is reported as a finding.
        """
        cmd = [
            ffprobe, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Αδύνατη η επαλήθευση → ΑΠΟΤΥΧΙΑ, ποτέ σιωπηλό πέρασμα: αλλιώς ένα
            # αρχείο με metadata θα έβγαινε στο Drive επειδή άργησε το ffprobe.
            print(f"[processor] ffprobe timeout — {os.path.basename(path)!r}")
            return {"_probe_timeout": f">{PROBE_TIMEOUT}s"}
        if r.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed on {path!r} (exit {r.returncode}):\n{r.stderr}"
            )

        data      = json.loads(r.stdout)
        forbidden: dict = {}

        # Container-level tags
        for k, v in data.get("format", {}).get("tags", {}).items():
            if _tag_violation(k, v):
                forbidden[f"container:{k}"] = v

        # Per-stream tags (video, audio, subtitles, …)
        for i, stream in enumerate(data.get("streams", [])):
            for k, v in stream.get("tags", {}).items():
                if _tag_violation(k, v):
                    forbidden[f"stream[{i}]:{k}"] = v

        return forbidden

    # ── Public helper (unchanged API) ─────────────────────────────────────────

    @classmethod
    def verify(cls, path: str) -> dict:
        """Returns technical info dict for external callers."""
        import av
        with av.open(path) as c:
            v = c.streams.video[0]
            a = next((s for s in c.streams if s.type == "audio"), None)
            return {
                "size_bytes":  os.path.getsize(path),
                "video_codec": v.codec_context.name,
                "width":       v.width,
                "height":      v.height,
                "fps":         float(v.average_rate),
                "metadata":    dict(c.metadata),
                "audio_codec": a.codec_context.name if a else None,
            }
