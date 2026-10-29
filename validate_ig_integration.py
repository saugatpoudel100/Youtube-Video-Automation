"""Validate and report on Instagram images integration.

Shows statistics about ig_images, stock_images, and posts to verify setup.

Usage: python validate_ig_integration.py
"""
import json
from pathlib import Path
from collections import defaultdict

import config
from store import load_posts

EXTS = (".jpg", ".jpeg", ".png", ".webp")


def count_folder_images(folder):
    """Count image files in a folder."""
    if not folder.exists():
        return 0
    return sum(1 for f in folder.rglob("*") 
              if f.is_file() and f.suffix.lower() in EXTS)


def validate():
    """Run validation checks."""
    posts = load_posts()
    
    print("=" * 70)
    print("INSTAGRAM IMAGES INTEGRATION VALIDATION")
    print("=" * 70)
    
    # Statistics
    ig_count = len([f for f in config.IG_IMAGES_DIR.iterdir() 
                   if f.is_dir()])
    ig_images_count = count_folder_images(config.IG_IMAGES_DIR)
    stock_count = len([f for f in config.STOCK_IMAGES_DIR.iterdir() 
                      if f.is_dir()])
    stock_images_count = count_folder_images(config.STOCK_IMAGES_DIR)
    
    print(f"\n📊 STATISTICS")
    print(f"  Instagram image folders: {ig_count}")
    print(f"  Total Instagram images: {ig_images_count}")
    print(f"  Stock image folders: {stock_count}")
    print(f"  Total stock images: {stock_images_count}")
    
    # Posts breakdown
    posts_by_status = defaultdict(list)
    for code, post in posts.items():
        status = post.get("status", "unknown")
        posts_by_status[status].append(code)
    
    print(f"\n📋 POSTS BY STATUS")
    for status, codes in sorted(posts_by_status.items()):
        print(f"  {status}: {len(codes)}")
    
    # Check for ig_images without matching stock_images
    print(f"\n🔍 POSTS WITH INSTAGRAM IMAGES")
    ig_posts = []
    stock_posts = set()
    
    for code in sorted(posts.keys()):
        ig_folder = config.IG_IMAGES_DIR / code
        stock_folder = config.STOCK_IMAGES_DIR / code
        
        if ig_folder.exists():
            ig_count = len([f for f in ig_folder.iterdir() 
                          if f.is_file() and f.suffix.lower() in EXTS])
            if ig_count > 0:
                stock_count = len([f for f in stock_folder.iterdir() 
                                 if f.is_file() and f.suffix.lower() in EXTS]) if stock_folder.exists() else 0
                status = posts[code].get("status", "?")
                ig_posts.append((code, ig_count, stock_count, status))
    
    if ig_posts:
        print(f"  Found {len(ig_posts)} posts with Instagram images:")
        for code, ig_cnt, stock_cnt, status in ig_posts[:10]:
            sync = "✅" if stock_cnt > 0 else "⏳"
            print(f"    {sync} {code}: {ig_cnt} ig_image(s), {stock_cnt} stock_image(s) - [{status}]")
        if len(ig_posts) > 10:
            print(f"    ... and {len(ig_posts) - 10} more")
    else:
        print(f"  No posts with Instagram images found")
    
    # Check which posts are ready for video
    print(f"\n🎬 POSTS READY FOR VIDEO")
    ready = []
    for code, post in posts.items():
        if post.get("status") == "voiced" and post.get("stock_images"):
            ready.append((code, len(post.get("stock_images", []))))
    
    if ready:
        print(f"  Found {len(ready)} posts ready for video:")
        for code, img_count in sorted(ready)[:10]:
            print(f"    • {code}: {img_count} images")
        if len(ready) > 10:
            print(f"    ... and {len(ready) - 10} more")
    else:
        print(f"  No posts ready for video yet")
    
    # Recommendations
    print(f"\n💡 NEXT STEPS")
    if not ready:
        print(f"  1. Run: python pipeline.py rewrite")
        print(f"  2. Run: python pipeline.py images")
        print(f"  3. Run: python pipeline.py voice")
        print(f"  4. Run: python pipeline.py video")
    else:
        print(f"  Run: python pipeline.py video")
        print(f"  (to create videos using Instagram images)")
    
    print(f"\nAlternatively, run full pipeline:")
    print(f"  python pipeline.py")
    print("=" * 70)


if __name__ == "__main__":
    validate()
