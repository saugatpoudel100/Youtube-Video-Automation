
"""STEP 5 — Optimized vertical Shorts video generator.

Features:
- 1080x1920 vertical video
- Ken Burns zoom using a lightweight NumPy frame function
- Voiceover audio
- Animated word-group captions
- Whisper model loaded only once per batch
- Faster FFmpeg encoding
- Automatic cleanup of video/audio resources
"""

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    ImageClip,
    VideoClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

import config
from store import get_by_status, update_post


W, H = config.VIDEO_W, config.VIDEO_H
FPS = 30
ZOOM_AMOUNT = 0.04


def _fit_cover(path):
    """Resize and crop an image to the final video dimensions once."""
    with Image.open(path) as source:
        img = source.convert("RGB")

        scale = max(W / img.width, H / img.height)

        new_size = (
            int(img.width * scale) + 2,
            int(img.height * scale) + 2,
        )

        img = img.resize(new_size, Image.Resampling.LANCZOS)

        left = (img.width - W) // 2
        top = (img.height - H) // 2

        img = img.crop((left, top, left + W, top + H))

        # Copy the pixels so the returned array is independent
        # of the Pillow image's lifetime.
        return np.array(img, dtype=np.uint8)


def _ken_burns(path, duration):
    """Build a zooming image clip without nested composites."""

    frame = _fit_cover(path)

    # Prepare a slightly larger image ONCE.
    # Zoom animation then uses fast NumPy cropping.
    zoom_w = int(W * (1 + ZOOM_AMOUNT)) + 2
    zoom_h = int(H * (1 + ZOOM_AMOUNT)) + 2

    enlarged = np.asarray(
        Image.fromarray(frame).resize(
            (zoom_w, zoom_h),
            Image.Resampling.LANCZOS,
        ),
        dtype=np.uint8,
    )

    extra_x = zoom_w - W
    extra_y = zoom_h - H

    def make_frame(t):
        # Slowly reveal more of the enlarged image.
        progress = min(max(t / max(duration, 0.01), 0.0), 1.0)

        # Start closer to the center, then gradually reduce
        # the crop offset for a gentle zoom-out/reframe effect.
        x = int((extra_x / 2) * (1 - progress))
        y = int((extra_y / 2) * (1 - progress))

        result = enlarged[y:y + H, x:x + W]

        # Return an exact-size frame for MoviePy.
        if result.shape[0] != H or result.shape[1] != W:
            result = result[:H, :W]

        return result

    return VideoClip(
        frame_function=make_frame,
        duration=duration,
    )


def _load_font(size):
    for name in (
        "arialbd.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass

    return ImageFont.load_default()


@lru_cache(maxsize=512)
def _caption_png(text):
    """Cache caption images so repeated text is rendered only once."""
    font = _load_font(72)
    pad = 40

    tmp = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(tmp)

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=6,
    )

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    img = Image.new(
        "RGBA",
        (tw + pad * 2, th + pad * 2),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(img)

    draw.text(
        (pad - bbox[0], pad - bbox[1]),
        text,
        font=font,
        fill="white",
        stroke_width=6,
        stroke_fill="black",
    )

    return np.array(img)


_whisper_model = None
_whisper_unavailable = False


def _get_whisper_model():
    """Load Whisper once and reuse it for all videos."""
    global _whisper_model, _whisper_unavailable

    if _whisper_unavailable:
        return None

    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel

            print("[video] Loading Whisper model...")

            _whisper_model = WhisperModel(
                config.WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )

        except Exception as exc:
            _whisper_unavailable = True
            print(f"[video] Captions disabled: {exc}")
            return None

    return _whisper_model


def _word_chunks(audio_path):
    """Return caption chunks with their start/end times."""
    model = _get_whisper_model()

    if model is None:
        return []

    segments, _ = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
    )

    chunks = []
    group = []

    for segment in segments:
        for word in segment.words or []:
            group.append(word)

            if len(group) >= 3:
                text = " ".join(
                    item.word.strip() for item in group
                )

                chunks.append(
                    (
                        text.upper(),
                        group[0].start,
                        group[-1].end,
                    )
                )
                group = []

    if group:
        text = " ".join(
            item.word.strip() for item in group
        )

        chunks.append(
            (
                text.upper(),
                group[0].start,
                group[-1].end,
            )
        )

    return chunks


def _build(post):
    audio = None
    bg = None
    video = None
    caption_clips = []

    try:
        audio = AudioFileClip(post["audio_file"])
        duration = audio.duration

        images = post.get("stock_images") or []

        if not images:
            raise RuntimeError("No stock images found")

        # Distribute image durations evenly across the voiceover.
        per_image = duration / len(images)

        print(
            f"   [render] {post['shortcode']}: "
            f"{len(images)} images, {duration:.1f}s"
        )

        image_clips = [
            _ken_burns(path, per_image)
            for path in images
        ]

        bg = concatenate_videoclips(
            image_clips,
            method="chain",
        ).with_duration(duration)

        layers = [bg]

        # Transcribe once per video; the model itself is cached.
        for text, start, end in _word_chunks(post["audio_file"]):
            caption = (
                ImageClip(_caption_png(text))
                .with_start(start)
                .with_duration(max(end - start, 0.15))
                .with_position(("center", int(H * 0.72)))
            )

            caption_clips.append(caption)
            layers.append(caption)

        video = (
            CompositeVideoClip(
                layers,
                size=(W, H),
                bg_color=(0, 0, 0),
            )
            .with_audio(audio)
            .with_duration(duration)
        )

        out = config.VIDEO_DIR / f"{post['shortcode']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        video.write_videofile(
            str(out),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4,
            logger="bar",
        )

        return str(out)

    finally:
        # Release FFmpeg readers and resources even if rendering fails.
        if video is not None:
            video.close()

        if bg is not None:
            bg.close()

        for clip in caption_clips:
            clip.close()

        if audio is not None:
            audio.close()


def run():
    todo = get_by_status("voiced")

    print(f"[video] {len(todo)} videos to build.")

    for code, post in todo.items():
        try:
            path = _build(post)

            update_post(
                code,
                video_file=path,
                status="video_ready",
            )

            print(f"   + {code}: {path}")

        except KeyboardInterrupt:
            print("\n[video] Interrupted by user.")
            raise

        except Exception as exc:
            print(f"   ! video failed ({code}): {exc}")

    print("[video] Batch finished.")
    return get_by_status("video_ready")


if __name__ == "__main__":
    run()
