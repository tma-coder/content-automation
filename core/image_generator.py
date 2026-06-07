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

# Models in priority order — only ones that actually exist
IMAGE_MODELS = [
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-image-preview",
]

FONT_URLS = [
    # jsDelivr CDN — most reliable, no redirects
    "https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.16/files/inter-latin-800-normal.woff2",
    "https://cdn.jsdelivr.net/gh/rsms/inter@master/docs/font-files/Inter-Bold.ttf",
    "https://cdn.jsdelivr.net/gh/rsms/inter@v4.0/docs/font-files/Inter-Bold.ttf",
    # GitHub raw
    "https://raw.githubusercontent.com/rsms/inter/master/docs/font-files/Inter-Bold.ttf",
    # Google Fonts mirror via jsDelivr (different paths)
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-Black.ttf",
    "https://cdn.jsdelivr.net/gh/google/fonts@main/apache/roboto/static/Roboto-Black.ttf",
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/bebasneue/BebasNeue-Regular.ttf",
]

_FONT_BYTES = None
_FONT_OBJ_CACHE = {}
_LAST_DEBUG = {}


def get_debug():
    """Return debug info from last generation."""
    return _LAST_DEBUG.copy()


def generate_image(title, description="", subject="", highlight_phrases=None):
    """Generate news card."""
    global _LAST_DEBUG
    _LAST_DEBUG = {"steps": []}

    if not title:
        title = "News Article"

    _LAST_DEBUG["title"] = title
    _LAST_DEBUG["subject"] = subject
    _LAST_DEBUG["highlights"] = highlight_phrases

    # 1. Background
    bg_bytes = _generate_background(title, subject)
    _LAST_DEBUG["bg_size"] = len(bg_bytes) if bg_bytes else 0
    _LAST_DEBUG["steps"].append(f"bg: {'OK' if bg_bytes else 'FAILED'}")

    if not bg_bytes:
        bg_bytes = _gradient_background(title)
        _LAST_DEBUG["steps"].append("bg: using gradient fallback")

    # 2. Compose
    try:
        final_bytes = _compose_news_card(bg_bytes, title, highlight_phrases or [])
        _LAST_DEBUG["steps"].append(f"compose: OK ({len(final_bytes)} bytes)")
    except Exception as e:
        logger.error(f"Composition failed: {e}", exc_info=True)
        _LAST_DEBUG["steps"].append(f"compose: FAILED - {e}")
        _LAST_DEBUG["compose_error"] = str(e)
        final_bytes = bg_bytes

    # 3. Upload
    url = _upload_to_supabase(final_bytes, title)
    _LAST_DEBUG["steps"].append(f"upload: {'OK' if url else 'FAILED'}")

    if url:
        return url
    return _svg_placeholder(title)


def regenerate_image(title, subject="", highlight_phrases=None):
    return generate_image(title, subject=subject, highlight_phrases=highlight_phrases)


def _generate_background(title, subject=""):
    """Try OpenRouter first, fall back to Pollinations if available."""
    visual_subject = subject.strip() if subject else _smart_subject(title)
    _LAST_DEBUG["visual_subject"] = visual_subject

    # Try OpenRouter
    bg = _try_openrouter(visual_subject)
    if bg:
        return bg

    # Fall back to Pollinations server-side
    if config.POLLINATIONS_API_KEY:
        bg = _try_pollinations(visual_subject)
        if bg:
            return bg

    return None


