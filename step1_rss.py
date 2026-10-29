"""STEP 1 (RSS) — Fast top football news from RSS feeds.

Covers transfers, goals, World Cup, tournament wins, big player news, and more.
Replaces the slow Playwright/Instagram scraper: finishes in seconds, no browser.

Default sources (override via RSS_FEEDS=url1,url2,... in .env):
  - Google News  (transfers, goals, World Cup — three ranked searches)
  - Sky Sports   (Transfers feed + Football news)
  - BBC Sport    (Football news)
  - ESPN Soccer  (match results & big player news)
  - Goal.com     (all football news)

pip install feedparser
"""
import hashlib
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser

import config
from store import load_posts, save_posts

# keywords that mark an article as relevant football news
FOOTBALL_KEYWORDS = {
    # transfers & signings
    "transfer", "sign", "signing", "signs", "signed", "deal", "contract",
    "loan", "move", "join", "joins", "joined", "fee", "bid", "offer",
    "agree", "agreement", "medical", "done deal", "here we go", "seals", "swap",
    # match results & goals
    "goal", "goals", "scored", "hat-trick", "hat trick", "winner", "wins",
    "victory", "defeat", "final", "semi-final", "quarterfinal", "penalty",
    "champions", "champion", "trophy", "title", "cup", "league",
    # World Cup / tournaments
    "world cup", "fifa", "euro", "copa america", "afcon", "nations league",
    "champions league", "europa league", "premier league", "la liga",
    "bundesliga", "serie a", "ligue 1",
    # big player news
    "record", "milestone", "debut", "captain", "hat trick", "brace",
    "red card", "banned", "suspension", "injury", "return",
}

DEFAULT_FEEDS = [
    # Google News — separate searches for transfers, goals/results, and World Cup
    "https://news.google.com/rss/search?q=football+transfer+news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=football+goal+win+result&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=world+cup+football&hl=en-US&gl=US&ceid=US:en",
    # Sky Sports — transfers + general football
    "https://www.skysports.com/rss/12040",
    # BBC Sport football
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    # ESPN Soccer
    "https://www.espn.com/espn/rss/soccer/news",
    # Goal.com
    "https://www.goal.com/feeds/en/news",
]

MAX_AGE_HOURS = int(os.getenv("RSS_MAX_AGE_HOURS", "48"))   # skip news older than this
MAX_PER_FEED = int(os.getenv("RSS_MAX_PER_FEED", "10"))     # top N stories per feed


# ------------------------------------------------------------------ helpers --

def _feeds():
    custom = os.getenv("RSS_FEEDS", "")
    if custom.strip():
        return [f.strip() for f in custom.split(",") if f.strip()]
    return DEFAULT_FEEDS


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _is_football_news(title, summary):
    text = (title + " " + (summary or "")).lower()
    return any(kw in text for kw in FOOTBALL_KEYWORDS)


def _parse_date(entry):
    for field in ("published", "updated"):
        val = entry.get(field)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return None


def _is_recent(entry):
    dt = _parse_date(entry)
    if dt is None:
        return True   # unknown date → include to be safe
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    return dt >= cutoff


def _make_post(entry, feed_url):
    title   = _strip_html(entry.get("title", "")).strip()
    summary = _strip_html(entry.get("summary", "")).strip()
    # combine title + summary as the caption the LLM will rewrite
    caption = f"{title}\n\n{summary}" if summary and summary != title else title
    link    = entry.get("link", feed_url)
    dt      = _parse_date(entry)
    ts      = int(dt.timestamp()) if dt else None
    code    = f"rss_{hashlib.md5(link.encode()).hexdigest()[:16]}"
    words   = caption.split()
    return {
        "shortcode":     code,
        "url":           link,
        "timestamp":     ts,
        "datetime":      dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
        "caption":       caption,
        "hashtags":      [w[1:] for w in words if w.startswith("#")],
        "mentions":      [w[1:] for w in words if w.startswith("@")],
        "image_urls":    [],
        "video_urls":    [],
        "like_count":    None,
        "comment_count": None,
        "ig_images":     [],
        "source":        "rss",
        "status":        "new",
    }


# -------------------------------------------------------------------- main --

def run():
    existing = load_posts()
    print(f"[rss] {len(existing)} posts already stored.")
    feeds = _feeds()
    added = 0

    for feed_url in feeds:
        label = feed_url[:70]
        print(f"   fetching: {label}...")
        try:
            d = feedparser.parse(feed_url, agent="FootballShortsBot/1.0")
        except Exception as e:
            print(f"   ! feed error ({label}): {e}")
            continue
        if d.bozo and not d.entries:
            print(f"   ! bad feed ({label}): {d.bozo_exception}")
            continue

        count = 0
        for entry in d.entries:
            if count >= MAX_PER_FEED:
                break
            title   = entry.get("title", "")
            summary = entry.get("summary", "")
            if not _is_football_news(title, summary):
                continue
            if not _is_recent(entry):
                continue
            post = _make_post(entry, feed_url)
            if post["shortcode"] in existing:
                continue
            existing[post["shortcode"]] = post
            print(f"   + {post['shortcode']}: {title[:70]}")
            added += 1
            count += 1

    save_posts(existing)
    print(f"[rss] {added} new posts saved -> {config.POSTS_FILE}")
    return {c: p for c, p in existing.items()
            if p.get("source") == "rss" and p.get("status") == "new"}


if __name__ == "__main__":
    run()
