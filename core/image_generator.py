import logging
import hashlib
import time
import base64
import re
import httpx
import config

logger = logging.getLogger(__name__)

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter image-capable models — tries in order
IMAGE_MODELS = [
    "google/gemini-2.5-flash-image:free",
    "google/gemini-2.5-flash-image-preview:free",
    "google/gemini-3.1-flash-image-preview:free",
    "google/gemini-2.5-flash-image",
    "google/gemini-2.5-flash-image-preview",
    "google/gemini-3.1-flash-image-preview",
]


def generate_image(title, description=""):
    """Generate image via OpenRouter, upload to Supabase, return public URL."""
    if not title:
        title = "news article"

    url = _openrouter_generate(title)
    if url:
        return url

    # If all OpenRouter models fail, return SVG placeholder
    return _svg_placeholder(title)


def regenerate_image(title):
    """Regenerate with creative variant."""
    if not title:
        title = "news article"

    url = _openrouter_generate(title, variant=True)
    if url:
        return url

    return _svg_placeholder(title)


def _openrouter_generate(title, variant=False):
    """Try each OpenRouter image model in sequence."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        logger.error("No OpenRouter API key configured")
        return ""

    short = _clean(title)
    if variant:
        prompt = f"Generate a creative, dramatic news article cover image about: {short}. Modern digital art, vibrant colors, no text overlay."
    else:
        prompt = f"Generate a professional news article cover image about: {short}. Clean modern design, vibrant colors, no text overlay."

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
                timeout=45,
            )

            if resp.status_code != 200:
                logger.warning(f"{model}: HTTP {resp.status_code} - {resp.text[:200]}")
                continue

            data = resp.json()
            image_bytes = _extract_image(data)
            if not image_bytes:
                logger.warning(f"{model}: no image in response")
                continue

            url = _upload_to_supabase(image_bytes, title)
            if url:
                logger.info(f"✅ Image generated via {model}")
                return url

        except httpx.TimeoutException:
            logger.warning(f"{model}: timeout")
            continue
        except Exception as e:
            logger.warning(f"{model} error: {e}")
            continue

    logger.error("All OpenRouter image models failed")
    return ""


def _extract_image(data):
    """Extract image bytes from various possible OpenRouter response formats."""
    try:
        choices = data.get("choices", [])
        if not choices:
            return None

        message = choices[0].get("message", {})

        # Format 1: images array at top level of message
        images = message.get("images")
        if isinstance(images, list) and images:
            for img in images:
                if isinstance(img, dict):
                    url = img.get("image_url", {}).get("url") if isinstance(img.get("image_url"), dict) else img.get("image_url")
                    if isinstance(url, str):
                        bytes_data = _decode_data_url(url)
                        if bytes_data:
                            return bytes_data

        # Format 2: content is a list of parts (multimodal)
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type", "")

                # image_url type
                if ptype == "image_url":
                    img_url = part.get("image_url")
                    url = img_url.get("url") if isinstance(img_url, dict) else img_url
                    if isinstance(url, str):
                        bytes_data = _decode_data_url(url)
                        if bytes_data:
                            return bytes_data

                # image type with data field
                if ptype == "image" and part.get("data"):
                    try:
                        return base64.b64decode(part["data"])
                    except Exception:
                        pass

                # inline_data style
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict) and inline.get("data"):
                    try:
                        return base64.b64decode(inline["data"])
                    except Exception:
                        pass

        # Format 3: content is a string with embedded data URL
        if isinstance(content, str) and "data:image" in content:
            match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", content)
            if match:
                try:
                    return base64.b64decode(match.group(1))
                except Exception:
                    pass

        return None
    except Exception as e:
        logger.error(f"Image extraction failed: {e}")
        return None


def _decode_data_url(url):
    """Decode a data:image/...;base64,... URL to bytes."""
    try:
        if url.startswith("data:image"):
            match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", url)
            if match:
                return base64.b64decode(match.group(1))
        # If it's a regular HTTP URL, fetch it
        elif url.startswith("http"):
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                return resp.content
    except Exception as e:
        logger.warning(f"Decode data URL failed: {e}")
    return None


def _upload_to_supabase(image_bytes, title):
    """Upload image bytes to Supabase Storage, return public URL."""
    try:
        import db
        filename = f"img_{hashlib.md5(title.encode()).hexdigest()[:12]}_{int(time.time())}.png"

        client = db.get_client()
        client.storage.from_("images").upload(
            filename,
            image_bytes,
            {"content-type": "image/png", "upsert": "true"},
        )

        public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        logger.info(f"Uploaded to Supabase: {filename} ({len(image_bytes)} bytes)")
        return public_url
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        return ""


def _clean(title):
    if not title:
        return "news"
    cleaned = title[:80]
    for ch in ['"', "'", "<", ">", "\n", "\r", "\t", "\\"]:
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split())[:80].strip() or "news"


def _svg_placeholder(title):
    """SVG data URL placeholder - shown when image generation fails. Always works."""
    short = _clean(title)[:40]
    # Pick color based on hash for visual variety
    h = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    hue = h % 360
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="hsl({hue},50%,30%)"/>
<stop offset="1" stop-color="hsl({(hue+60)%360},50%,20%)"/>
</linearGradient></defs>
<rect width="800" height="450" fill="url(#g)"/>
<text x="400" y="220" font-family="sans-serif" font-size="32" fill="white" text-anchor="middle" font-weight="700">{_xml_escape(short)}</text>
<text x="400" y="270" font-family="sans-serif" font-size="14" fill="rgba(255,255,255,0.6)" text-anchor="middle">Image generation unavailable</text>
</svg>'''
    encoded = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
