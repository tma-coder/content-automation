import logging
import urllib.parse
import hashlib
import time
import httpx

logger = logging.getLogger(__name__)


def generate_image(title, description=""):
    """Try multiple image providers until one works."""
    providers = [
        _pollinations_v1,
        _pollinations_v2,
        _picsum,
    ]

    for provider in providers:
        try:
            url = provider(title)
            if url and _verify_url(url):
                logger.info(f"Image generated via {provider.__name__}")
                return url
        except Exception as e:
            logger.warning(f"{provider.__name__} failed: {e}")
            continue

    # Final fallback - always works
    return _picsum(title)


def regenerate_image(title):
    """Regenerate with different seed/provider."""
    seed = int(time.time())
    short = _clean(title)

    # Try pollinations with new seed
    prompt = urllib.parse.quote(f"{short} creative news illustration")
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"
    if _verify_url(url):
        return url

    # Fallback
    return f"https://picsum.photos/seed/{seed}/800/450"


def _clean(title):
    return title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()


def _pollinations_v1(title):
    """Pollinations.ai - image.pollinations.ai endpoint."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news cover photo digital art")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"


def _pollinations_v2(title):
    """Pollinations.ai - pollinations.ai/p/ endpoint."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} professional thumbnail")
    return f"https://pollinations.ai/p/{prompt}?width=800&height=450&seed={seed}&nologo=true&model=flux"


def _picsum(title):
    """Lorem Picsum - always works, random high-quality photos."""
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % 1000
    return f"https://picsum.photos/seed/{seed}/800/450"


def _verify_url(url, timeout=5):
    """Quick HEAD check to see if URL is reachable."""
    try:
        resp = httpx.head(url, timeout=timeout, follow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False
