import base64
import logging
from datetime import datetime
from google import genai
from google.genai import types
import config
import db

logger = logging.getLogger(__name__)


def generate_image(title, description):
    client = genai.Client(api_key=config.GOOGLE_GENAI_API_KEY)

    prompt = (
        f"Generate an image: Professional social media graphic for news article: '{title}'. "
        f"Context: {description[:200]}. Modern, clean, vibrant. No text overlay."
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
            return ""

        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data

        # Upload to Supabase Storage
        filename = f"img_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        sb = db.get_client()
        sb.storage.from_("images").upload(filename, image_bytes, {"content-type": "image/png"})

        # Get public URL
        public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        return public_url

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ""
