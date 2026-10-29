"""STEP 1b — Scrape the Facebook page as a BACKUP source.

Adds posts from facebook.com/fabrizioromanoherewego into the SAME data/posts.json,
but skips anything whose news already arrived via Instagram (content-similarity
dedup), so the same transfer never becomes two videos.

Facebook is harder than Instagram: it forces a login wall and flags automation
hard, so use a SEPARATE/throwaway account. First run keep HEADLESS=False and log
in manually in the window; the session is saved in fb_session/.

NOTE: Facebook's markup and GraphQL shapes are messy and change often. This is a
best-effort extractor (caption text + timestamp); images for FB posts come from
step 3 like everything else. If it captures too little/too much, tune MIN_LEN and
the selectors in _dom_fallback().
"""
import difflib
import hashlib
import json
import re
import time

from playwright.sync_api import sync_playwright

import config
from store import load_posts, save_posts

HEADLESS = False
MAX_SCROLLS = 15
SCROLL_PAUSE = 3.0
MIN_LEN = 50            # ignore short text (comments, UI noise)


# ---------- content dedup ----------
def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def _is_duplicate(caption, existing_norm, threshold):
    n = _norm(caption)
    if not n:
        return True
    for other in existing_norm:
        if not other:
            continue
        # quick prefix check first, then full ratio
        if n[:40] == other[:40]:
            return True
        if difflib.SequenceMatcher(None, n, other).ratio() >= threshold:
            return True
    return False


# ---------- FB response parsing ----------
def _parse_bodies(text):
    """FB returns single JSON, line-delimited JSON, or a 'for(;;);' prefix."""
    text = text.strip()
    if text.startswith("for (;;);"):
        text = text[len("for (;;);"):]
    objs = []
    try:
        return [json.loads(text)]
    except Exception:
        pass
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                objs.append(json.loads(line))
            except Exception:
                pass
    return objs


def _walk(node, out):
    """Find FB post nodes: a dict with message.text."""
    if isinstance(node, dict):
        msg = node.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("text"), str):
            t = msg["text"].strip()
            if len(t) >= MIN_LEN:
                ts = (node.get("creation_time") or node.get("publish_time")
                      or node.get("created_time"))
                pid = node.get("post_id") or node.get("id")
                out.append((t, pid, ts))
        for v in node.values():
            _walk(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out)


def _dom_fallback(page):
    """If JSON interception finds nothing, grab visible post text from the DOM."""
    texts = []
    try:
        nodes = page.query_selector_all('div[data-ad-preview="message"], div[data-ad-comet-preview="message"]')
        for n in nodes:
            t = (n.inner_text() or "").strip()
            if len(t) >= MIN_LEN:
                texts.append(t)
    except Exception:
        pass
    return texts


def _make_post(text, pid, ts):
    words = text.split()
    code = f"fb_{hashlib.md5(_norm(text).encode()).hexdigest()[:16]}"
    return {
        "shortcode": code,
        "url": (f"https://www.facebook.com/{pid}" if pid
                else config.FB_TARGET),
        "timestamp": ts,
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts else None,
        "caption": text,
        "hashtags": [w[1:] for w in words if w.startswith("#")],
        "mentions": [w[1:] for w in words if w.startswith("@")],
        "image_urls": [], "video_urls": [],
        "like_count": None, "comment_count": None,
        "ig_images": [],
        "source": "facebook",
        "status": "new",
    }


def run():
    existing = load_posts()
    existing_norm = [_norm(p.get("caption", "")) for p in existing.values()]
    print(f"[fb] {len(existing)} posts already stored (all sources).")
    captured = {}      # caption text -> (pid, ts)

    def on_response(response):
        url = response.url
        if "graphql" not in url and "/api/" not in url:
            return
        try:
            body = response.text()
        except Exception:
            return
        for obj in _parse_bodies(body):
            found = []
            _walk(obj, found)
            for text, pid, ts in found:
                if text not in captured:
                    captured[text] = (pid, ts)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(config.FB_SESSION_DIR), headless=HEADLESS,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)
        page.goto(config.FB_TARGET, wait_until="domcontentloaded")
        time.sleep(5)

        if "login" in page.url.lower() or "/login" in page.url:
            print(">> Not logged in. Log into Facebook in the window (90s)...")
            time.sleep(90)
            page.goto(config.FB_TARGET, wait_until="domcontentloaded")
            time.sleep(5)

        for i in range(MAX_SCROLLS):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(SCROLL_PAUSE)
            print(f"   scroll {i + 1}/{MAX_SCROLLS} ... {len(captured)} captions seen")

        # DOM fallback if JSON gave us nothing
        if not captured:
            for t in _dom_fallback(page):
                captured.setdefault(t, (None, None))
        ctx.close()

    threshold = config.DEDUP_THRESHOLD
    added, skipped = 0, 0
    batch_norm = []     # also dedup within this FB batch
    for text, (pid, ts) in captured.items():
        if _is_duplicate(text, existing_norm + batch_norm, threshold):
            skipped += 1
            continue
        post = _make_post(text, pid, ts)
        if post["shortcode"] in existing:
            skipped += 1
            continue
        existing[post["shortcode"]] = post
        existing_norm.append(_norm(text))
        batch_norm.append(_norm(text))
        added += 1
        print(f"   + {post['shortcode']}: {text[:60]}")

    save_posts(existing)
    print(f"[fb] {len(captured)} captions seen, {added} new, {skipped} skipped "
          f"(already on Instagram / duplicate).")
    return {c: p for c, p in existing.items()
            if p.get("source") == "facebook" and p.get("status") == "new"}


if __name__ == "__main__":
    run()