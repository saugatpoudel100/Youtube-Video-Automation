"""Consolidate Instagram images into stock_images directory.

This script copies images from ig_images/ to stock_images/ for posts that need
them, making them available as a unified pool for video creation.

Usage: python consolidate_ig_images.py
"""
import shutil
from pathlib import Path

import config
from store import get_by_status, load_posts, update_post

EXTS = (".jpg", ".jpeg", ".png", ".webp")


def consolidate():
    """Copy ig_images to stock_images directory, organized by post code."""
    posts = load_posts()
    consolidated = 0
    
    for code, post in posts.items():
        ig_folder = config.IG_IMAGES_DIR / code
        if not ig_folder.exists():
            continue
        
        # Check if this post already has stock_images
        stock_images = post.get("stock_images", [])
        stock_folder = config.STOCK_IMAGES_DIR / code
        
        # Create stock_images folder if needed
        stock_folder.mkdir(parents=True, exist_ok=True)
        
        # Count existing images in stock folder
        existing = len([f for f in stock_folder.iterdir() 
                       if f.is_file() and f.suffix.lower() in EXTS])
        
        # Copy ig_images to stock_images
        copied = 0
        for f in sorted(ig_folder.iterdir()):
            if f.is_file() and f.suffix.lower() in EXTS:
                dest = stock_folder / f"{existing + copied}.jpg"
                try:
                    shutil.copy2(f, dest)
                    copied += 1
                except Exception as e:
                    print(f"   ! failed to copy {f.name}: {e}")
        
        if copied > 0:
            # Update post with new stock_images list
            all_images = sorted([str(f) for f in stock_folder.iterdir() 
                               if f.is_file() and f.suffix.lower() in EXTS])
            update_post(code, stock_images=all_images)
            print(f"   + {code}: copied {copied} Instagram images")
            consolidated += copied
    
    print(f"\n[consolidate] Total images consolidated: {consolidated}")
    return consolidated


if __name__ == "__main__":
    consolidate()
