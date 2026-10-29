"""STEP 3 — Fetch relevant images for the video.

Priority order:
  0. YOUR OWN images  -> data/my_images/<shortcode>/  (or loose in data/my_images/)
  1. Wikidata entity  -> official LOGO (P154), main IMAGE (P18), and the entity's
     Commons CATEGORY (P373). This is what makes clubs/stadiums/crests resolve to
     real photos (e.g. "Camp Nou" -> stadium photos, "FC Barcelona" -> the crest).
  2. Wikipedia lead image -> the real portrait of a person.
  3. Commons free-text search -> more real photos.
  4. Pexels -> generic football B-roll fallback only.

Variety: chosen IDs stored in data/used_images.json and shuffled. Commons/Wikidata
attribution is collected for the description.

Reads 'rewritten' posts -> status 'images_ready'.
"""
import json
import random
import re
import shutil
import time
from urllib.parse import quote, unquote

import requests

import config
from store import get_by_status, update_post

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
PEXELS_URL = "https://api.pexels.com/v1/search"
UA = {"User-Agent": config.WIKI_USER_AGENT}   # all Wikimedia APIs need a real UA
USED_FILE = config.DATA_DIR / "used_images.json"
THUMB_W = 1280
WIKI_PAUSE = 0.7
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _load_used():
    if USED_FILE.exists():
        return set(json.loads(USED_FILE.read_text(encoding="utf-8")))
    return set()


def _save_used(used):
    USED_FILE.write_text(json.dumps(sorted(used)), encoding="utf-8")


def _wm_get(url, **kw):
    time.sleep(WIKI_PAUSE)
    return requests.get(url, headers=UA, timeout=30, **kw)


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _ig_images(code):
    """Load images from Instagram scrape (highest priority)."""
    out = []
    ig_folder = config.IG_IMAGES_DIR / code
    if ig_folder.exists():
        for f in sorted(ig_folder.iterdir()):
            if f.is_file() and f.suffix.lower() in EXTS:
                out.append({"id": f"ig:{code}:{f.name}", "url": str(f), "artist": "",
                            "license": "", "source": "Instagram Original"})
    return out


