import logging
import urllib.parse
import hashlib
import time
import httpx
import config

logger = logging.getLogger(__name__)


def generate_image(title, description=""):
    """Try multiple free image providers until one works."""
    providers = [
        _smart_pollinations,
        _pollinations_v1,
        _pollinations_v2,
        _picsum,
    ]

    for provider in providers:
        try:
            url = provider(title)
            if url:
                logger.info(f"Image via {provider.__name__}")
                return url
        except Exception as e:
            logger.warning(f"{provider.__name__} failed: {e}")
            continue

    return _picsum(title)


def regenerate_image(title):
    """Regenerate with different seed."""
    seed = int(time.time())
    short = _clean(title)
    prompt = urllib.parse.quote(f"{short} creative news illustration")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"


def _clean(title):
    return title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()


def _smart_pollinations(title):
    """Use free LLM to write a vivid prompt, then generate via Pollinations."""
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        return ""

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    free_models = [
        "google/gemini-3.5-flash:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-4-maverick:free",
        "microsoft/phi-4-reasoning:free",
        "qwen/qwen3-235b-a22b:free",
        "mistralai/mistral-small-3.2-24b-instruct:free",
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
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=450&seed={seed}&nologo=true"
            logger.info(f"Smart prompt via {model}: {desc}")
            return url
        except Exception as e:
            logger.warning(f"Smart prompt {model} failed: {e}")
            continue

    return ""


def _pollinations_v1(title):
    """Pollinations.ai - direct prompt."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news cover photo digital art")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=450&seed={seed}&nologo=true"


def _pollinations_v2(title):
    """Pollinations.ai - Flux model."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} professional thumbnail")
    return f"https://pollinations.ai/p/{prompt}?width=800&height=450&seed={seed}&nologo=true&model=flux"


def _picsum(title):
    """Lorem Picsum - always works, high-quality stock photos."""
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % 1000
    return f"https://picsum.photos/seed/{seed}/800/450"
