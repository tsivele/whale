"""
Video post-processing pipeline — PyAV, no ffmpeg CLI.
"""

import os
import tempfile
import av


def _try_open_output(path: str):
    """Open av output, trying mp4 then matroska as fallback."""
    try:
        return av.open(path, "w", format="mp4")
    except Exception:
        mkv = path.replace(".mp4", ".mkv")
        return av.open(mkv, "w", format="matroska")


class VideoProcessor:

    @classmethod
    def process(cls, src: str, progress_cb=None) -> str:
        if progress_cb:
            progress_cb(0.02, "Ανοίγω αρχείο...")

        # Generate a temp path WITHOUT creating the file — av needs to create it itself
        dst = tempfile.mktemp(suffix=".mp4")
        print(f"[processor] src={src!r}  dst={dst!r}")

        try:
            with av.open(src) as inp:
                v_in = inp.streams.video[0]
                a_in = next((s for s in inp.streams if s.type == "audio"), None)
                total_frames = v_in.frames or 0
                print(f"[processor] {v_in.codec_context.name} {v_in.width}x{v_in.height}"
                      f"  audio={'yes' if a_in else 'no'}  frames={total_frames}")

                with _try_open_output(dst) as out:
                    # Try libx264, fall back to mpeg4 (always built-in)
                    try:
                        v_out = out.add_stream("libx264", rate=v_in.average_rate)
                        v_out.options = {"crf": "23", "preset": "medium"}
                    except Exception as e:
                        print(f"[processor] libx264 unavailable ({e}), using mpeg4")
                        v_out = out.add_stream("mpeg4", rate=v_in.average_rate)

                    v_out.width  = v_in.width
                    v_out.height = v_in.height
                    v_out.pix_fmt = "yuv420p"

                    a_out = None
                    if a_in:
                        try:
                            a_out = out.add_stream("aac", rate=a_in.rate)
                            a_out.layout = "stereo" if a_in.channels >= 2 else "mono"
                        except Exception as e:
                            print(f"[processor] aac unavailable ({e}), skipping audio")

                    encoded = 0
                    for packet in inp.demux(*[s for s in [v_in, a_in] if s]):
                        if packet.dts is None:
                            continue
                        for frame in packet.decode():
                            frame.pts = None
                            if isinstance(frame, av.VideoFrame):
                                for pkt in v_out.encode(frame):
                                    out.mux(pkt)
                                encoded += 1
                                if progress_cb and total_frames:
                                    pct = min(0.92, 0.05 + 0.87 * encoded / total_frames)
                                    progress_cb(pct, f"Frame {encoded}/{total_frames}...")
                            elif a_out:
                                for pkt in a_out.encode(frame):
                                    out.mux(pkt)

                    for pkt in v_out.encode(None):
                        out.mux(pkt)
                    if a_out:
                        for pkt in a_out.encode(None):
                            out.mux(pkt)

            print(f"[processor] done — {os.path.getsize(dst)} bytes")

        except Exception:
            if os.path.exists(dst):
                os.remove(dst)
            raise

        if progress_cb:
            progress_cb(1.0, "✅ Ολοκληρώθηκε!")

        return dst

    @classmethod
    def verify(cls, path: str) -> dict:
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
