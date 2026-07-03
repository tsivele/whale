"""
Video post-processing pipeline — 3-stage: re-encode → metadata scrub → verify.

  Stage 1 (PyAV):    libx264/aac re-encode — correct fps, clean codec headers
  Stage 2 (FFmpeg):  stream copy -map_metadata -1 -fflags +bitexact
  Stage 3 (ffprobe): strict JSON parse — any non-structural tag raises ValueError

process() accepts a single path OR a list of paths.
When given a list, it encodes+scrubs all files first, then verifies every one of
them and aggregates failures into a single comprehensive error before raising.
"""

import json
import os
import subprocess
import tempfile
from typing import List, Union

import av


# MP4 ftyp-box fields that ffprobe surfaces as TAGs but are structural
# container requirements (not user-injectable metadata). They live in the
# 'ftyp' MP4 box — removing them corrupts the container.
_STRUCTURAL_TAGS = frozenset({
    "major_brand",
    "minor_version",
    "compatible_brands",
})


def _ffbin():
    """Return (ffmpeg_path, ffprobe_path), preferring static_ffmpeg."""
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass
    return "ffmpeg", "ffprobe"


class VideoProcessor:

    @classmethod
    def process(
        cls,
        src: Union[str, os.PathLike, List[Union[str, os.PathLike]]],
        progress_cb=None,
    ) -> Union[str, List[str]]:
        """
        Full pipeline: re-encode → metadata scrub → strict verify.

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

        # ── Stage 1 + 2: encode → scrub, one file at a time ─────────────────
        for i, src_path in enumerate(inputs):
            tmp_raw   = tempfile.mktemp(suffix="_raw.mp4")
            tmp_clean = tempfile.mktemp(suffix="_clean.mp4")

            # Scale this file's 0→1 progress into its share of 0 → 0.93 total.
            # Single-mode skips scaling so the existing progress values are
            # passed through unchanged (backward-compatible).
            if n > 1:
                _slot_start = i       * (0.93 / n)
                _slot_size  = 0.93 / n
                def _cb(p, t, _s=_slot_start, _z=_slot_size):
                    if progress_cb:
                        progress_cb(_s + p * _z, t)
            else:
                _cb = progress_cb

            print(f"[processor] ({i + 1}/{n}) src={src_path!r}")

            try:
                # ── Stage 1: PyAV re-encode ──────────────────────────────────
                cls._reencode(src_path, tmp_raw, _cb)

                # ── Stage 2: FFmpeg metadata scrub ───────────────────────────
                if _cb:
                    _cb(0.95, f"[{i+1}/{n}] ⚙️ Αφαίρεση metadata..."
                              if n > 1 else "⚙️ Αφαίρεση metadata...")
                cls._scrub(tmp_raw, tmp_clean, ffmpeg)

                size = os.path.getsize(tmp_clean)
                if size < 1000:
                    raise RuntimeError(
                        f"[{i+1}/{n}] Output suspiciously small: {size} bytes"
                    )

                outputs.append(tmp_clean)

            except Exception:
                # Abort: destroy every clean file produced so far
                for o in outputs:
                    if os.path.exists(o):
                        os.remove(o)
                if os.path.exists(tmp_clean):
                    os.remove(tmp_clean)
                raise
            finally:
                # Always remove intermediate re-encoded file
                if os.path.exists(tmp_raw):
                    os.remove(tmp_raw)

        # ── Stage 3: verify ALL outputs — never stop on first failure ────────
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

    # ── Stage 1: PyAV re-encode ───────────────────────────────────────────────

    @classmethod
    def _reencode(cls, src: str, dst: str, progress_cb=None) -> None:
        if progress_cb:
            progress_cb(0.05, "Ανοίγω αρχείο...")

        with av.open(src) as inp:
            v_in = inp.streams.video[0]
            a_in = next((s for s in inp.streams if s.type == "audio"), None)

            fps      = float(v_in.average_rate)
            tb       = v_in.time_base
            pts_step = round(tb.denominator / (fps * tb.numerator))
            total    = int(v_in.frames) if v_in.frames else 0

            print(
                f"[processor] {v_in.codec_context.name} "
                f"{v_in.width}x{v_in.height} "
                f"{fps:.3f}fps  tb={tb}  pts_step={pts_step}  "
                f"frames={total}  audio={'yes' if a_in else 'no'}"
            )

            if progress_cb:
                progress_cb(0.10, "Ξεκινώ re-encode...")

            with av.open(dst, "w", format="mp4") as out:
                v_out = out.add_stream("libx264", rate=v_in.average_rate)
                v_out.width   = v_in.width
                v_out.height  = v_in.height
                v_out.pix_fmt = "yuv420p"

                a_out = out.add_stream("aac") if a_in else None

                v_idx   = 0
                streams = [s for s in [v_in, a_in] if s]

                for packet in inp.demux(*streams):
                    if packet.dts is None:
                        continue
                    if packet.stream == v_in:
                        for frame in packet.decode():
                            frame.pts = v_idx * pts_step
                            v_idx += 1
                            for pkt in v_out.encode(frame):
                                out.mux(pkt)
                            if progress_cb and total:
                                pct = min(0.92, 0.10 + 0.82 * v_idx / total)
                                progress_cb(pct, f"Frame {v_idx}/{total}...")
                    elif a_out and packet.stream == a_in:
                        for frame in packet.decode():
                            for pkt in a_out.encode(frame):
                                out.mux(pkt)

                for pkt in v_out.encode(None):
                    out.mux(pkt)
                if a_out:
                    for pkt in a_out.encode(None):
                        out.mux(pkt)

    # ── Stage 2: FFmpeg metadata scrub ────────────────────────────────────────

    @classmethod
    def _scrub(cls, src: str, dst: str, ffmpeg: str) -> None:
        """
        Stream-copy src → dst, wiping every metadata layer:

          -map_metadata -1           drop all container-level tags
          -map_metadata:s:v:0 -1     drop video-stream tags
          -map_metadata:s:a:0 -1     drop audio-stream tags
          -fflags +bitexact          suppress libavformat writing 'encoder=Lavf…'
          -flags:v +bitexact         suppress per-video-stream encoder annotation
          -flags:a +bitexact         suppress per-audio-stream encoder annotation
        """
        cmd = [
            ffmpeg, "-y", "-i", src,
            "-map_metadata",       "-1",
            "-map_metadata:s:v:0", "-1",
            "-map_metadata:s:a:0", "-1",
            "-c",       "copy",
            "-fflags",  "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            dst,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"FFmpeg scrub failed (exit {r.returncode}):\n{r.stderr[-2000:]}"
            )
        print(f"[processor] scrub ✓ → {os.path.basename(dst)!r}")

    # ── Stage 3 helpers ───────────────────────────────────────────────────────

    @classmethod
    def _check_tags(cls, path: str, ffprobe: str) -> dict:
        """
        Run ffprobe on one file.
        Returns a dict of forbidden tags found — empty dict means clean.
        Never raises on metadata findings (caller decides what to do).

        Whitelist rationale:
          major_brand / minor_version / compatible_brands
            live in the MP4 'ftyp' structural box, not the 'udta' metadata box.
            They identify the MP4 profile and are required by the container spec.
            They contain no user data and carry zero tracking risk.

          Everything else (encoder, creation_time, comment, C2PA, EXIF, …)
            must be absent — any hit is flagged as forbidden.
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
