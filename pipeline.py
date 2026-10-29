"""Run the whole pipeline end-to-end: scrape -> rewrite -> images -> voice ->
video -> upload. Each step processes whatever posts are pending for it, so a
failure in one post never blocks the others. Run it on a schedule (cron / Task
Scheduler / GitHub Actions) to keep the channel fed.

    python pipeline.py            # full run
    python pipeline.py rewrite    # run a single step (scrape/rewrite/images/voice/video/upload)
"""
import sys
import traceback

import step1_rss
import step1_scrape
import step1b_scrape_fb
import step2_rewrite
import step3_images
import step4_voice
import step5_video
import step6_upload

STEPS = {
    "scrape_rss": step1_rss.run,
    "scrape": step1_scrape.run,
    "scrape_fb": step1b_scrape_fb.run,
    "rewrite": step2_rewrite.run,
    "images": step3_images.run,
    "voice": step4_voice.run,
    "video": step5_video.run,
    "upload": step6_upload.run,
}


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    steps = {only: STEPS[only]} if only in STEPS else STEPS
    for name, fn in steps.items():
        print(f"\n===== {name.upper()} =====")
        try:
            fn()
        except SystemExit as e:
            print(f"[{name}] stopped: {e}")
        except Exception:
            print(f"[{name}] ERROR:\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
