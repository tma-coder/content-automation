import logging
import urllib.parse
import hashlib

logger = logging.getLogger(__name__)


def generate_image(title, description=""):
    """Generate AI image using Pollinations.ai - free, no API key."""
    try:
        # Keep prompt short and clean for reliable generation
        short_title = title[:80].replace('"', '').replace("'", "")
        prompt = f"news thumbnail {short_title}, modern digital art, vibrant"
        encoded = urllib.parse.quote(prompt)
        # Add seed based on title for consistent images
        seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"
        logger.info(f"Image URL generated for: {short_title}")
        return image_url
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ""


def regenerate_image(title):
    """Regenerate with a different style by adding random seed."""
    import time
    seed = int(time.time())
    short_title = title[:80].replace('"', '').replace("'", "")
    prompt = f"news article cover {short_title}, professional graphic design"
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"
