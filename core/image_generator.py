import logging
import urllib.parse

logger = logging.getLogger(__name__)


def generate_image(title, description):
    """Generate AI image using Pollinations.ai - completely free, no API key needed."""
    try:
        prompt = f"Professional news article thumbnail, modern social media graphic about: {title}. Clean design, vibrant colors, no text overlay"
        encoded = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"
        logger.info(f"Generated image URL for: {title}")
        return image_url
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ""
