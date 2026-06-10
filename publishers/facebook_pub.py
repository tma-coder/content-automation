import httpx
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


class FacebookPublisher:
    def __init__(self, page_id=None, access_token=None):
        # Allow per-page credentials, fall back to env defaults
        self.page_id = page_id or self.page_id
        self.access_token = access_token or self.access_token

    def publish(self, title, body, short_text, hashtags, image_url, link):
        if not self.access_token or not self.page_id:
            return {"success": False, "post_id": "", "error": "Facebook credentials not configured", "post_url": ""}

        message = self._build_message(title, body, hashtags, link)

        try:
            if image_url:
                result = self._post_with_binary(message, image_url)
                if result["success"]:
                    return result
                logger.warning(f"Binary upload failed: {result.get('error')}")

                result = self._post_with_url(message, image_url)
                if result["success"]:
                    return result
                logger.warning(f"URL upload failed: {result.get('error')}")

            return self._post_text(message)
        except Exception as e:
            logger.error(f"Facebook publish exception: {e}")
            return {"success": False, "post_id": "", "error": str(e), "post_url": ""}

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

    @staticmethod
    def _make_post_url(post_id):
        """Build a Facebook URL from the post ID."""
        if not post_id:
            return ""
        # Post IDs come back as "pageid_postid" — Facebook URL format
        return f"https://www.facebook.com/{post_id}"

    def _result(self, success, post_id="", error=""):
        return {
            "success": success,
            "post_id": post_id,
            "error": error,
            "post_url": self._make_post_url(post_id) if success else "",
        }

    def _post_with_binary(self, message, image_url):
        """Download image then upload binary to Facebook (most reliable)."""
        try:
            img_resp = httpx.get(image_url, timeout=45, follow_redirects=True)
            if img_resp.status_code != 200 or not img_resp.content:
                return self._result(False, error=f"Image fetch failed: HTTP {img_resp.status_code}")

            content_type = img_resp.headers.get("content-type", "image/png")
            if not content_type.startswith("image/"):
                return self._result(False, error=f"Not an image: {content_type}")

            resp = httpx.post(
                f"{GRAPH_API}/{self.page_id}/photos",
                data={
                    "message": message,
                    "access_token": self.access_token,
                    "published": "true",  # Explicitly publish (default but be explicit)
                },
                files={"source": ("image.png", img_resp.content, content_type)},
                timeout=60,
            )
            data = resp.json()
            if "id" in data:
                # For photo posts, also get the actual post_id (page_id_postid format)
                post_id = data.get("post_id") or data.get("id")
                logger.info(f"FB photo posted: id={data.get('id')}, post_id={data.get('post_id')}")
                return self._result(True, post_id=post_id)
            err = data.get("error", {}).get("message", str(data))
            return self._result(False, error=err)
        except Exception as e:
            return self._result(False, error=f"Binary upload error: {e}")

    def _post_with_url(self, message, image_url):
        """Pass URL to Facebook - Facebook will fetch it."""
        try:
            resp = httpx.post(
                f"{GRAPH_API}/{self.page_id}/photos",
                data={
                    "message": message,
                    "url": image_url,
                    "access_token": self.access_token,
                    "published": "true",
                },
                timeout=60,
            )
            data = resp.json()
            if "id" in data:
                post_id = data.get("post_id") or data.get("id")
                return self._result(True, post_id=post_id)
            err = data.get("error", {}).get("message", str(data))
            return self._result(False, error=err)
        except Exception as e:
            return self._result(False, error=f"URL upload error: {e}")

    def _post_text(self, message):
        """Text-only post fallback."""
        try:
            resp = httpx.post(
                f"{GRAPH_API}/{self.page_id}/feed",
                data={
                    "message": message,
                    "access_token": self.access_token,
                    "published": "true",
                },
                timeout=30,
            )
            data = resp.json()
            if "id" in data:
                return self._result(True, post_id=data["id"])
            err = data.get("error", {}).get("message", str(data))
            return self._result(False, error=err)
        except Exception as e:
            return self._result(False, error=f"Text post error: {e}")