def _try_openrouter(visual_subject):
    """Try OpenRouter image models. Time-budget aware (max ~30s total)."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        _LAST_DEBUG["openrouter_error"] = "no API key"
        return None

    prompt = (
        f"Generate a high-quality photographic news cover image showing: {visual_subject}. "
        f"Style: Professional photography, cinematic lighting, sharp focus, vibrant colors. "
        f"Portrait orientation. The subject should be prominent in the upper-center. "
        f"DO NOT add any text, captions, watermarks, or logos."
    )

    model_errors = []
    start_time = time.time()

    for model in IMAGE_MODELS:
        # Time budget: leave 25s for Pollinations fallback + composition
        if time.time() - start_time > 30:
            model_errors.append(f"time budget exceeded after {model}")
            break

        try:
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
                    "max_tokens": 100,
                },
                timeout=25,
            )
            if resp.status_code != 200:
                err_text = resp.text[:120] if resp.text else f"HTTP {resp.status_code}"
                model_errors.append(f"{model}: {resp.status_code} - {err_text}")
                continue

            image_bytes = _extract_image(resp.json())
            if image_bytes:
                _LAST_DEBUG["bg_model"] = model
                _LAST_DEBUG["bg_source"] = "OpenRouter"
                return image_bytes
            else:
                model_errors.append(f"{model}: no image in response")
        except httpx.TimeoutException:
            model_errors.append(f"{model}: timeout")
        except Exception as e:
            model_errors.append(f"{model}: {str(e)[:80]}")

    _LAST_DEBUG["openrouter_errors"] = model_errors
    return None


def _try_pollinations(visual_subject):
    """Server-side fetch from Pollinations - tries multiple auth methods."""
    import urllib.parse
    prompt = f"{visual_subject}, professional photography, photorealistic, cinematic"
    encoded = urllib.parse.quote(prompt, safe='')
    seed = int(hashlib.md5(visual_subject.encode()).hexdigest()[:8], 16) % 1000000
    base_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1280&seed={seed}&model=flux&nologo=true"

    # Try different auth methods
    attempts = [
        {"desc": "Bearer header", "url": base_url, "headers": {"Authorization": f"Bearer {config.POLLINATIONS_API_KEY}"}},
        {"desc": "x-api-key", "url": base_url, "headers": {"x-api-key": config.POLLINATIONS_API_KEY}},
        {"desc": "token query", "url": f"{base_url}&token={config.POLLINATIONS_API_KEY}", "headers": {}},
        {"desc": "key query", "url": f"{base_url}&key={config.POLLINATIONS_API_KEY}", "headers": {}},
    ]

    results = []
    for attempt in attempts:
        try:
            headers = {"User-Agent": "Mozilla/5.0 ContentAutomation", **attempt["headers"]}
            resp = httpx.get(attempt["url"], headers=headers, timeout=20, follow_redirects=True)
            ct = resp.headers.get("content-type", "")
            results.append(f"{attempt['desc']}: HTTP {resp.status_code}, type={ct}, bytes={len(resp.content)}")

            if resp.status_code == 200 and ct.startswith("image/") and resp.content:
                _LAST_DEBUG["bg_source"] = f"Pollinations ({attempt['desc']})"
                _LAST_DEBUG["pollinations_status"] = " | ".join(results)
                return resp.content
        except Exception as e:
            results.append(f"{attempt['desc']}: error {str(e)[:60]}")

    _LAST_DEBUG["pollinations_status"] = " | ".join(results)
    return None


def _smart_subject(title):
    """Extract a visual subject from a title."""
    # Clean and shorten
    clean = _clean(title)[:120]

    # If title contains a colon, take the part before it (usually the topic)
    if ":" in clean:
        before_colon = clean.split(":")[0].strip()
        after_colon = clean.split(":", 1)[1].strip()
        # If there's a name after colon (capitalized words), include it
        if after_colon and after_colon[0].isupper():
            return f"{before_colon}, featuring {after_colon}"
        return before_colon

    # Remove common stop phrases
    for phrase in ["is here", "is now", "are here", "has arrived", "is launching"]:
        clean = clean.replace(phrase, "")

    return clean.strip()


def _extract_image(data):
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
        logger.error(f"Extract: {e}")
        return None


def _decode_url(url):
    try:
        if url.startswith("data:image"):
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", url)
            if m:
                return base64.b64decode(m.group(1))
        elif url.startswith("http"):
            r = httpx.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200:
                return r.content
    except Exception:
        pass
    return None


# ============================================
# PIL COMPOSITION
# ============================================

def _ensure_font_bytes():
    global _FONT_BYTES
    if _FONT_BYTES is not None:
        return _FONT_BYTES

    for url in FONT_URLS:
        try:
            logger.info(f"Downloading font: {url}")
            r = httpx.get(url, timeout=15, follow_redirects=True)
            logger.info(f"Font response: HTTP {r.status_code}, size={len(r.content)}")
            if r.status_code == 200 and len(r.content) > 50000:
                _FONT_BYTES = r.content
                _LAST_DEBUG["font_url"] = url
                _LAST_DEBUG["font_size_bytes"] = len(r.content)
                return _FONT_BYTES
        except Exception as e:
            logger.warning(f"Font {url}: {e}")

    _LAST_DEBUG["font_error"] = "all font URLs failed"
    return None


def _get_font(size):
    from PIL import ImageFont

    cache_key = size
    if cache_key in _FONT_OBJ_CACHE:
        return _FONT_OBJ_CACHE[cache_key]

    font_bytes = _ensure_font_bytes()
    if font_bytes:
        try:
            font = ImageFont.truetype(BytesIO(font_bytes), size=size)
            _FONT_OBJ_CACHE[cache_key] = font
            _LAST_DEBUG["font_used"] = "Inter-Bold (truetype)"
            return font
        except Exception as e:
            logger.error(f"truetype load: {e}")
            _LAST_DEBUG["font_error"] = f"truetype: {e}"

    # Fallback: Pillow 10+ load_default with size
    try:
        font = ImageFont.load_default(size=size)
        _FONT_OBJ_CACHE[cache_key] = font
        _LAST_DEBUG["font_used"] = f"default (size={size})"
        return font
    except TypeError:
        # Older Pillow - load_default doesn't accept size
        font = ImageFont.load_default()
        _LAST_DEBUG["font_used"] = "default (tiny bitmap)"
        return font


def _compose_news_card(bg_bytes, title, highlight_phrases):
    """Compose news card with title overlay. CRITICAL: use RGB tuples only."""
    from PIL import Image, ImageDraw

    W, H = 1080, 1350

    # Load and prepare background
    bg = Image.open(BytesIO(bg_bytes)).convert("RGB")
    _LAST_DEBUG["bg_dimensions"] = bg.size
    bg = _cover_resize(bg, W, H)

    # Apply dark gradient overlay - work in RGBA, then convert back
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    gradient_start = int(H * 0.35)
    for y in range(gradient_start, H):
        ratio = (y - gradient_start) / (H - gradient_start)
        alpha = int(min(255, 220 * (ratio ** 0.9) + 40))
        odraw.line([(0, y), (W, y)], fill=(8, 10, 22, alpha))

    bg_rgba = bg.convert("RGBA")
    composed = Image.alpha_composite(bg_rgba, overlay)
    final = composed.convert("RGB")  # Now we're in RGB mode

    # Draw title using RGB tuples ONLY
    draw = ImageDraw.Draw(final)
    _draw_title(draw, title, highlight_phrases, W, H)

    out = BytesIO()
    final.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def _cover_resize(img, w, h):
    from PIL import Image
    iw, ih = img.size
    target_ratio = w / h
    img_ratio = iw / ih

    if img_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 4
        img = img.crop((0, top, iw, top + new_h))

    return img.resize((w, h), Image.LANCZOS)


def _draw_title(draw, title, highlights, W, H):
    """Draw title at bottom with highlighted phrases. Uses RGB tuples only."""
    # Dynamic font sizing
    n = len(title)
    if n > 100:
        font_size, line_height = 52, 66
    elif n > 70:
        font_size, line_height = 62, 78
    elif n > 40:
        font_size, line_height = 72, 90
    else:
        font_size, line_height = 84, 104

    font = _get_font(font_size)

    padding_x = 60
    max_width = W - 2 * padding_x

    lines = _wrap_text(draw, title, font, max_width)
    if not lines:
        _LAST_DEBUG["draw_error"] = "no lines after wrap"
        return

    lines = lines[:7]
    _LAST_DEBUG["lines"] = len(lines)
    _LAST_DEBUG["font_size"] = font_size

    bottom_padding = 120
    total_height = len(lines) * line_height
    start_y = H - bottom_padding - total_height

    min_start = int(H * 0.42)
    if start_y < min_start:
        start_y = min_start

    _LAST_DEBUG["start_y"] = start_y
    _LAST_DEBUG["total_text_height"] = total_height

    highlight_colors = [
        (251, 191, 36),   # yellow
        (163, 230, 53),   # green
        (251, 191, 36),
    ]

    highlights_norm = [h.lower().strip() for h in highlights if h and h.strip()]
    used = set()

    for i, line in enumerate(lines):
        y = start_y + i * line_height
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        x_start = (W - line_w) // 2

        # Find highlight match
        matched = None
        match_idx = -1
        match_pos = -1
        for idx, hp in enumerate(highlights_norm):
            if idx in used:
                continue
            pos = line.lower().find(hp)
            if pos != -1:
                matched = hp
                match_idx = idx
                match_pos = pos
                break

        if matched is not None:
            used.add(match_idx)
            color = highlight_colors[match_idx % len(highlight_colors)]
            _draw_with_highlight(draw, line, match_pos, len(matched),
                                 x_start, y, font, color, line_height)
        else:
            _draw_text_shadow(draw, x_start, y, line, font)


def _draw_text_shadow(draw, x, y, text, font):
    """Draw white text with dark shadow. RGB only."""
    # Shadow offset (RGB only, no alpha)
    draw.text((x + 3, y + 3), text, fill=(0, 0, 0), font=font)
    # Main text
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def _draw_with_highlight(draw, line, match_pos, match_len, x_start, y, font, color, line_height):
    """Draw line with highlighted portion."""
    before = line[:match_pos]
    highlighted = line[match_pos:match_pos + match_len]
    after = line[match_pos + match_len:]

    cur_x = x_start

    if before:
        bbox = draw.textbbox((0, 0), before, font=font)
        w_b = bbox[2] - bbox[0]
        _draw_text_shadow(draw, cur_x, y, before, font)
        cur_x += w_b

    if highlighted:
        bbox = draw.textbbox((0, 0), highlighted, font=font)
        w_h = bbox[2] - bbox[0]
        h_h = bbox[3] - bbox[1]

        pad_x = 14
        pad_y_top = 6
        pad_y_bot = 14

        rect = [
            cur_x - pad_x,
            y + pad_y_top,
            cur_x + w_h + pad_x,
            y + h_h + pad_y_bot,
        ]
        # Highlight box (RGB)
        draw.rectangle(rect, fill=color)
        # Dark text on highlight (RGB)
        draw.text((cur_x, y), highlighted, fill=(20, 20, 30), font=font)
        cur_x += w_h

    if after:
        _draw_text_shadow(draw, cur_x, y, after, font)


def _wrap_text(draw, text, font, max_width):
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
            r, g, b = hls_to_rgb((hue + ratio * 0.15) % 1, 0.4 - ratio * 0.25, 0.6)
            draw.line([(0, y), (W, y)], fill=(int(r * 255), int(g * 255), int(b * 255)))

        out = BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        logger.error(f"Gradient: {e}")
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
        return f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
    except Exception as e:
        logger.error(f"Upload: {e}")
        _LAST_DEBUG["upload_error"] = str(e)
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
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350"><rect width="1080" height="1350" fill="hsl({hue},50%,25%)"/><text x="540" y="675" font-family="sans-serif" font-size="48" fill="white" text-anchor="middle" font-weight="700">{_xml_escape(short)}</text></svg>'
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
