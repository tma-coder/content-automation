import logging
import urllib.parse
import hashlib
import time
import config

logger = logging.getLogger(__name__)

POLLINATIONS_API = "https://image.pollinations.ai/prompt"


def generate_image(title, description=""):
    """Generate Pollinations image URL. Image is created when browser loads it."""
    # Try smart prompt first, fall back to direct
    url = _smart_pollinations(title)
    if not url:
        url = _pollinations_direct(title)
    return url


def regenerate_image(title):
    """Regenerate with different seed for a new image."""
    seed = int(time.time())
    short = _clean(title)
    prompt = urllib.parse.quote(f"{short} creative news illustration")
    return _build_url(prompt, seed)


def _clean(title):
    return title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()


def _build_url(encoded_prompt, seed):
    """Build Pollinations URL with optional API key."""
    url = f"{POLLINATIONS_API}/{encoded_prompt}?width=800&height=450&seed={seed}&nologo=true"
    if config.POLLINATIONS_API_KEY:
        url += f"&token={config.POLLINATIONS_API_KEY}"
    return url


def _smart_pollinations(title):
    """Use free LLM to write a vivid prompt for better images."""
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
                messages=[{"role": "user", "content": f"Write a 10-word vivid image description for news about: {title[:60]}. Only the description, no quotes, no explanation."}],
                max_tokens=30,
            )
            desc = resp.choices[0].message.content.strip().strip('"').strip("'")[:100]
            encoded = urllib.parse.quote(desc)
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
            logger.info(f"Smart prompt via {model}: {desc}")
            return _build_url(encoded, seed)
        except Exception as e:
            logger.warning(f"{model} failed: {e}")
            continue

    return ""


def _pollinations_direct(title):
    """Direct Pollinations URL - no LLM needed."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news article cover photo digital art vibrant")
    return _build_url(prompt, seed)
