import httpx
import logging
import config

logger = logging.getLogger(__name__)
GRAPH_API = "https://graph.facebook.com/v21.0"


class FacebookPublisher:
    def publish(self, title, body, short_text, hashtags, image_path, link):
        message = f"{title}\n\n{body}\n\n{hashtags}\n\nSource: {link}"
        try:
            if image_path:
                return self._post_with_image(message, image_path)
            else:
                return self._post_text(message)
        except Exception as e:
            logger.error(f"Facebook error: {e}")
            return {"success": False, "post_id": "", "error": str(e)}

    def _post_with_image(self, message, image_path):
        url = f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/photos"
        with open(image_path, "rb") as img:
            resp = httpx.post(url,
                data={"message": message, "access_token": config.META_PAGE_ACCESS_TOKEN},
                files={"source": ("image.png", img, "image/png")},
                timeout=60)
        data = resp.json()
        if "id" in data:
            return {"success": True, "post_id": data["id"], "error": ""}
        return {"success": False, "post_id": "", "error": data.get("error", {}).get("message", str(data))}

    def _post_text(self, message):
        url = f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/feed"
        resp = httpx.post(url,
            data={"message": message, "access_token": config.META_PAGE_ACCESS_TOKEN},
            timeout=30)
        data = resp.json()
        if "id" in data:
            return {"success": True, "post_id": data["id"], "error": ""}
        return {"success": False, "post_id": "", "error": data.get("error", {}).get("message", str(data))}
