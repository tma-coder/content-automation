import logging
import urllib.parse
import hashlib
import time
import httpx
import config

logger = logging.getLogger(__name__)

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


def generate_image(title, description=""):
    """Generate image. Tries Pollinations (server-side with auth) → upload to Supabase → fallback to Picsum."""
    if not title:
        title = "news"

    # Try Pollinations server-side with Bearer auth
    if config.POLLINATIONS_API_KEY:
        url = _pollinations_authenticated(title)
        if url:
            return url

    # Fallback: try without auth (might work if not rate-limited)
    url = _pollinations_no_auth(title)
    if url:
        return url

    # Guaranteed fallback
    logger.info("Using Picsum fallback")
    return _picsum_fallback(title)


def regenerate_image(title):
    """Regenerate with different seed."""
    if not title:
        title = "news"

    seed = int(time.time())

    if config.POLLINATIONS_API_KEY:
        url = _pollinations_authenticated(title, seed=seed, variant=True)
        if url:
            return url

    url = _pollinations_no_auth(title, seed=seed, variant=True)
    if url:
        return url

    return _picsum_fallback(f"{title}-{seed}")


def _build_prompt(title, variant=False):
    short = _clean(title)
    if variant:
        return f"{short}, creative news illustration, dramatic lighting, digital art"
    return f"{short}, professional news article cover photo, modern design, vibrant colors, no text"


def _pollinations_authenticated(title, seed=None, variant=False):
    """Server-side fetch from Pollinations with Bearer auth, upload to Supabase."""
    try:
        prompt = _build_prompt(title, variant)
        encoded = urllib.parse.quote(prompt, safe='')

        if seed is None:
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % 1000000

        url = f"{POLLINATIONS_BASE}/{encoded}?width=800&height=450&seed={seed}&model=flux&nologo=true"

        logger.info(f"Fetching from Pollinations: {url[:120]}")

        resp = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {config.POLLINATIONS_API_KEY}",
                "User-Agent": "Mozilla/5.0 ContentAutomation/1.0",
            },
            timeout=25,
            follow_redirects=True,
        )

        content_type = resp.headers.get("content-type", "")
        logger.info(f"Pollinations response: HTTP {resp.status_code}, type={content_type}, bytes={len(resp.content) if resp.content else 0}")

        if resp.status_code == 200 and content_type.startswith("image/") and resp.content:
            return _upload_to_supabase(resp.content, title, content_type)

        if resp.status_code == 402:
            logger.warning("Pollinations: rate limit hit (402)")
        else:
            logger.warning(f"Pollinations: unexpected response {resp.status_code}")

        return ""

    except httpx.TimeoutException:
        logger.warning("Pollinations: timeout")
        return ""
    except Exception as e:
        logger.error(f"Pollinations auth fetch failed: {e}")
        return ""


def _pollinations_no_auth(title, seed=None, variant=False):
    """Build URL without auth - browser will fetch directly. May hit rate limit."""
    try:
        prompt = _build_prompt(title, variant)
        encoded = urllib.parse.quote(prompt, safe='')

        if seed is None:
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % 1000000

        return f"{POLLINATIONS_BASE}/{encoded}?width=800&height=450&seed={seed}&model=flux&nologo=true"
    except Exception as e:
        logger.error(f"Pollinations no-auth URL build failed: {e}")
        return ""


def _upload_to_supabase(image_bytes, title, content_type="image/png"):
    """Upload image bytes to Supabase Storage, return public URL."""
    try:
        import db
        ext = "png" if "png" in content_type else "jpg"
        filename = f"img_{hashlib.md5(title.encode()).hexdigest()[:12]}_{int(time.time())}.{ext}"

        client = db.get_client()
        client.storage.from_("images").upload(
            filename,
            image_bytes,
            {"content-type": content_type, "upsert": "true"},
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
    for ch in ['"', "'", "&", "<", ">", "\n", "\r", "\t", "\\"]:
        cleaned = cleaned.replace(ch, " ")
    cleaned = " ".join(cleaned.split())
    return cleaned[:80].strip() or "news"


def _picsum_fallback(title):
    """Lorem Picsum - guaranteed instant fallback."""
    seed = abs(hash(title)) % 1000
    return f"https://picsum.photos/seed/{seed}/800/450"
