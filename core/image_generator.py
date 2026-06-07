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

# Font URLs - try in order (raw.githubusercontent.com directly to avoid redirects)
FONT_URLS = [
    "https://raw.githubusercontent.com/rsms/inter/master/docs/font-files/Inter-Bold.ttf",
    "https://cdn.jsdelivr.net/gh/google/fonts/ofl/inter/static/Inter_28pt-Bold.ttf",
    "https://cdn.jsdelivr.net/npm/@fontsource/inter@5/files/inter-latin-700-normal.woff",
]

# Cache (per cold-start container)
_FONT_BYTES = None
_FONT_OBJ_CACHE = {}


def generate_image(title, description="", subject="", highlight_phrases=None):
    """Generate news card: AI background + composited text overlay."""
    if not title:
        title = "News Article"

    # 1. Generate background image (subject focus, no text)
    bg_bytes = _generate_background(title, subject)

    if not bg_bytes:
        logger.warning("Using gradient background fallback")
        bg_bytes = _gradient_background(title)

    # 2. Composite text overlay with PIL
    try:
        final_bytes = _compose_news_card(bg_bytes, title, highlight_phrases or [])
    except Exception as e:
        logger.error(f"Composition failed: {e}", exc_info=True)
        final_bytes = bg_bytes

    # 3. Upload to Supabase
    url = _upload_to_supabase(final_bytes, title)
    if url:
        return url

    return _svg_placeholder(title)


def regenerate_image(title, subject="", highlight_phrases=None):
    return generate_image(title, subject=subject, highlight_phrases=highlight_phrases)


