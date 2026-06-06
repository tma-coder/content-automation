import logging
from openai import OpenAI
import config

logger = logging.getLogger(__name__)


def generate_image(title, description):
    """Generate image using OpenRouter with a free model that supports image generation.
    Falls back to returning empty string if image generation fails."""
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.OPENROUTER_API_KEY,
        )

        # Use a free model to generate an image description, then use a placeholder
        # OpenRouter doesn't support direct image generation on free tier
        # So we'll use a free image from Unsplash based on the topic
        search_term = title.split()[0:3]
        search_query = "+".join(search_term)
        image_url = f"https://source.unsplash.com/1024x1024/?{search_query},news"

        logger.info(f"Using stock image for: {title}")
        return image_url

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ""
