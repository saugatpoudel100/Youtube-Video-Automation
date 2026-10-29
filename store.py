"""Tiny JSON-backed store for posts (no database).

Each post is a dict keyed by its Instagram shortcode. A `status` field tracks
where it is in the pipeline:
    new -> rewritten -> images_ready -> voiced -> video_ready -> published
"""
import json

import config


def load_posts() -> dict:
    if config.POSTS_FILE.exists():
        return json.loads(config.POSTS_FILE.read_text(encoding="utf-8"))
    return {}


def save_posts(posts: dict) -> None:
    config.POSTS_FILE.write_text(
        json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_by_status(status: str) -> dict:
    return {c: p for c, p in load_posts().items() if p.get("status") == status}


def update_post(shortcode: str, **fields) -> None:
    posts = load_posts()
    if shortcode in posts:
        posts[shortcode].update(fields)
        save_posts(posts)
