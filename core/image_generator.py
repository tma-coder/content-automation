import logging
import hashlib
import time
import base64
import re
import httpx
from io import BytesIO
import config

logger = logging.getLogger(__name__)

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"

IMAGE_MODELS = [
    "google/gemini-2.5-flash-image:free",
    "google/gemini-2.5-flash-image-preview:free",
    "google/gemini-3.1-flash-image-preview:free",
    "google/gemini-2.5-flash-image",
    "google/gemini-2.5-flash-image-preview",
    "google/gemini-3.1-flash-image-preview",
]

# Font cache (per cold-start)
_FONT_BYTES = None
INTER_BOLD_URL = "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Bold.ttf"


def generate_image(title, description="", subject="", highlight_phrases=None):
    """Generate news card: AI background + composited text overlay."""
    if not title:
        title = "News Article"

    # 1. Generate background image (subject focus, no text)
    bg_bytes = _generate_background(title, subject)

    if not bg_bytes:
        logger.warning("Background generation failed, using gradient")
        bg_bytes = _gradient_background(title)

    # 2. Composite text overlay with PIL
    try:
        final_bytes = _compose_news_card(bg_bytes, title, highlight_phrases or [])
    except Exception as e:
        logger.error(f"Composition failed: {e}", exc_info=True)
        final_bytes = bg_bytes  # Fall back to plain background

    # 3. Upload to Supabase
    url = _upload_to_supabase(final_bytes, title)
    if url:
        return url

    # Fallback: SVG placeholder
    return _svg_placeholder(title)


def regenerate_image(title, subject="", highlight_phrases=None):
    """Regenerate with creative variant."""
    return generate_image(title, subject=subject, highlight_phrases=highlight_phrases)


