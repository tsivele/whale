"""
Video post-processing pipeline — 2-stage: re-encode+scrub → verify.

  Stage 1 (FFmpeg):  libx264/aac re-encode with all metadata stripped inline
                     (-map_metadata -1, -fflags +bitexact, -flags:v/a +bitexact)
  Stage 2 (ffprobe): strict JSON parse — any non-structural tag raises ValueError

process() accepts a single path OR a list of paths.
When given a list, it encodes+scrubs all files first, then verifies every one of
them and aggregates failures into a single comprehensive error before raising.
"""

import json
import os
import subprocess
import tempfile
from typing import List, Union


# MP4 ftyp-box fields that ffprobe surfaces as TAGs but are structural
# container requirements (not user-injectable metadata). They live in the
# 'ftyp' MP4 box — removing them corrupts the container.
_STRUCTURAL_TAGS = frozenset({
    "major_brand",
    "minor_version",
    "compatible_brands",
})


def _find_bin(name: str) -> str:
    """
    Locate ffmpeg/ffprobe with four fallbacks (most reliable first):
      1. imageio_ffmpeg bundled binary  (ffmpeg only — most reliable on Streamlit Cloud)
      2. PATH search                    (works if packages.txt installed system ffmpeg)
      3. Known fixed paths              (/usr/bin, /usr/local/bin, /bin)
      4. Bare name                      (last resort — subprocess will raise FileNotFoundError)
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


def _ffbin():
    """Return (ffmpeg_path, ffprobe_path | None)."""
    ffmpeg = _find_bin("ffmpeg")
    ffprobe = _find_bin("ffprobe")
    # If ffprobe resolved to bare "ffprobe" and doesn't exist, signal unavailable
    if ffprobe == "ffprobe" and not os.path.exists(ffprobe):
        import shutil as _sh
        if _sh.which("ffprobe") is None:
            ffprobe = None
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

        On verification failure all output files are deleted before raising,
        so nothing dirty ever escapes the pipeline.
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
        if ffprobe is None:
            print("[processor] ffprobe not available — skipping tag verification (scrub still applied)")
        else:
            if progress_cb:
                progress_cb(0.95, "🔍 Επαλήθευση metadata...")

            failures: dict = {}          # {clean_path: {tag_key: tag_value, …}}
            for path in outputs:
                found = cls._check_tags(path, ffprobe)
                if found:
                    failures[path] = found
                    print(f"[processor] verify FAIL — {os.path.basename(path)!r}: {found}")
                else:
                    print(f"[processor] verify ✓  — {os.path.basename(path)!r} is clean")

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
        Re-encode src → dst with libx264/aac. Five suppression layers:

          Layer 1 — map_metadata -1
            Drop every tag copied from the input container/streams.

          Layer 2 — bitexact flags
            Prevent libavformat/libavcodec injecting 'encoder=Lavf…' /
            'encoder=Lavc…' during the write phase.

          Layer 3 — explicit encoder empty-overwrite
            Force encoder tag to "" at container and both stream levels.
            In FFmpeg ≥4 an empty value equals tag removal.

          Layer 4 — handler_name empty-overwrite
            Clears 'VideoHandler'/'SoundHandler' from the hdlr box, which
            is the clearest FFmpeg fingerprint visible in stream metadata.

          Layer 5 — brand remapping
            Rewrites the ftyp major_brand from 'isom' (FFmpeg default) to
            'mp42' (MPEG-4 v2, used by Android/generic camera apps).
        """
        cmd = [
            ffmpeg, "-y", "-i", src,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            # Layer 1
            "-map_metadata",       "-1",
            "-map_metadata:s:v:0", "-1",
            "-map_metadata:s:a:0", "-1",
            # Layer 2
            "-fflags",  "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            # Layer 3 — encoder tags
            "-metadata",       "encoder=",
            "-metadata:s:v:0", "encoder=",
            "-metadata:s:a:0", "encoder=",
            # Layer 4 — handler names
            "-metadata:s:v:0", "handler_name=",
            "-metadata:s:a:0", "handler_name=",
            # Layer 5 — ftyp brand (mp42 = generic Android/camera, not isom/FFmpeg)
            "-brand", "mp42",
            dst,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"FFmpeg encode failed (exit {r.returncode}):\n{r.stderr[-2000:]}"
            )
        print(f"[processor] encode+scrub ✓ → {os.path.basename(dst)!r}")

    # ── Stage 2 helpers ───────────────────────────────────────────────────────

    @classmethod
    def _check_tags(cls, path: str, ffprobe: str) -> dict:
        """
        Run ffprobe on one file.
        Returns a dict of forbidden tags found — empty dict means clean.
        Never raises on metadata findings (caller decides what to do).
        """
        cmd = [
            ffprobe, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed on {path!r} (exit {r.returncode}):\n{r.stderr}"
            )

        data      = json.loads(r.stdout)
        forbidden: dict = {}

        # Container-level tags
        for k, v in data.get("format", {}).get("tags", {}).items():
            if k.lower() not in _STRUCTURAL_TAGS:
                forbidden[f"container:{k}"] = v

        # Per-stream tags (video, audio, subtitles, …)
        for i, stream in enumerate(data.get("streams", [])):
            for k, v in stream.get("tags", {}).items():
                if k.lower() not in _STRUCTURAL_TAGS:
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
