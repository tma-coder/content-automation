import logging
import urllib.parse
import hashlib
import time

logger = logging.getLogger(__name__)

# Image generation providers - tries in order
PROVIDERS = ["pollinations", "openrouter"]


def generate_image(title, description="", provider=None):
    """Try multiple providers for image generation."""
    providers = [provider] if provider else PROVIDERS

    for p in providers:
        try:
            if p == "pollinations":
                url = _pollinations(title)
            elif p == "openrouter":
                url = _openrouter(title, description)
            else:
                continue

            if url:
                logger.info(f"Image generated via {p}: {title[:50]}")
                return url
        except Exception as e:
            logger.warning(f"Image provider {p} failed: {e}")
            continue

    return ""


def regenerate_image(title, provider=None):
    """Regenerate with different seed/style."""
    seed = int(time.time())
    if provider == "openrouter":
        return _openrouter(title, "", seed=seed)

    short = title[:80].replace('"', '').replace("'", "")
    prompt = f"news cover art {short}, digital illustration"
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"


def _pollinations(title):
    """Pollinations.ai - free, no API key, generates on URL load."""
    short = title[:80].replace('"', '').replace("'", "")
    prompt = f"news thumbnail {short}, modern digital art, vibrant"
    encoded = urllib.parse.quote(prompt)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={seed}&nologo=true"


def _openrouter(title, description="", seed=None):
    """Use OpenRouter with a free model to generate image via markdown."""
    import config
    from openai import OpenAI

    if not config.OPENROUTER_API_KEY:
        return ""

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=config.OPENROUTER_API_KEY)

    prompt = f"""Generate a detailed image description for a news article thumbnail about: {title[:100]}
Return ONLY a Pollinations.ai URL in this exact format (nothing else):
https://image.pollinations.ai/prompt/YOUR_DESCRIPTION_HERE?width=800&height=500&nologo=true

Make the description vivid, professional, suitable for news. URL-encode spaces as %20. Keep it under 200 chars."""

    models = [
        "google/gemini-3.5-flash:free",
        "google/gemma-4-31b-it:free",
        "deepseek/deepseek-chat-v3-0324:free",
    ]

    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            text = resp.choices[0].message.content.strip()
            # Extract URL from response
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("https://image.pollinations.ai/"):
                    return line
            # If model returned a description, build the URL
            if text and not text.startswith("http"):
                desc = text[:200].replace('"', '').replace("'", "")
                encoded = urllib.parse.quote(desc)
                return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&nologo=true"
        except Exception:
            continue

    return ""
