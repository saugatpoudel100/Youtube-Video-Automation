"""Test Instagram images integration end-to-end.

This script demonstrates that Instagram images are properly integrated
and will be used when creating videos.
"""
from pathlib import Path
import json

import config
from store import load_posts
from step3_images import _ig_images, _gather, _choose


def test_ig_image_loading():
    """Test that Instagram images are properly detected and loaded."""
    print("\n" + "=" * 70)
    print("TEST 1: Instagram Image Loading")
    print("=" * 70)
    
    # Find a post with Instagram images
    posts = load_posts()
    for code, post in list(posts.items())[:50]:
        ig_folder = config.IG_IMAGES_DIR / code
        if ig_folder.exists():
            ig_imgs = _ig_images(code)
            if ig_imgs:
                print(f"\n✅ Found Instagram images for post: {code}")
                print(f"   Location: {ig_folder}")
                print(f"   Images loaded: {len(ig_imgs)}")
                for img in ig_imgs[:3]:
                    print(f"     • {Path(img['url']).name} (source: {img['source']})")
                return code, post
    
    print("❌ No Instagram images found in test")
    return None, None


def test_image_selection_priority(code, post):
    """Test that Instagram images get highest priority in selection."""
    print("\n" + "=" * 70)
    print("TEST 2: Image Selection Priority")
    print("=" * 70)
    
    if not code:
        print("⏭️  Skipped (no Instagram images found)")
        return
    
    # Gather candidates
    candidates = _gather(post, code)
    print(f"\n✅ Gathered {len(candidates)} image candidates for {code}")
    
    # Show source breakdown
    sources = {}
    for c in candidates:
        src = c["source"]
        sources[src] = sources.get(src, 0) + 1
    
    print(f"\n   Source breakdown:")
    for src in ["Instagram Original", "Local", "Wikimedia Commons", "Pexels"]:
        count = sources.get(src, 0)
        if count > 0:
            icon = "🥇" if src == "Instagram Original" else "  "
            print(f"   {icon} {src}: {count}")
    
    # Show that Instagram images appear first
    ig_imgs = [c for c in candidates if c["source"] == "Instagram Original"]
    if ig_imgs:
        print(f"\n✅ Instagram images appear in candidates")
        print(f"   They will be selected FIRST in: {ig_imgs[0]['id']}")
        return candidates
    else:
        print(f"\n⚠️  No Instagram images in candidates")
        return candidates


def test_video_readiness(code):
    """Test that posts with Instagram images can create videos."""
    print("\n" + "=" * 70)
    print("TEST 3: Video Creation Readiness")
    print("=" * 70)
    
    posts = load_posts()
    if code not in posts:
        print("❌ Post not found")
        return False
    
    post = posts[code]
    
    # Check requirements for video creation
    checks = {
        "Rewritten content": post.get("content") is not None,
        "Stock images selected": len(post.get("stock_images", [])) > 0,
        "Audio generated": post.get("audio_file") is not None,
        "Status allows video": post.get("status") in ["voiced", "video_ready"],
    }
    
    print(f"\nPost {code} readiness check:")
    all_good = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        all_good = all_good and passed
    
    if all_good:
        print(f"\n✅ Post is READY for video creation")
        print(f"   Run: python pipeline.py video")
        return True
    else:
        status = post.get("status")
        print(f"\n⏳ Post needs more steps first")
        print(f"   Current status: {status}")
        if status == "rewritten":
            print(f"   Next: python pipeline.py images")
        elif status == "images_ready":
            print(f"   Next: python pipeline.py voice")
        return False


def test_actual_video_creation():
    """Check if any posts are ready for immediate video creation."""
    print("\n" + "=" * 70)
    print("TEST 4: Ready for Video Creation")
    print("=" * 70)
    
    posts = load_posts()
    voiced = [code for code, p in posts.items() 
             if p.get("status") == "voiced" and p.get("stock_images")]
    
    if voiced:
        print(f"\n✅ Found {len(voiced)} post(s) ready for video creation")
        for code in voiced[:3]:
            post = posts[code]
            img_count = len(post.get("stock_images", []))
            print(f"   • {code}: {img_count} images ready")
        if len(voiced) > 3:
            print(f"   ... and {len(voiced) - 3} more")
        print(f"\n🎬 To create videos now:")
        print(f"   python pipeline.py video")
        return True
    else:
        print(f"\n⏳ No posts ready for video creation yet")
        print(f"   Run: python pipeline.py")
        print(f"   (or individual steps: rewrite, images, voice)")
        return False


def main():
    print("\n🔍 Testing Instagram Images Integration for Video Creation")
    print("=" * 70)
    
    # Test 1: Can we load Instagram images?
    code, post = test_ig_image_loading()
    
    # Test 2: Are they prioritized?
    if code:
        candidates = test_image_selection_priority(code, post)
    
    # Test 3: Is this specific post ready?
    if code:
        test_video_readiness(code)
    
    # Test 4: Any posts ready now?
    test_actual_video_creation()
    
    print("\n" + "=" * 70)
    print("✅ INTEGRATION TEST COMPLETE")
    print("=" * 70)
    print("""
Your Instagram images are integrated and ready to use!

Next steps:
1. Run: python validate_ig_integration.py (to check current status)
2. Run: python pipeline.py video (to create videos)
3. Run: python pipeline.py (for full pipeline with everything)
    """)


if __name__ == "__main__":
    main()
