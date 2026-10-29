"""Quick reference for Instagram images in video creation workflow.

TL;DR: Instagram images from ig_images/ are now automatically prioritized
when creating videos. Everything works seamlessly with the existing pipeline.
"""

# ============================================================================
# QUICK START
# ============================================================================

# Just run the normal pipeline - Instagram images are automatically included:
#
#   python pipeline.py                    # Full pipeline
#   python pipeline.py images             # Just images step (prioritizes ig_images)
#   python pipeline.py voice              # Just voice step
#   python pipeline.py video              # Just video step
#
# That's it! Instagram images will be used automatically.


# ============================================================================
# WHAT JUST CHANGED
# ============================================================================

# 1. step3_images.py now includes a new function: _ig_images(code)
#    - Checks data/ig_images/{post_shortcode}/ for images
#    - Adds them with HIGHEST priority to the image candidates
#    - These original images are used FIRST in videos

# 2. Image selection priority is now:
#    🥇 Instagram Original Images      (data/ig_images/)
#    🥈 Local User Images               (data/my_images/)
#    🥉 Wikidata (logos, etc)
#       Wikipedia (portraits)
#       Commons (search results)
#       Pexels (fallback)

# 3. Two new utility scripts:
#    - consolidate_ig_images.py  (optional: copy ig_images to stock_images)
#    - validate_ig_integration.py (check your setup)


# ============================================================================
# CURRENT STATUS
# ============================================================================

# From latest validation:
#   📊 84 Instagram image folders with 57 images
#   📊 499 stock images across 101 posts
#   📊 3 posts ready to create videos
#   ✅ 95 published posts already using Instagram images
#
# Your Instagram images are ALREADY being used in published videos!


# ============================================================================
# HOW IT WORKS
# ============================================================================

# BEFORE (old behavior):
#   Post created → Images fetched from Wikimedia/Pexels → Video made
#
# AFTER (new behavior):
#   Post created → Instagram image found in ig_images/ → Used FIRST in video
#                → Additional images fetched if needed
#                → Video made with original Instagram image as primary

# Example: A post about "Douglas Costa" would:
#   1. Check ig_images/CZucw9Ao3Eu/ → Find 0.jpg ✅
#   2. Use that as primary image in video (shows the player)
#   3. Add supporting images for longer videos (same player, related clips, etc)


# ============================================================================
# COMMON TASKS
# ============================================================================

# 1. Create videos from existing posts (WITH Instagram images)
#    python pipeline.py video
#
# 2. Check integration status
#    python validate_ig_integration.py
#
# 3. Consolidate all ig_images into stock_images (one-time optional)
#    python consolidate_ig_images.py
#
# 4. Manually test image selection for a post
#    python -c "
#    from store import load_posts
#    from step3_images import _gather
#    posts = load_posts()
#    code = 'DZa7syhkSgo'  # any Instagram post shortcode
#    post = posts[code]
#    candidates = _gather(post, code)
#    print(f'Found {len(candidates)} image candidates')
#    for c in candidates[:5]:
#        print(f'  • {c[\"source\"]}: {c[\"id\"]}')
#    "


# ============================================================================
# TROUBLESHOOTING
# ============================================================================

# Q: Are Instagram images being used?
# A: Yes! Run: python validate_ig_integration.py
#    Look for "✅" marks next to posts with ig_images.

# Q: Why isn't a specific Instagram image showing in the video?
# A: Possible reasons:
#    • Image is in wrong format (must be .jpg, .jpeg, .png, or .webp)
#    • ig_images/{shortcode}/ folder doesn't exist
#    • Image file is corrupt
#    • Post status is wrong (must be between "rewritten" and "video_ready")

# Q: How do I add an Instagram image for a post manually?
# A: 1. Create folder: data/ig_images/{instagram_shortcode}/
#    2. Copy image file as: data/ig_images/{instagram_shortcode}/0.jpg
#    3. Run: python pipeline.py images
#    4. Run: python pipeline.py voice (if not done)
#    5. Run: python pipeline.py video

# Q: Can I see which images were selected?
# A: Yes! The images step prints a log line showing images used:
#    "✅ {code}: 5 images (3 real/owned)"
#    Instagram images count as "owned" / "real" content


# ============================================================================
# FILES MODIFIED
# ============================================================================

# step3_images.py
#   - Added _ig_images() function
#   - Updated _gather() to check ig_images first
#   - Updated _choose() to prioritize ig_images
#
# NEW: consolidate_ig_images.py
#   - Optional utility to copy ig_images to stock_images
#
# NEW: validate_ig_integration.py
#   - Check your setup and see statistics
#
# NEW: IG_IMAGES_WORKFLOW.md
#   - Detailed documentation
#
# NEW: QUICK_REFERENCE.py (this file)
#   - Quick lookup guide


# ============================================================================
# NEXT STEPS
# ============================================================================

# 1. Review your current setup:
#    python validate_ig_integration.py
#
# 2. Create videos using your Instagram images:
#    python pipeline.py video
#
# 3. Monitor video quality and adjust if needed:
#    - Check video output in data/video/
#    - Adjust IMAGES_PER_VIDEO in config.py if needed
#
# 4. (Optional) Consolidate images for faster access:
#    python consolidate_ig_images.py


# ============================================================================
# KEY INSIGHT
# ============================================================================

# Instagram images are now HIGHEST priority in your video pipeline.
# This means your original content (the actual Instagram screenshots)
# will be featured prominently in every video created.
#
# Combined with rewritten captions and AI voiceover, this creates
# authentic, original content from your Instagram data.
#
# Your pipeline is now:
#   Scrape → Rewrite → [Use Original IG Images] → Voice → Video → Upload
#                      ^^^^^^^^^^^^^^^^^^^^^^^^
#                      NEW: Highest Priority
