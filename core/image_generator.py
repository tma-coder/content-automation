import logging
import urllib.parse
import hashlib
import time
import base64
import httpx
import config

logger = logging.getLogger(__name__)

POLLINATIONS_API = "https://image.pollinations.ai/prompt"

# OpenRouter image models - uses chat completions with modalities=["text","image"]
OPENROUTER_IMAGE_MODELS = [
    "google/gemini-3.1-flash-image-preview:free",
    "google/gemini-2.5-flash-preview-image:free",
    "bytedance/seedream-3.0",
    "xai/grok-2-image",
    "stabilityai/flux-2-klein-4b",
]


def generate_image(title, description=""):
    """Try OpenRouter image generation first, then Pollinations."""
    # 1. Try OpenRouter image models
    url = _openrouter_generate(title)
    if url:
        return url

    # 2. Smart Pollinations (free LLM writes prompt)
    url = _smart_pollinations(title)
    if url:
        return url

    # 3. Direct Pollinations
    return _pollinations_direct(title)


def regenerate_image(title):
    """Regenerate with different approach."""
    url = _openrouter_generate(title, style="different creative angle")
    if url:
        return url

    seed = int(time.time())
    short = _clean(title)
    prompt = urllib.parse.quote(f"{short} creative news illustration")
    return _build_pollinations_url(prompt, seed)


def _clean(title):
    return title[:60].replace('"', '').replace("'", '').replace("&", "and").strip()


def _openrouter_generate(title, style=""):
    """Generate image via OpenRouter chat completions with image modality."""
    api_key = config.OPENROUTER_IMAGE_API_KEY or config.OPENROUTER_API_KEY
    if not api_key:
        return ""

    short = _clean(title)
    prompt = f"Generate an image: Professional news thumbnail about {short}. Modern clean design, vibrant colors, no text overlay. {style}"

    for model in OPENROUTER_IMAGE_MODELS:
        try:
            logger.info(f"Trying image model: {model}")
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": ["text", "image"],
                    "max_tokens": 1000,
                },
                timeout=30,
            )

            if resp.status_code != 200:
                logger.warning(f"{model} returned {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                continue

            message = choices[0].get("message", {})
            content = message.get("content", "")

            # Check if content is a list (multimodal response)
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "image_url":
                            url = part.get("image_url", {}).get("url", "")
                            if url.startswith("data:image"):
                                return _upload_base64(url, title)
                            elif url:
                                logger.info(f"Image URL from {model}")
                                return url
                        elif part.get("type") == "image" and part.get("data"):
                            return _upload_base64(f"data:image/png;base64,{part['data']}", title)

            # Check for inline base64 in string content
            if isinstance(content, str) and "data:image" in content:
                start = content.find("data:image")
                end = content.find('"', start)
                if end == -1:
                    end = content.find("'", start)
                if end == -1:
                    end = len(content)
                return _upload_base64(content[start:end], title)

            logger.warning(f"{model} returned no image in response")

        except Exception as e:
            logger.warning(f"{model} failed: {e}")
            continue

    return ""


def _upload_base64(data_url, title):
    """Upload base64 image to Supabase Storage."""
    try:
        import db as database
        # Extract base64 data
        if "base64," in data_url:
            b64 = data_url.split("base64,")[1]
        else:
            b64 = data_url

        image_bytes = base64.b64decode(b64)
        filename = f"img_{hashlib.md5(title.encode()).hexdigest()[:12]}_{int(time.time())}.png"

        client = database.get_client()
        client.storage.from_("images").upload(filename, image_bytes, {"content-type": "image/png"})

        public_url = f"{config.SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        logger.info(f"Image uploaded to Supabase: {filename}")
        return public_url
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        return ""


def _smart_pollinations(title):
    """Use free LLM to write a vivid prompt for Pollinations."""
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        return _pollinations_direct(title)

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    free_models = [
        "google/gemini-3.5-flash:free",
        "google/gemma-4-31b-it:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-4-maverick:free",
        "microsoft/phi-4-reasoning:free",
        "qwen/qwen3-235b-a22b:free",
    ]

    for model in free_models:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"Write a 10-word vivid image description for news about: {title[:60]}. Only the description, nothing else."}],
                max_tokens=30,
            )
            desc = resp.choices[0].message.content.strip().strip('"').strip("'")[:100]
            encoded = urllib.parse.quote(desc)
            seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
            logger.info(f"Smart prompt via {model}: {desc}")
            return _build_pollinations_url(encoded, seed)
        except Exception:
            continue

    return ""


def _pollinations_direct(title):
    """Direct Pollinations URL."""
    short = _clean(title)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16)
    prompt = urllib.parse.quote(f"{short} news article cover photo digital art vibrant")
    return _build_pollinations_url(prompt, seed)


def _build_pollinations_url(encoded_prompt, seed):
    url = f"{POLLINATIONS_API}/{encoded_prompt}?width=800&height=450&seed={seed}&nologo=true"
    if config.POLLINATIONS_API_KEY:
        url += f"&token={config.POLLINATIONS_API_KEY}"
    return url
