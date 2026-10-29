# Instagram Images to Video Workflow

## Overview
This document explains how Instagram images (`ig_images/`) are now integrated into the video creation pipeline.

## What Changed

### 1. **Image Selection Priority** (step3_images.py)
Images are now selected in this priority order:
1. **Instagram Original Images** (data/ig_images/{code}/) - HIGHEST PRIORITY ⭐
2. **Local User Images** (data/my_images/)
3. Wikidata Images (logos, crests)
4. Wikipedia Images (portraits)
5. Wikimedia Commons Images (search results)
6. Pexels Images (fallback)

### 2. **Instagram Images Folder Structure**
```
data/ig_images/
├── CZucw9Ao3Eu/          (Instagram post code)
│   └── 0.jpg             (Image from that post)
├── DGV39vsIxjX/
│   └── 0.jpg
├── ... (84+ image folders)
```

Each folder name matches a post's Instagram shortcode and contains the original image(s) from that post.

### 3. **Automatic Integration**
When running `step3_images.run()` (or `python pipeline.py images`):
- It now checks `ig_images/{post_code}/` for images
- If found, these images are automatically selected FIRST
- They're copied to `stock_images/{post_code}/` for video generation
- The post's `stock_images` field is updated with their paths

## Usage

### Option A: Use Existing Pipeline (Recommended)
Simply run the normal pipeline - Instagram images are automatically prioritized:
```bash
python pipeline.py                # full run - ig_images automatically included
python pipeline.py images         # just run images step
```

### Option B: Consolidate All Images (Optional)
If you want to pre-process and consolidate all ig_images into stock_images:
```bash
python consolidate_ig_images.py
```
This copies all Instagram images from `ig_images/` to `stock_images/`, making them permanent.

## Video Creation
When videos are created via `step5_video.run()`:
1. It reads `post["stock_images"]` which now includes your Instagram images
2. Ken Burns zoom effect is applied to each image
3. Images are timed to voiceover duration
4. Animated captions are overlaid (if whisper-faster is installed)

## Example Workflow

```
1. Posts scraped with ig_images/CZucw9Ao3Eu/ existing
   ↓
2. Run: python pipeline.py rewrite
   ↓
3. Run: python pipeline.py images
   → Detects ig_images/CZucw9Ao3Eu/0.jpg
   → Adds it to candidates with HIGHEST priority
   → Copies to stock_images/CZucw9Ao3Eu/0.jpg
   → Updates post: "stock_images": ["data/stock_images/CZucw9Ao3Eu/0.jpg", ...]
   ↓
4. Run: python pipeline.py voice
   ↓
5. Run: python pipeline.py video
   → Uses all images in post["stock_images"] including Instagram original
   → Creates 1080x1920 vertical video with Ken Burns effects
   ↓
6. Run: python pipeline.py upload
```

## Benefits
✅ **Original Content**: Your scraped Instagram images are used in videos
✅ **Authenticity**: Posts feature the original images they were about
✅ **Fallback Coverage**: Still uses other sources if needed
✅ **No Code Changes**: Works seamlessly with existing pipeline
✅ **Reversible**: Instagram images are just treated as "local" priority sources

## Troubleshooting

**Q: Videos not using Instagram images?**
- Check that `ig_images/{code}/` folder exists
- Check that images are `.jpg`, `.jpeg`, `.png`, or `.webp` format
- Check that `posts.json` has the post with status between "rewritten" and "voiced"

**Q: Want to see which images were selected?**
- The images step prints: `+ {code}: {len(images)} images (X real/owned)`
- Instagram images count as "owned" since they're original content

**Q: How to manually add Instagram images for a post?**
1. Create folder: `data/ig_images/{instagram_shortcode}/`
2. Place image as `0.jpg` in that folder
3. Run `python pipeline.py images` to regenerate

## Files Modified
- `step3_images.py` - Added `_ig_images()` function, updated priority order
- `consolidate_ig_images.py` - New utility script for optional consolidation