def _generate_background(title, subject=""):
    """Generate background image via OpenRouter. Returns image bytes."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        logger.error("No OpenRouter API key")
        return None

    visual_subject = subject or _clean(title)[:80]

    prompt = (
        f"Generate a high-quality photographic image suitable for a news article cover. "
        f"Subject: {visual_subject}. "
        f"Style: Professional news photography, dramatic lighting, vibrant colors, sharp focus. "
        f"Composition: Subject prominently in the upper-center area of the frame. "
        f"Important: NO text overlay, NO captions, NO watermarks, NO logos. "
        f"Just a clean photograph of the subject. Portrait orientation."
    )

    for model in IMAGE_MODELS:
        try:
            logger.info(f"Trying image model: {model}")
            resp = httpx.post(
                OPENROUTER_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://content-automation-chi.vercel.app",
                    "X-Title": "Content Automation",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": ["image", "text"],
                    "max_tokens": 2000,
                },
                timeout=40,
            )
            if resp.status_code != 200:
                logger.warning(f"{model}: HTTP {resp.status_code} - {resp.text[:150]}")
                continue

            image_bytes = _extract_image(resp.json())
            if image_bytes:
                logger.info(f"✅ Background from {model}")
                return image_bytes
            logger.warning(f"{model}: no image extracted")
        except httpx.TimeoutException:
            logger.warning(f"{model}: timeout")
        except Exception as e:
            logger.warning(f"{model} error: {e}")

    return None


def _extract_image(data):
    """Extract image bytes from OpenRouter response (multiple format support)."""
    try:
        choices = data.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})

        # Format 1: top-level images array
        images = message.get("images")
        if isinstance(images, list):
            for img in images:
                if isinstance(img, dict):
                    img_url = img.get("image_url")
                    url = img_url.get("url") if isinstance(img_url, dict) else img_url
                    if isinstance(url, str):
                        b = _decode_url(url)
                        if b:
                            return b

        # Format 2: content list with parts
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type", "")
                if ptype == "image_url":
                    img_url = part.get("image_url")
                    url = img_url.get("url") if isinstance(img_url, dict) else img_url
                    if isinstance(url, str):
                        b = _decode_url(url)
                        if b:
                            return b
                if ptype == "image" and part.get("data"):
                    try:
                        return base64.b64decode(part["data"])
                    except Exception:
                        pass
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict) and inline.get("data"):
                    try:
                        return base64.b64decode(inline["data"])
                    except Exception:
                        pass

        # Format 3: data URL embedded in string content
        if isinstance(content, str) and "data:image" in content:
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", content)
            if m:
                return base64.b64decode(m.group(1))
        return None
    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return None


def _decode_url(url):
    """Decode data URL or fetch HTTP URL to bytes."""
    try:
        if url.startswith("data:image"):
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", url)
            if m:
                return base64.b64decode(m.group(1))
        elif url.startswith("http"):
            r = httpx.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return r.content
    except Exception:
        pass
    return None


# ============================================
# PIL COMPOSITION
# ============================================

def _load_font(size, bold=True):
    """Load Inter Bold font (downloaded once per container)."""
    global _FONT_BYTES
    try:
        from PIL import ImageFont
    except ImportError:
        logger.error("Pillow not installed")
        return None

    if _FONT_BYTES is None:
        try:
            logger.info("Downloading Inter Bold font...")
            r = httpx.get(INTER_BOLD_URL, timeout=10)
            if r.status_code == 200:
                _FONT_BYTES = r.content
                logger.info(f"Font cached ({len(_FONT_BYTES)} bytes)")
        except Exception as e:
            logger.error(f"Font download failed: {e}")
            return ImageFont.load_default()

    try:
        return ImageFont.truetype(BytesIO(_FONT_BYTES), size=size)
    except Exception as e:
        logger.warning(f"Font load failed: {e}")
        return ImageFont.load_default()


def _compose_news_card(bg_bytes, title, highlight_phrases):
    """Compose final news card image with title overlay."""
    from PIL import Image, ImageDraw

    # Output dimensions: 4:5 portrait (Instagram-friendly)
    W, H = 1080, 1350

    # Load and prepare background
    bg = Image.open(BytesIO(bg_bytes)).convert("RGB")
    bg = _cover_resize(bg, W, H)

    # Add dark gradient at bottom 50%
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    gradient_start = int(H * 0.45)
    for y in range(gradient_start, H):
        ratio = (y - gradient_start) / (H - gradient_start)
        alpha = int(245 * (ratio ** 1.2))
        odraw.line([(0, y), (W, y)], fill=(10, 12, 22, alpha))
    bg_rgba = bg.convert("RGBA")
    bg_rgba = Image.alpha_composite(bg_rgba, overlay)

    final = bg_rgba.convert("RGB")
    draw = ImageDraw.Draw(final)

    # Draw title with highlighted phrases
    _draw_title_with_highlights(draw, title, highlight_phrases, W, H)

    # Save as JPEG (smaller, faster)
    out = BytesIO()
    final.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue()


def _cover_resize(img, w, h):
    """Resize image to cover target dimensions (crop excess)."""
    iw, ih = img.size
    target_ratio = w / h
    img_ratio = iw / ih

    if img_ratio > target_ratio:
        # Image wider: crop sides
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        # Image taller: crop top/bottom
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))

    return img.resize((w, h))


def _draw_title_with_highlights(draw, title, highlights, W, H):
    """Draw title text at bottom with highlighted phrases."""
    font = _load_font(54)
    if not font:
        return

    # Layout
    padding_x = 50
    max_width = W - 2 * padding_x
    line_height = 70

    # Wrap title into lines
    lines = _wrap_text(title, font, max_width)
    if not lines:
        return

    # Limit to 6 lines
    lines = lines[:6]

    # Calculate starting Y to bottom-align with some padding
    bottom_padding = 130
    total_height = len(lines) * line_height
    start_y = H - bottom_padding - total_height

    # Normalize highlights (lowercase for matching)
    highlights_lower = [h.lower().strip() for h in highlights if h and len(h.strip()) > 1]

    # Colors for highlights (cycle through)
    highlight_colors = [(251, 191, 36), (163, 230, 53), (251, 191, 36)]  # yellow, green, yellow

    for i, line in enumerate(lines):
        y = start_y + i * line_height

        # Measure line width
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        x = (W - line_w) // 2  # Center each line

        # Check if any highlight phrase appears in this line
        drawn = False
        for hi, hphrase in enumerate(highlights_lower):
            if hphrase and hphrase in line.lower():
                _draw_line_with_highlight(draw, line, hphrase, x, y, font, highlight_colors[hi % len(highlight_colors)])
                drawn = True
                break

        if not drawn:
            # Plain white text
            draw.text((x, y), line, fill=(255, 255, 255), font=font)


def _draw_line_with_highlight(draw, line, phrase, x, y, font, highlight_color):
    """Draw a single line of text with a highlighted phrase."""
    line_lower = line.lower()
    idx = line_lower.find(phrase.lower())
    if idx == -1:
        draw.text((x, y), line, fill=(255, 255, 255), font=font)
        return

    # Three parts: before, highlighted, after
    before = line[:idx]
    highlighted = line[idx:idx + len(phrase)]
    after = line[idx + len(phrase):]

    # Measure each part
    bbox_before = draw.textbbox((0, 0), before, font=font) if before else (0, 0, 0, 0)
    bbox_high = draw.textbbox((0, 0), highlighted, font=font)
    w_before = bbox_before[2] - bbox_before[0]
    w_high = bbox_high[2] - bbox_high[0]

    cur_x = x

    # Draw "before"
    if before:
        draw.text((cur_x, y), before, fill=(255, 255, 255), font=font)
        cur_x += w_before

    # Draw highlight rectangle then text on top
    pad = 8
    rect = [cur_x - 4, y + 2, cur_x + w_high + 4, y + bbox_high[3] + pad]
    draw.rectangle(rect, fill=highlight_color)
    draw.text((cur_x, y), highlighted, fill=(20, 20, 20), font=font)
    cur_x += w_high

    # Draw "after"
    if after:
        draw.text((cur_x, y), after, fill=(255, 255, 255), font=font)


def _wrap_text(text, font, max_width):
    """Wrap text into lines that fit within max_width."""
    from PIL import ImageDraw, Image
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    if not words:
        return []

    lines = []
    current = words[0]
    for word in words[1:]:
        test = current + " " + word
        bbox = tmp.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _gradient_background(title):
    """Generate a colored gradient background as fallback."""
    try:
        from PIL import Image, ImageDraw
        W, H = 1080, 1350
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        h = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
        hue = h % 360

        for y in range(H):
            ratio = y / H
            # HSL-ish gradient
            from colorsys import hls_to_rgb
            r, g, b = hls_to_rgb((hue + ratio * 60) / 360 % 1, 0.35 - ratio * 0.2, 0.55)
            draw.line([(0, y), (W, y)], fill=(int(r*255), int(g*255), int(b*255)))

        out = BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        logger.error(f"Gradient fallback failed: {e}")
        return None


def _upload_to_supabase(image_bytes, title):
    """Upload to Supabase Storage."""
    if not image_bytes:
        return ""
    try:
        import db
        filename = f"card_{hashlib.md5(title.encode()).hexdigest()[:12]}_{int(time.time())}.jpg"

        client = db.get_client()
        client.storage.from_("images").upload(
            filename,
            image_bytes,
            {"content-type": "image/jpeg", "upsert": "true"},
        )

        public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        logger.info(f"Uploaded: {filename} ({len(image_bytes)} bytes)")
        return public_url
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        return ""


def _clean(title):
    if not title:
        return "news"
    cleaned = title[:120]
    for ch in ['"', "'", "<", ">", "\n", "\r", "\t", "\\"]:
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split()).strip() or "news"


def _svg_placeholder(title):
    """SVG placeholder when all generation fails."""
    short = _clean(title)[:60]
    h = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    hue = h % 360
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="hsl({hue},50%,30%)"/>
<stop offset="1" stop-color="hsl({(hue+60)%360},50%,15%)"/>
</linearGradient></defs>
<rect width="1080" height="1350" fill="url(#g)"/>
<text x="540" y="675" font-family="sans-serif" font-size="48" fill="white" text-anchor="middle" font-weight="700">{_xml_escape(short)}</text>
</svg>'''
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
