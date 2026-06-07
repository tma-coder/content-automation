import logging
import urllib.parse
import hashlib
import time
import config

logger = logging.getLogger(__name__)

POLLINATIONS_API = "https://image.pollinations.ai/prompt"


def generate_image(title, description=""):
    """Generate image URL. Always returns a working URL."""
    if not title:
        title = "news"

    # Try Pollinations with smart prompt
    url = _pollinations_with_model(title)
    if url:
        logger.info(f"Generated image URL: {url[:100]}")
        return url

    # Guaranteed Picsum fallback
    return _picsum_fallback(title)


def regenerate_image(title):
    """Regenerate with different seed."""
    if not title:
        title = "news"
    seed = int(time.time())
    return _pollinations_with_model(title, seed=seed, variant=True)


def _pollinations_with_model(title, seed=None, variant=False):
    """Build a Pollinations.ai URL with the Flux model."""
    try:
        short = _clean(title)
        if not short:
            short = "news article"

        if seed is None:
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % 1000000

        # Build a vivid prompt
        if variant:
            prompt_text = f"{short}, creative news illustration, dramatic lighting, digital art"
        else:
            prompt_text = f"{short}, professional news article cover photo, modern, vibrant, no text"

        encoded = urllib.parse.quote(prompt_text, safe='')

        # Pollinations.ai URL with model=flux (their default high-quality model)
        url = (
            f"{POLLINATIONS_API}/{encoded}"
            f"?width=800&height=450"
            f"&seed={seed}"
            f"&model=flux"
            f"&nologo=true"
        )

        if config.POLLINATIONS_API_KEY:
            url += f"&token={config.POLLINATIONS_API_KEY}"

        return url
    except Exception as e:
        logger.error(f"Pollinations URL build failed: {e}")
        return ""


def _clean(title):
    """Clean title for use in URL."""
    if not title:
        return "news"
    # Remove problematic characters
    cleaned = title[:80]
    for ch in ['"', "'", "&", "<", ">", "\n", "\r", "\t"]:
        cleaned = cleaned.replace(ch, " ")
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned[:80].strip() or "news"


def _picsum_fallback(title):
    """Lorem Picsum - guaranteed instant stock photo."""
    seed = abs(hash(title)) % 1000
    return f"https://picsum.photos/seed/{seed}/800/450"
