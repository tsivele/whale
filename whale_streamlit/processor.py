"""
Video post-processing pipeline.
No external CLI dependencies — uses PyAV (libav bindings already in requirements.txt).

What it does:
  - Re-encodes video with libx264 (CRF 23, medium preset)
  - Re-encodes audio with AAC
  - Strips ALL source metadata (no -map_metadata equivalent needed — new container,
    new streams, nothing is copied)
  - Sets movflags +faststart (moov atom at start, optimal for web streaming)
  - Returns path of the cleaned output file

Usage:
    from processor import VideoProcessor
    out_path = VideoProcessor.process(src_path)          # blocking
    out_path = VideoProcessor.process(src_path, progress_cb=lambda p, t: print(p, t))
"""

import os
import tempfile
import av


class VideoProcessor:
    """Stateless — all methods are classmethods."""

    OUTPUT_SUFFIX = "_clean.mp4"

    @classmethod
    def process(cls, src: str, progress_cb=None) -> str:
        """
        Re-encode src, strip metadata, write faststart MP4 next to src.

        progress_cb(pct: float, text: str) is called periodically with 0.0–1.0.
        Returns the path of the output file.
        Raises on any error.
        """
        base = os.path.splitext(src)[0]
        dst = base + cls.OUTPUT_SUFFIX
        # Avoid collisions if already processed
        if os.path.exists(dst):
            os.remove(dst)

        if progress_cb:
            progress_cb(0.02, "Ανοίγω αρχείο...")

        with av.open(src) as inp:
            v_in = inp.streams.video[0]
            a_in = next((s for s in inp.streams if s.type == "audio"), None)

            total_frames = v_in.frames or None  # may be 0 if not in header

            # movflags +faststart is an optimisation — skip if the av version rejects it.
            try:
                _out_ctx = av.open(dst, "w", format="mp4", options={"movflags": "+faststart"})
                _out_ctx.close()
                _open_kwargs = {"options": {"movflags": "+faststart"}}
            except Exception:
                _open_kwargs = {}
            with av.open(dst, "w", format="mp4", **_open_kwargs) as out:
                v_out = out.add_stream("libx264", rate=v_in.average_rate)
                v_out.width  = v_in.width
                v_out.height = v_in.height
                v_out.pix_fmt = "yuv420p"
                v_out.options = {"crf": "23", "preset": "medium"}

                a_out = None
                if a_in:
                    a_out = out.add_stream("aac", rate=a_in.rate)
                    a_out.layout = "stereo" if a_in.channels >= 2 else "mono"

                streams_to_demux = [s for s in [v_in, a_in] if s]
                encoded_frames = 0

                for packet in inp.demux(*streams_to_demux):
                    if packet.dts is None:
                        continue
                    for frame in packet.decode():
                        frame.pts = None  # let encoder assign pts
                        if isinstance(frame, av.VideoFrame):
                            for pkt in v_out.encode(frame):
                                out.mux(pkt)
                            encoded_frames += 1
                            if progress_cb and total_frames:
                                pct = min(0.92, 0.05 + 0.87 * encoded_frames / total_frames)
                                progress_cb(pct, f"Επεξεργασία frame {encoded_frames}/{total_frames}...")
                        elif a_out:
                            for pkt in a_out.encode(frame):
                                out.mux(pkt)

                # Flush encoders
                for pkt in v_out.encode(None):
                    out.mux(pkt)
                if a_out:
                    for pkt in a_out.encode(None):
                        out.mux(pkt)

        if progress_cb:
            progress_cb(1.0, "✅ Ολοκληρώθηκε!")

        return dst

    @classmethod
    def verify(cls, path: str) -> dict:
        """Return basic info dict for verification. Raises if file is corrupt."""
        with av.open(path) as c:
            v = c.streams.video[0]
            a = next((s for s in c.streams if s.type == "audio"), None)
            return {
                "size_bytes": os.path.getsize(path),
                "video_codec": v.codec_context.name,
                "width": v.width,
                "height": v.height,
                "metadata": dict(c.metadata),
                "audio_codec": a.codec_context.name if a else None,
            }
