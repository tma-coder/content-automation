import os
import base64
import logging
from datetime import datetime
from google import genai
from google.genai import types
import config

logger = logging.getLogger(__name__)

client = genai.Client(api_key=config.GOOGLE_GENAI_API_KEY)


def generate_image(title, description):
    logger.info(f"Generating image for: {title}")

    prompt = (
        f"Generate an image: Professional social media graphic for a news article titled: '{title}'. "
        f"Context: {description[:200]}. "
        f"Style: Modern, clean, vibrant colors. No text overlay."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )

        image_data = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_data = part.inline_data.data
                    break

        if not image_data:
            logger.warning("No image generated")
            return ""

        os.makedirs(config.STORAGE_DIR, exist_ok=True)
        filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(config.STORAGE_DIR, filename)

        with open(filepath, "wb") as f:
            if isinstance(image_data, str):
                f.write(base64.b64decode(image_data))
            else:
                f.write(image_data)

        logger.info(f"Image saved: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ""
