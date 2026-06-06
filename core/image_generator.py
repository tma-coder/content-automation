import logging
import urllib.parse
import hashlib
import time
import httpx
import config

logger = logging.getLogger(__name__)


def generate_image(title, description=""):
    """Try multiple image providers until one works."""
    providers = [
        _openrouter_image,
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
            elif url and url.startswith("https://image.pollinations"):
                # Pollinations generates on-demand, skip verify
                logger.info(f"Image URL set via {provider.__name__} (on-demand)")
                return url
        except Exception as e:
            logger.warning(f"{provider.__name__} failed: {e}")
            continue

    return _picsum(title)


def regenerate_image(title):
    """Regenerate with different seed/provider."""
    seed = int(time.time())
    short = _clean(title)

    # Try OpenRouter first
    try:
        url = _openrouter_image(title, seed=seed)
        if url and _verify_url(url):
            return url
    except Exception:
        pass

    prompt = urllib.parse.quote(f"{short} creative news illustration")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"


def _clean(title):
    return title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()


def _openrouter_image(title, seed=None):
    """Try OpenRouter image generation models."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        return ""

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    short = _clean(title)
    prompt = f"Professional news thumbnail: {short}. Modern, clean, vibrant colors, no text overlay."

    # Image generation models on OpenRouter
    image_models = [
        "openai/dall-e-3",
        "google/imagen-4",
        "stability/stable-diffusion-3",
        "stability/sdxl",
        "black-forest-labs/flux-1.1-pro",
        "black-forest-labs/flux-schnell",
    ]

    for model in image_models:
        try:
            logger.info(f"Trying image model: {model}")
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            if response.data and response.data[0].url:
                logger.info(f"Image generated via OpenRouter/{model}")
                return response.data[0].url
        except Exception as e:
            logger.warning(f"OpenRouter {model} failed: {e}")
            continue

    # Fallback: use free chat model to make a smart Pollinations prompt
    return _smart_pollinations(title, client)


def _smart_pollinations(title, client):
    """Use free LLM to create a better Pollinations prompt."""
    free_models = [
        "google/gemini-3.5-flash:free",
        "google/gemma-4-31b-it:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-4-maverick:free",
    ]

    for model in free_models:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"Write a 10-word vivid image description for news about: {title[:60]}. Just the description, nothing else."}],
                max_tokens=30,
            )
            desc = resp.choices[0].message.content.strip()[:100]
            encoded = urllib.parse.quote(desc)
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
            return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=450&seed={seed}&nologo=true"
        except Exception:
            continue

    return ""


def _pollinations_v1(title):
    """Pollinations.ai - image.pollinations.ai endpoint."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news cover photo digital art")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"


def _pollinations_v2(title):
    """Pollinations.ai - pollinations.ai/p/ endpoint with Flux."""
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
