import httpx
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


class FacebookPublisher:
    def publish(self, title, body, short_text, hashtags, image_url, link):
        if not config.META_PAGE_ACCESS_TOKEN or not config.FACEBOOK_PAGE_ID:
            return {"success": False, "post_id": "", "error": "Facebook credentials not configured"}

        message = self._build_message(title, body, hashtags, link)

        try:
            if image_url:
                # Try uploading image as binary first (more reliable)
                result = self._post_with_binary(message, image_url)
                if result["success"]:
                    return result
                # Fall back to URL-based upload
                logger.warning(f"Binary upload failed, trying URL: {result.get('error')}")
                result = self._post_with_url(message, image_url)
                if result["success"]:
                    return result
                # Final fallback to text-only
                logger.warning(f"URL upload failed, falling back to text: {result.get('error')}")

            return self._post_text(message)
        except Exception as e:
            logger.error(f"Facebook publish exception: {e}")
            return {"success": False, "post_id": "", "error": str(e)}

    @staticmethod
    def _build_message(title, body, hashtags, link):
        parts = []
        if title:
            parts.append(title)
        if body:
            parts.append(body)
        if hashtags:
            parts.append(hashtags)
        if link:
            parts.append(f"Source: {link}")
        return "\n\n".join(parts)

    def _post_with_binary(self, message, image_url):
        """Download image then upload binary to Facebook (most reliable)."""
        try:
            img_resp = httpx.get(image_url, timeout=45, follow_redirects=True)
            if img_resp.status_code != 200 or not img_resp.content:
                return {"success": False, "post_id": "", "error": f"Image fetch failed: HTTP {img_resp.status_code}"}

            # Verify it's actually an image
            content_type = img_resp.headers.get("content-type", "image/png")
            if not content_type.startswith("image/"):
                return {"success": False, "post_id": "", "error": f"Not an image: {content_type}"}

            resp = httpx.post(
                f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/photos",
                data={
                    "message": message,
                    "access_token": config.META_PAGE_ACCESS_TOKEN,
                },
                files={"source": ("image.png", img_resp.content, content_type)},
                timeout=60,
            )
            data = resp.json()
            if "id" in data:
                return {"success": True, "post_id": data["id"], "error": ""}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "post_id": "", "error": err}
        except Exception as e:
            return {"success": False, "post_id": "", "error": f"Binary upload error: {e}"}

    def _post_with_url(self, message, image_url):
        """Pass URL to Facebook - Facebook will fetch it."""
        try:
            resp = httpx.post(
                f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/photos",
                data={
                    "message": message,
                    "url": image_url,
                    "access_token": config.META_PAGE_ACCESS_TOKEN,
                },
                timeout=60,
            )
            data = resp.json()
            if "id" in data:
                return {"success": True, "post_id": data["id"], "error": ""}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "post_id": "", "error": err}
        except Exception as e:
            return {"success": False, "post_id": "", "error": f"URL upload error: {e}"}

    def _post_text(self, message):
        """Text-only post fallback."""
        try:
            resp = httpx.post(
                f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/feed",
                data={
                    "message": message,
                    "access_token": config.META_PAGE_ACCESS_TOKEN,
                },
                timeout=30,
            )
            data = resp.json()
            if "id" in data:
                return {"success": True, "post_id": data["id"], "error": ""}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "post_id": "", "error": err}
        except Exception as e:
            return {"success": False, "post_id": "", "error": f"Text post error: {e}"}