def _generate_background(title, subject=""):
    """Generate background image via OpenRouter."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        return None

    visual_subject = subject or _clean(title)[:80]

    prompt = (
        f"Generate a high-quality photographic news cover image. "
        f"Subject: {visual_subject}. "
        f"Style: Professional news photography, cinematic lighting, sharp focus, vibrant colors, photorealistic. "
        f"Composition: Subject prominently in the UPPER HALF of the frame, with empty/dark space at the bottom for text overlay. "
        f"Aspect ratio: portrait (taller than wide). "
        f"CRITICAL: NO text, NO captions, NO logos, NO watermarks in the image. Just a clean photograph."
    )

    for model in IMAGE_MODELS:
        try:
            logger.info(f"Trying: {model}")
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
                logger.warning(f"{model}: HTTP {resp.status_code}")
                continue
            image_bytes = _extract_image(resp.json())
            if image_bytes:
                logger.info(f"✅ Background from {model} ({len(image_bytes)} bytes)")
                return image_bytes
        except Exception as e:
            logger.warning(f"{model} error: {e}")
    return None


def _extract_image(data):
    """Extract image bytes from OpenRouter response."""
    try:
        choices = data.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})

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

        if isinstance(content, str) and "data:image" in content:
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", content)
            if m:
                return base64.b64decode(m.group(1))
        return None
    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return None


def _decode_url(url):
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

def _ensure_font_bytes():
    """Download Inter-Bold font once per container. CRITICAL: follow_redirects=True."""
    global _FONT_BYTES
    if _FONT_BYTES is not None:
        return _FONT_BYTES

    for url in FONT_URLS:
        try:
            logger.info(f"Downloading font from: {url}")
            r = httpx.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 50000:
                _FONT_BYTES = r.content
                logger.info(f"✅ Font cached: {len(_FONT_BYTES)} bytes")
                return _FONT_BYTES
            else:
                logger.warning(f"Font URL {url}: HTTP {r.status_code}, size={len(r.content)}")
        except Exception as e:
            logger.warning(f"Font URL {url} failed: {e}")

    logger.error("ALL font URLs failed - text will be tiny!")
    return None


def _get_font(size):
    """Get PIL font of given size, cached."""
    from PIL import ImageFont

    if size in _FONT_OBJ_CACHE:
        return _FONT_OBJ_CACHE[size]

    font_bytes = _ensure_font_bytes()
    if font_bytes:
        try:
            font = ImageFont.truetype(BytesIO(font_bytes), size=size)
            _FONT_OBJ_CACHE[size] = font
            return font
        except Exception as e:
            logger.error(f"Font truetype load failed: {e}")

    # Last resort
    return ImageFont.load_default()


def _compose_news_card(bg_bytes, title, highlight_phrases):
    """Compose final news card with title overlay."""
    from PIL import Image, ImageDraw

    W, H = 1080, 1350

    # Load and resize background
    bg = Image.open(BytesIO(bg_bytes)).convert("RGB")
    bg = _cover_resize(bg, W, H)

    # Add dark gradient overlay (much stronger)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # Gradient from transparent (top) to nearly opaque dark (bottom)
    gradient_start = int(H * 0.35)
    for y in range(gradient_start, H):
        ratio = (y - gradient_start) / (H - gradient_start)
        # Quicker ramp to near-black
        alpha = int(min(255, 220 * (ratio ** 0.9) + 40))
        odraw.line([(0, y), (W, y)], fill=(8, 10, 20, alpha))

    bg_rgba = bg.convert("RGBA")
    composed = Image.alpha_composite(bg_rgba, overlay)
    final = composed.convert("RGB")
    draw = ImageDraw.Draw(final)

    # Draw title with highlighted phrases
    _draw_title(draw, title, highlight_phrases, W, H)

    out = BytesIO()
    final.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def _cover_resize(img, w, h):
    """Resize to cover dimensions, cropping excess."""
    iw, ih = img.size
    target_ratio = w / h
    img_ratio = iw / ih

    if img_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 4  # bias toward upper portion
        img = img.crop((0, top, iw, top + new_h))

    return img.resize((w, h), Image.LANCZOS)


def _draw_title(draw, title, highlights, W, H):
    """Draw title at bottom with highlighted phrases."""
    # Dynamic font sizing based on title length
    if len(title) > 90:
        font_size = 56
        line_height = 70
    elif len(title) > 60:
        font_size = 64
        line_height = 80
    else:
        font_size = 72
        line_height = 90

    font = _get_font(font_size)
    if not font:
        return

    padding_x = 50
    max_width = W - 2 * padding_x

    # Wrap title into lines
    lines = _wrap_text(draw, title, font, max_width)
    if not lines:
        return
    lines = lines[:7]  # max 7 lines

    # Calculate total height and position from bottom
    bottom_padding = 130
    total_height = len(lines) * line_height
    start_y = H - bottom_padding - total_height

    # Make sure we don't go above the gradient
    min_start = int(H * 0.42)
    if start_y < min_start:
        start_y = min_start

    # Highlight colors (cycle): yellow, green, yellow
    highlight_colors = [
        (251, 191, 36),   # warm yellow
        (163, 230, 53),   # bright green
        (251, 191, 36),
        (163, 230, 53),
    ]

    highlights_norm = [h.lower().strip() for h in highlights if h and h.strip()]
    used_highlights = set()

    for i, line in enumerate(lines):
        y = start_y + i * line_height

        # Measure line
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        x_start = (W - line_w) // 2  # center

        # Check if any unused highlight matches in this line
        matched_highlight = None
        matched_idx = -1
        match_pos = -1

        for idx, hp in enumerate(highlights_norm):
            if idx in used_highlights:
                continue
            pos = line.lower().find(hp)
            if pos != -1:
                matched_highlight = hp
                matched_idx = idx
                match_pos = pos
                break

        if matched_highlight:
            used_highlights.add(matched_idx)
            color = highlight_colors[matched_idx % len(highlight_colors)]
            _draw_with_highlight(draw, line, match_pos, len(matched_highlight),
                                 x_start, y, font, color, line_height)
        else:
            # Plain white text with shadow
            _draw_text_with_shadow(draw, x_start, y, line, font, (255, 255, 255))


def _draw_text_with_shadow(draw, x, y, text, font, color):
    """Draw text with subtle shadow for depth."""
    # Shadow
    draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 180), font=font)
    # Main
    draw.text((x, y), text, fill=color, font=font)


def _draw_with_highlight(draw, line, match_pos, match_len, x_start, y, font, color, line_height):
    """Draw a line where part is highlighted."""
    before = line[:match_pos]
    highlighted = line[match_pos:match_pos + match_len]
    after = line[match_pos + match_len:]

    cur_x = x_start

    # Before (white)
    if before:
        bbox_b = draw.textbbox((0, 0), before, font=font)
        w_b = bbox_b[2] - bbox_b[0]
        _draw_text_with_shadow(draw, cur_x, y, before, font, (255, 255, 255))
        cur_x += w_b

    # Highlight box + text
    if highlighted:
        bbox_h = draw.textbbox((0, 0), highlighted, font=font)
        w_h = bbox_h[2] - bbox_h[0]
        h_h = bbox_h[3] - bbox_h[1]

        # Padding around highlighted text
        pad_x = 16
        pad_y = 8

        rect = [
            cur_x - pad_x,
            y + 4,
            cur_x + w_h + pad_x,
            y + h_h + pad_y + 8,
        ]
        draw.rectangle(rect, fill=color)
        # Text in dark color on highlight
        draw.text((cur_x, y), highlighted, fill=(20, 20, 30), font=font)
        cur_x += w_h

    # After (white)
    if after:
        _draw_text_with_shadow(draw, cur_x, y, after, font, (255, 255, 255))


def _wrap_text(draw, text, font, max_width):
    """Wrap text into lines that fit max_width."""
    words = text.split()
    if not words:
        return []

    lines = []
    current = words[0]
    for word in words[1:]:
        test = current + " " + word
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _gradient_background(title):
    """Colored gradient as fallback when AI image gen fails."""
    try:
        from PIL import Image, ImageDraw
        from colorsys import hls_to_rgb

        W, H = 1080, 1350
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        h = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
        hue = (h % 360) / 360

        for y in range(H):
            ratio = y / H
            r, g, b = hls_to_rgb(hue + ratio * 0.15, 0.4 - ratio * 0.25, 0.6)
            draw.line([(0, y), (W, y)], fill=(int(r * 255), int(g * 255), int(b * 255)))

        out = BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        logger.error(f"Gradient fallback: {e}")
        return None


def _upload_to_supabase(image_bytes, title):
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
        logger.info(f"Uploaded: {filename}")
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
    short = _clean(title)[:60]
    h = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    hue = h % 360
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350">
<rect width="1080" height="1350" fill="hsl({hue},50%,25%)"/>
<text x="540" y="675" font-family="sans-serif" font-size="48" fill="white" text-anchor="middle" font-weight="700">{_xml_escape(short)}</text>
</svg>'''
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
