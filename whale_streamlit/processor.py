"""
Video post-processing pipeline — re-encode with libx264/aac, strips all source metadata.
Works with PyAV 11.x and 17.x. Correct fps guaranteed via input-stream time_base alignment.
"""

import os
import tempfile
import av


class VideoProcessor:

    @classmethod
    def process(cls, src: str, progress_cb=None) -> str:
        """
        Re-encodes src into a clean MP4 with libx264/aac, stripping all source metadata.
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

                fps = float(v_in.average_rate)
                tb = v_in.time_base
                # pts_step: how many time_base ticks = one frame
                # e.g. tb=1/90000, fps=25 → pts_step=3600
                pts_step = round(tb.denominator / (fps * tb.numerator))

                total_frames = int(v_in.frames) if v_in.frames else 0
                print(f"[processor] {v_in.codec_context.name} "
                      f"{v_in.width}x{v_in.height} "
                      f"{fps:.3f}fps  tb={tb}  pts_step={pts_step}  "
                      f"frames={total_frames}  audio={'yes' if a_in else 'no'}")

                if progress_cb:
                    progress_cb(0.10, "Ξεκινώ re-encode...")

                with av.open(dst, "w", format="mp4") as out:
                    v_out = out.add_stream("libx264", rate=v_in.average_rate)
                    v_out.width = v_in.width
                    v_out.height = v_in.height
                    v_out.pix_fmt = "yuv420p"

                    a_out = None
                    if a_in:
                        a_out = out.add_stream("aac")

                    v_idx = 0
                    streams = [s for s in [v_in, a_in] if s]

                    for packet in inp.demux(*streams):
                        if packet.dts is None:
                            continue

                        if packet.stream == v_in:
                            for frame in packet.decode():
                                # Assign pts in the input stream's time_base units
                                # so the encoder produces the correct frame rate
                                frame.pts = v_idx * pts_step
                                v_idx += 1
                                for pkt in v_out.encode(frame):
                                    out.mux(pkt)
                                if progress_cb and total_frames:
                                    pct = min(0.95, 0.10 + 0.85 * v_idx / total_frames)
                                    progress_cb(pct, f"Frame {v_idx}/{total_frames}...")

                        elif a_out and packet.stream == a_in:
                            for frame in packet.decode():
                                for pkt in a_out.encode(frame):
                                    out.mux(pkt)

                    # Flush encoders
                    for pkt in v_out.encode(None):
                        out.mux(pkt)
                    if a_out:
                        for pkt in a_out.encode(None):
                            out.mux(pkt)

            size = os.path.getsize(dst)
            print(f"[processor] done — {size} bytes")
            if size < 1000:
                raise RuntimeError(f"Output file suspiciously small: {size} bytes")

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
