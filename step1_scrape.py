"""STEP 1 — Scrape latest posts (caption + images) into data/posts.json.

Intercepts Instagram's background JSON instead of parsing HTML, so it survives
layout changes. Downloads reference images locally. Only NEW shortcodes are
added, so it is safe to run repeatedly / on a schedule.

First run: keep HEADLESS=False and log in manually; the session is saved in
ig_session/ and reused afterwards.
"""
import time

import requests
from playwright.sync_api import sync_playwright

import config
from store import load_posts, save_posts

HEADLESS = False
MAX_SCROLLS = 8   # keep recent/top content only; bump up if you need more history
SCROLL_PAUSE = 2.5
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _best_image(node):
    iv = node.get("image_versions2") or {}
    cands = iv.get("candidates") or []
    if cands:
        return cands[0].get("url")
    return node.get("display_url") or node.get("thumbnail_src")


def _extract_media(node):
    images, videos = [], []
    items = node.get("carousel_media") or [node]
    for it in items:
        img = _best_image(it)
        if img:
            images.append(img)
        vids = it.get("video_versions") or []
        if vids:
            videos.append(vids[0].get("url"))
    return images, videos


def _caption(node):
    cap = node.get("caption")
    if isinstance(cap, dict):
        return cap.get("text")
    if isinstance(cap, str):
        return cap
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    return edges[0]["node"]["text"] if edges else None


def _parse(node):
    cap = _caption(node)
    code = node.get("code") or node.get("shortcode")
    ts = node.get("taken_at") or node.get("taken_at_timestamp")
    images, videos = _extract_media(node)
    words = (cap or "").split()
    return {
        "shortcode": code,
        "url": f"https://www.instagram.com/p/{code}/" if code else None,
        "timestamp": ts,
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts else None,
        "caption": cap,
        "hashtags": [w[1:] for w in words if w.startswith("#")],
        "mentions": [w[1:] for w in words if w.startswith("@")],
        "image_urls": images,
        "video_urls": videos,
        "like_count": node.get("like_count"),
        "comment_count": node.get("comment_count"),
        "ig_images": [],
        "source": "instagram",
        "status": "new",
    }


def _looks_like_post(node):
    code = node.get("code") or node.get("shortcode")
    return bool(code and ("caption" in node or "edge_media_to_caption" in node))


def _walk(obj, out):
    if isinstance(obj, dict):
        if _looks_like_post(obj):
            out.append(_parse(obj))
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)


def _download(post):
    if not post["image_urls"]:
        return
    dest = config.IG_IMAGES_DIR / post["shortcode"]
    dest.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(post["image_urls"]):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            path = dest / f"{i}.jpg"
            path.write_bytes(r.content)
            post["ig_images"].append(str(path))
        except Exception as e:
            print(f"   ! image download failed ({post['shortcode']} #{i}): {e}")


def run():
    existing = load_posts()
    print(f"[scrape] {len(existing)} posts already stored.")
    captured = {}

    def on_response(response):
        if "graphql" not in response.url and "/api/v1/" not in response.url:
            return
        if "application/json" not in response.headers.get("content-type", ""):
            return
        try:
            data = response.json()
        except Exception:
            return
        found = []
        _walk(data, found)
        for post in found:
            code = post["shortcode"]
            if code and code not in captured:
                captured[code] = post

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(config.SESSION_DIR),
            headless=HEADLESS,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)
        page.goto(f"https://www.instagram.com/{config.IG_TARGET}/",
                  wait_until="domcontentloaded")
        time.sleep(4)

        if "login" in page.url.lower():
            print(">> Not logged in. Log in manually in the window (90s)...")
            time.sleep(90)
            page.goto(f"https://www.instagram.com/{config.IG_TARGET}/",
                      wait_until="domcontentloaded")
            time.sleep(4)

        stalls = 0
        for i in range(MAX_SCROLLS):
            before = len(captured)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(SCROLL_PAUSE)
            page.evaluate("window.scrollBy(0, -600)")
            time.sleep(0.4)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(SCROLL_PAUSE)
            gained = len(captured) - before
            print(f"   scroll {i + 1}/{MAX_SCROLLS} ... {len(captured)} posts (+{gained})")
            if gained == 0:
                stalls += 1
                if stalls >= 3:
                    break
            else:
                stalls = 0
        ctx.close()

    new = {c: post for c, post in captured.items() if c not in existing}
    print(f"[scrape] {len(captured)} seen, {len(new)} new.")

    # top-news filter: keep only posts above the like threshold
    if config.MIN_LIKES > 0:
        before = len(new)
        new = {c: p for c, p in new.items()
               if p.get("like_count") is None or (p.get("like_count") or 0) >= config.MIN_LIKES}
        print(f"[scrape] {before - len(new)} low-engagement posts dropped "
              f"(< {config.MIN_LIKES} likes), {len(new)} remain.")

    # cap to most-recent N posts
    if config.MAX_POSTS > 0 and len(new) > config.MAX_POSTS:
        sorted_new = sorted(new.items(),
                            key=lambda x: x[1].get("timestamp") or 0, reverse=True)
        new = dict(sorted_new[:config.MAX_POSTS])
        print(f"[scrape] capped to {config.MAX_POSTS} most-recent posts.")

    for post in new.values():
        _download(post)
    existing.update(new)
    save_posts(existing)
    print(f"[scrape] saved -> {config.POSTS_FILE}")
    return new


if __name__ == "__main__":
    run()
