import logging
import urllib.parse
import hashlib
import time
import base64
import os
import config

logger = logging.getLogger(__name__)

# Image models on OpenRouter (tries in order)
IMAGE_MODELS = [
    "openai/dall-e-3",
    "google/imagen-4",
    "stability/stable-diffusion-3",
]

# Free fallback models to generate Pollinations URL
FREE_MODELS = [
    "google/gemini-3.5-flash:free",
    "google/gemma-4-31b-it:free",
    "deepseek/deepseek-chat-v3-0324:free",
]


def generate_image(title, description=""):
    """Try OpenRouter image API first, then Pollinations fallback."""
    # Try OpenRouter with dedicated image API key
    if config.OPENROUTER_IMAGE_API_KEY:
        url = _openrouter_image(title)
        if url:
            return url

    # Fallback to Pollinations
    return _pollinations(title)


def regenerate_image(title):
    """Regenerate with different seed/style."""
    if config.OPENROUTER_IMAGE_API_KEY:
        url = _openrouter_image(title, style="different angle, creative composition")
        if url:
            return url

    seed = int(time.time())
    short = title[:80].replace('"', '').replace("'", "")
    prompt = f"news cover art {short}, digital illustration"
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"


def _openrouter_image(title, style=""):
    """Generate image using OpenRouter image API."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.OPENROUTER_IMAGE_API_KEY,
    )

    short = title[:100].replace('"', '').replace("'", "")
    prompt = f"Professional news article thumbnail about: {short}. Modern, clean design, vibrant colors, no text. {style}"

    for model in IMAGE_MODELS:
        try:
            logger.info(f"Trying image model: {model}")
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size="1024x1024",
            )

            if response.data and response.data[0].url:
                logger.info(f"Image generated via {model}")
                return response.data[0].url

            if response.data and response.data[0].b64_json:
                # Upload base64 image to Supabase Storage
                return _upload_to_supabase(response.data[0].b64_json, title)

        except Exception as e:
            logger.warning(f"Image model {model} failed: {e}")
            continue

    # Fallback: use free model to create a smart Pollinations URL
    return _smart_pollinations(title)


def _pollinations(title):
    """Pollinations.ai - free, generates on URL load."""
    short = title[:80].replace('"', '').replace("'", "")
    prompt = f"news thumbnail {short}, modern digital art, vibrant"
    encoded = urllib.parse.quote(prompt)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"


def _smart_pollinations(title):
    """Use free LLM to create a better image prompt for Pollinations."""
    from openai import OpenAI

    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        return _pollinations(title)

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    for model in FREE_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"Write a short (under 15 words) vivid image description for a news thumbnail about: {title[:80]}. Just the description, nothing else."}],
                max_tokens=50,
            )
            desc = resp.choices[0].message.content.strip()[:150]
            encoded = urllib.parse.quote(desc)
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
            return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"
        except Exception:
            continue

    return _pollinations(title)


def _upload_to_supabase(b64_data, title):
    """Upload base64 image to Supabase Storage and return public URL."""
    try:
        import db as database
        filename = f"img_{hashlib.md5(title.encode()).hexdigest()[:12]}_{int(time.time())}.png"
        image_bytes = base64.b64decode(b64_data)
        client = database.get_client()
        client.storage.from_("images").upload(filename, image_bytes, {"content-type": "image/png"})
        public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        logger.info(f"Image uploaded to Supabase: {filename}")
        return public_url
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        return ""
