"""
Video post-processing pipeline — stream copy remux, no re-encode, no ffmpeg CLI.
Strips all source metadata by creating a new container.
Preserves original fps, bitrate, and quality exactly.
"""

import os
import tempfile
import av


class VideoProcessor:

    @classmethod
    def process(cls, src: str, progress_cb=None) -> str:
        """
        Remux src into a clean MP4 — no re-encode, strips all source metadata.
        Returns path of the output file.
        """
        if progress_cb:
            progress_cb(0.05, "Ανοίγω αρχείο...")

        dst = tempfile.mktemp(suffix=".mp4")
        print(f"[processor] src={src!r}  dst={dst!r}")

        try:
            with av.open(src) as inp:
                v_in = inp.streams.video[0]
                a_in = next((s for s in inp.streams if s.type == "audio"), None)
                total = v_in.frames or 0
                print(f"[processor] {v_in.codec_context.name} "
                      f"{v_in.width}x{v_in.height} "
                      f"{float(v_in.average_rate):.2f}fps  "
                      f"audio={'yes' if a_in else 'no'}")

                if progress_cb:
                    progress_cb(0.10, "Αντιγραφή streams...")

                with av.open(dst, "w", format="mp4") as out:
                    # Stream copy — copy codec params, mux packets without re-encoding
                    out_v = out.add_stream(v_in.codec_context.name)
                    out_v.codec_context.extradata = v_in.codec_context.extradata
                    out_v.width     = v_in.width
                    out_v.height    = v_in.height
                    out_v.pix_fmt   = v_in.pix_fmt or "yuv420p"
                    out_v.time_base = v_in.time_base

                    out_a = None
                    if a_in:
                        out_a = out.add_stream(a_in.codec_context.name)
                        out_a.codec_context.extradata = a_in.codec_context.extradata
                        out_a.time_base = a_in.time_base

                    copied = 0
                    in_streams = [s for s in [v_in, a_in] if s]
                    for packet in inp.demux(*in_streams):
                        if packet.dts is None:
                            continue
                        if packet.stream == v_in:
                            packet.stream = out_v
                            out.mux(packet)
                            copied += 1
                            if progress_cb and total:
                                pct = min(0.95, 0.10 + 0.85 * copied / total)
                                progress_cb(pct, f"Frame {copied}/{total}...")
                        elif out_a and packet.stream == a_in:
                            packet.stream = out_a
                            out.mux(packet)

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
                "fps": float(v.average_rate),
                "metadata": dict(c.metadata),
                "audio_codec": a.codec_context.name if a else None,
            }
