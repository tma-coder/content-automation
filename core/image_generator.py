import logging
import urllib.parse
import hashlib
import time
import config

logger = logging.getLogger(__name__)

POLLINATIONS_API = "https://image.pollinations.ai/prompt"

FREE_TEXT_MODELS = [
    "google/gemini-3.5-flash:free",
    "google/gemma-4-31b-it:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-4-maverick:free",
    "microsoft/phi-4-reasoning:free",
    "qwen/qwen3-235b-a22b:free",
]


def generate_image(title, description=""):
    """Generate image URL. Always returns a working URL (Picsum fallback)."""
    if not title:
        return _picsum_fallback("default")

    # Try smart Pollinations (free LLM writes vivid prompt)
    url = _smart_pollinations(title)
    if url:
        return url

    # Direct Pollinations
    url = _pollinations_direct(title)
    if url:
        return url

    # Guaranteed fallback
    return _picsum_fallback(title)


def regenerate_image(title):
    """Regenerate with different seed/prompt."""
    if not title:
        return _picsum_fallback("default")

    # Use new timestamp as seed for variation
    seed = int(time.time())
    short = _clean(title)

    # Try smart approach first
    url = _smart_pollinations(title, seed=seed, variant=True)
    if url:
        return url

    # Direct with new seed
    prompt = urllib.parse.quote(f"{short} creative news illustration")
    return _build_pollinations_url(prompt, seed)


def _clean(title):
    cleaned = title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()
    # Remove any newlines/control chars
    cleaned = ''.join(c if c.isprintable() else ' ' for c in cleaned)
    return cleaned.strip() or "news"


def _build_pollinations_url(encoded_prompt, seed):
    url = f"{POLLINATIONS_API}/{encoded_prompt}?width=800&height=450&seed={seed}&nologo=true"
    if config.POLLINATIONS_API_KEY:
        url += f"&token={config.POLLINATIONS_API_KEY}"
    return url


def _smart_pollinations(title, seed=None, variant=False):
    """Use free LLM to write a vivid prompt for Pollinations."""
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed")
        return ""

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    variant_text = "Make it visually different and creative." if variant else ""
    user_prompt = f"Write a 10-word vivid image description for a news article thumbnail about: {title[:80]}. {variant_text} Only the description, no quotes or explanation."

    if seed is None:
        seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)

    for model in FREE_TEXT_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=40,
                temperature=0.9 if variant else 0.7,
            )

            if not resp.choices or not resp.choices[0].message.content:
                continue

            desc = resp.choices[0].message.content.strip()
            # Clean up quotes and newlines
            desc = desc.strip('"').strip("'").replace("\n", " ")[:150]

            if not desc:
                continue

            encoded = urllib.parse.quote(desc)
            logger.info(f"Smart prompt via {model}: {desc[:50]}...")
            return _build_pollinations_url(encoded, seed)

        except Exception as e:
            logger.warning(f"Text model {model} failed: {e}")
            continue

    return ""


def _pollinations_direct(title):
    """Direct Pollinations URL with simple prompt."""
    try:
        short = _clean(title)
        seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
        prompt = urllib.parse.quote(f"{short}, news article cover photo, digital art, vibrant colors")
        return _build_pollinations_url(prompt, seed)
    except Exception as e:
        logger.error(f"Direct pollinations failed: {e}")
        return ""


def _picsum_fallback(title):
    """Lorem Picsum - guaranteed to return a real image instantly."""
    seed = abs(hash(title)) % 1000
    return f"https://picsum.photos/seed/{seed}/800/450"
