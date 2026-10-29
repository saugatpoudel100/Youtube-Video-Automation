# Football Shorts Automation

Turns a football journalist's public Instagram posts into original-commentary
YouTube Shorts: scrape → AI rewrite → license-clean images → AI voiceover →
captioned vertical video → upload.

No database — everything lives in `data/posts.json` plus folders under `data/`.

## ⚠️ Read this first (keeps your channel alive)

- The pipeline writes **original commentary that credits Fabrizio Romano**, it
  does not republish his captions. Don't change it to copy his text verbatim —
  that's what gets channels demonetized under YouTube's reused-content policy.
- The video uses **royalty-free Pexels images**, not the scraped Instagram
  press photos (those are licensed to agencies/clubs and aren't yours to
  republish). The scraped image is kept only as internal reference.
- Scraping Instagram is against its Terms of Service. Keep volume low, use a
  secondary account, and don't hammer it. For serious use, the official
  Instagram Graph API is the sanctioned route.
- Start with `YOUTUBE_PRIVACY=unlisted` until you're happy with the output.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium
```

Install **FFmpeg** and put it on your PATH (needed for video).

Copy `.env.example` to `.env` and fill in your keys:
- Gemini: https://aistudio.google.com/apikey
- ElevenLabs: https://elevenlabs.io  (set the voice name, e.g. `Paul`)
- Pexels (free): https://www.pexels.com/api/

For uploads, create an OAuth **Desktop** client in Google Cloud Console (enable
the *YouTube Data API v3*), download the JSON, and save it as
`client_secret.json` in this folder.

## Run

First run the scraper alone so you can log into Instagram in the browser window:

```bash
python step1_scrape.py
```

Then the rest, or the whole thing:

```bash
python pipeline.py            # full pipeline
python pipeline.py rewrite    # just one step: scrape/rewrite/images/voice/video/upload
```

## How it flows

Each post moves through statuses in `data/posts.json`:

```
new -> rewritten -> images_ready -> voiced -> video_ready -> published
```

Every step only touches posts at its expected status, so you can re-run safely;
finished posts are skipped and a failure on one post won't block the others.

| File | Step |
|------|------|
| `step1_scrape.py` | Instagram → caption + reference images |
| `step2_rewrite.py` | Gemini → original script, title, description, tags |
| `step3_images.py` | Pexels → license-clean vertical images |
| `step4_voice.py` | ElevenLabs → MP3 voiceover |
| `step5_video.py` | MoviePy → Ken Burns + Whisper captions → MP4 |
| `step6_upload.py` | YouTube Data API → upload |
| `pipeline.py` | runs them in order |

## Scheduling

Point Windows Task Scheduler / cron / a GitHub Actions cron job at
`python pipeline.py`. Note that uploading needs the cached `token.json`, and the
scraper needs the saved `ig_session/` — generate both once interactively before
automating.

## Common gotchas

- **Captions missing**: `faster-whisper` not installed (the video still builds
  without them), or no FFmpeg available.
- **moviepy install fails with `KeyError: '__version__'`**: you pinned the old
  `moviepy==1.0.3`, which won't build on Python 3.13. Use `moviepy>=2.0`
  (already set in requirements.txt).
- **Voice not found**: the `ELEVENLABS_VOICE` name doesn't exist on your account;
  it falls back to the first available voice and prints a warning.
- **Scraper stuck at ~12 posts**: Instagram paginates slowly; raise `SCROLL_PAUSE`
  rather than scrolling faster.