def _romano_recent_images(n=6):
    """Return the N most-recent downloaded Romano Instagram images as a pool.

    Used for RSS posts that have no dedicated Instagram image. Romano's photos
    are football-relevant and give the video a real, recognisable look.
    """
    out = []
    ig_root = config.IG_IMAGES_DIR
    if not ig_root.exists():
        return out
    folders = sorted(
        (f for f in ig_root.iterdir() if f.is_dir()),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    for folder in folders:
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in EXTS:
                out.append({"id": f"ig_pool:{f}", "url": str(f), "artist": "",
                            "license": "", "source": "Instagram Original"})
        if len(out) >= n:
            break
    return out[:n]


def _article_image(url):
    """Fetch the Open Graph / Twitter Card image from a news article URL.

    Returns a candidate dict or None. Used for RSS posts so they always have
    at least the article's editorial photo.
    """
    if not url:
        return None
    try:
        r = requests.get(url, headers=UA, timeout=12, allow_redirects=True)
        r.raise_for_status()
        html = r.text[:60_000]          # only scan the <head>
        # handle either attribute order: property/name first or content first
        pat = (
            r'<meta[^>]+(?:property|name)\s*=\s*["\'](?:og|twitter):image["\'][^>]+'
            r'content\s*=\s*["\']([^"\']+)["\']'
            r'|'
            r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+'
            r'(?:property|name)\s*=\s*["\'](?:og|twitter):image["\']'
        )
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            img_url = (m.group(1) or m.group(2) or "").strip()
            ext = img_url.lower().split("?")[0].split("#")[0]
            if img_url.startswith("http") and ext.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return {"id": f"article:{url}", "url": img_url, "artist": "",
                        "license": "", "source": "Article"}
    except Exception:
        pass
    return None


def _local_user_images(code):
    out = []
    for folder in (config.MY_IMAGES_DIR / code, config.MY_IMAGES_DIR):
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in EXTS:
                out.append({"id": f"local:{f}", "url": str(f), "artist": "",
                            "license": "", "source": "Local"})
    return out


def _candidate(title, ii):
    # thumburl is a rasterized PNG even for SVG logos, so crests work here too
    url = ii.get("thumburl") or ii.get("url")
    if not url or not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png")):
        return None
    # drop tiny images (icons, low-res thumbnails, small logos)
    w, h = ii.get("width") or 0, ii.get("height") or 0
    if w and h and min(w, h) < config.MIN_IMAGE_DIM:
        return None
    meta = ii.get("extmetadata") or {}
    return {"id": title, "url": url,
            "artist": _strip_html((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons",
            "license": (meta.get("LicenseShortName") or {}).get("value", "CC"),
            "source": "Wikimedia Commons"}


def _commons_fileinfo(file_title):
    params = {"action": "query", "format": "json", "titles": file_title,
              "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": THUMB_W}
    r = _wm_get(COMMONS_API, params=params)
    r.raise_for_status()
    for p in ((r.json().get("query") or {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [None])[0]
        if ii:
            return _candidate(p.get("title", file_title), ii)
    return None


# ---------- Wikidata (clubs / stadiums / crests / people) ----------
def _wikidata_qid(subject):
    params = {"action": "wbsearchentities", "search": subject, "language": "en",
              "format": "json", "type": "item", "limit": 1}
    try:
        r = _wm_get(WIKIDATA_API, params=params)
        r.raise_for_status()
        hits = r.json().get("search") or []
        return hits[0]["id"] if hits else None
    except Exception:
        return None


def _wikidata_media(qid):
    """Return (commons filenames from P154 logo + P18 image, commons category)."""
    params = {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}
    files, category = [], None
    try:
        r = _wm_get(WIKIDATA_API, params=params)
        r.raise_for_status()
        claims = (((r.json().get("entities") or {}).get(qid) or {}).get("claims") or {})
    except Exception:
        return files, category
    for prop in ("P154", "P18"):                 # logo first, then main image
        for c in claims.get(prop, []):
            try:
                fn = c["mainsnak"]["datavalue"]["value"]
                if isinstance(fn, str):
                    files.append(fn)
            except Exception:
                pass
    for c in claims.get("P373", []):              # Commons category
        try:
            category = c["mainsnak"]["datavalue"]["value"]
            break
        except Exception:
            pass
    return files, category


def _commons_category(cat, limit=12):
    params = {"action": "query", "format": "json", "generator": "categorymembers",
              "gcmtitle": f"Category:{cat}", "gcmtype": "file", "gcmlimit": limit,
              "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": THUMB_W}
    r = _wm_get(COMMONS_API, params=params)
    r.raise_for_status()
    out = []
    for p in ((r.json().get("query") or {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [None])[0]
        if ii:
            c = _candidate(p.get("title"), ii)
            if c:
                out.append(c)
    return out


def _wikipedia_lead(subject):
    try:
        r = _wm_get(WIKI_SUMMARY + quote(subject.replace(" ", "_")))
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    img = (data.get("originalimage") or {}).get("source") or (data.get("thumbnail") or {}).get("source")
    if not img or "/wikipedia/commons/" not in img:
        return None
    parts = img.split("/")
    fname = unquote(parts[-2] if "/thumb/" in img else parts[-1])
    try:
        return _commons_fileinfo("File:" + fname)
    except Exception:
        return None


def _commons_search(term, limit=25):
    params = {"action": "query", "format": "json", "generator": "search",
              "gsrnamespace": 6, "gsrsearch": term, "gsrlimit": limit,
              "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": THUMB_W}
    r = _wm_get(COMMONS_API, params=params)
    r.raise_for_status()
    out = []
    for p in ((r.json().get("query") or {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [None])[0]
        if ii:
            c = _candidate(p.get("title"), ii)
            if c:
                out.append(c)
    return out


def _pexels_search(query, n):
    if not config.PEXELS_API_KEY:
        return []
    try:
        r = requests.get(PEXELS_URL, headers={"Authorization": config.PEXELS_API_KEY},
                         params={"query": query, "per_page": n, "orientation": "portrait",
                                 "size": "large"}, timeout=30)
        r.raise_for_status()
        photos = r.json().get("photos", [])
    except Exception as e:
        print(f"   ! pexels failed: {e}")
        return []
    return [{"id": f"pexels:{p['id']}", "url": p["src"]["portrait"],
             "artist": p.get("photographer", "Pexels"), "license": "Pexels License",
             "source": "Pexels"} for p in photos]


def _gather(post, code):
    content = post.get("content", {})
    subjects = [s for s in (content.get("subjects") or []) if s.strip()]
    fallback_q = content.get("image_query") or "football soccer match"
    candidates, seen = [], set()
    target = config.IMAGES_PER_VIDEO * 3

    def add(c):
        if c and c["id"] not in seen:
            seen.add(c["id"])
            candidates.append(c)

    for c in _ig_images(code):                          # 0) Instagram images (HIGHEST PRIORITY)
        add(c)
    for c in _local_user_images(code):                  # 1) your images
        add(c)

    if post.get("source") == "rss":                     # 1b) RSS: article og:image + Romano pool
        add(_article_image(post.get("url", "")))
        for c in _romano_recent_images():
            add(c)

    for term in subjects[:3]:                           # 2) Wikidata: logo/image/category
        if len(candidates) >= target:
            break
        qid = _wikidata_qid(term)
        if qid:
            files, category = _wikidata_media(qid)
            for fn in files[:3]:
                try:
                    add(_commons_fileinfo("File:" + fn))
                except Exception:
                    pass
            if category and len(candidates) < target:
                try:
                    for c in _commons_category(category):
                        add(c)
                except Exception as e:
                    print(f"   ! category '{category}' failed: {e}")
        add(_wikipedia_lead(term))                      # 3) real portrait (people)

    for term in subjects[:3]:                           # 4) more via text search
        if len(candidates) >= target:
            break
        try:
            for c in _commons_search(term):
                add(c)
        except Exception as e:
            print(f"   ! commons '{term}' failed: {e}")

    if len(subjects) >= 2 and len(candidates) < target: # 4b) combined search (e.g. "Mbappe Real Madrid")
        combo = " ".join(subjects[:2])
        try:
            for c in _commons_search(combo, limit=15):
                add(c)
        except Exception as e:
            print(f"   ! commons combined '{combo}' failed: {e}")

    if len(candidates) < config.IMAGES_PER_VIDEO * 2:   # generic football
        try:
            for c in _commons_search(fallback_q):
                add(c)
        except Exception:
            pass
    if len(candidates) < config.IMAGES_PER_VIDEO:       # 5) Pexels fallback
        for c in _pexels_search(fallback_q, config.IMAGES_PER_VIDEO):
            add(c)
    return candidates


def _choose(candidates, used, n):
    """Instagram/your images lead; choose most-relevant results; shuffle the rest."""
    if not candidates:
        return []
    ig = [c for c in candidates if c["source"] == "Instagram Original"]
    locals_ = [c for c in candidates if c["source"] == "Local"]
    rest = [c for c in candidates if c["source"] not in ("Instagram Original", "Local")]
    priority = rest[:2]                                  # most-relevant come first
    pool = [c for c in rest[2:] if c["id"] not in used]
    random.shuffle(pool)
    chosen = (ig + locals_ + priority + pool)[:n]
    if len(chosen) < n:
        leftovers = [c for c in candidates if c not in chosen]
        random.shuffle(leftovers)
        chosen += leftovers[: n - len(chosen)]
    return chosen


def run():
    todo = get_by_status("rewritten")
    print(f"[images] {len(todo)} posts need images.")
    used = _load_used()
    for code, post in todo.items():
        candidates = _gather(post, code)
        if not candidates:
            print(f"   ! no images found for {code}")
            continue
        chosen = _choose(candidates, used, config.IMAGES_PER_VIDEO)
        dest = config.STOCK_IMAGES_DIR / code
        dest.mkdir(parents=True, exist_ok=True)
        local, credits = [], []
        for i, c in enumerate(chosen):
            path = dest / f"{i}.jpg"
            try:
                if c["source"] in ("Local", "Instagram Original"):
                    shutil.copyfile(c["url"], path)
                elif "wikimedia.org" in c["url"]:
                    r = _wm_get(c["url"]); r.raise_for_status(); path.write_bytes(r.content)
                else:
                    r = requests.get(c["url"], headers=UA, timeout=30); r.raise_for_status(); path.write_bytes(r.content)
                local.append(str(path))
                used.add(c["id"])
                if c["source"] == "Wikimedia Commons":
                    credits.append(f'{c["artist"]} ({c["license"]}, {c["source"]})')
            except Exception as e:
                print(f"   ! image failed ({code} #{i}): {e}")
        if not local:
            print(f"   ! nothing usable for {code}")
            continue
        real = sum(1 for c in chosen if c["source"] in ("Local", "Wikimedia Commons"))
        update_post(code, stock_images=local, image_credits=credits, status="images_ready")
        print(f"   + {code}: {len(local)} images ({real} real/owned)")
    _save_used(used)
    return get_by_status("images_ready")


if __name__ == "__main__":
    run()