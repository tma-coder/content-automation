import logging
import urllib.parse
import hashlib
import time

logger = logging.getLogger(__name__)


def generate_image(title, description=""):
    """Generate image URL via Pollinations.ai - reliable, free, no API key."""
    short = title[:60].replace('"', '').replace("'", '').replace("&", "and")
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news article cover photo")
    return f"https://pollinations.ai/p/{prompt}?width=800&height=450&seed={seed}&nologo=true&model=flux"


def regenerate_image(title):
    """Regenerate with different seed."""
    short = title[:60].replace('"', '').replace("'", '').replace("&", "and")
    seed = int(time.time())
    prompt = urllib.parse.quote(f"{short} digital art news thumbnail")
    return f"https://pollinations.ai/p/{prompt}?width=800&height=450&seed={seed}&nologo=true&model=flux"
