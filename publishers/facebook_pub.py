import httpx
import config

GRAPH_API = "https://graph.facebook.com/v21.0"


class FacebookPublisher:
    def publish(self, title, body, short_text, hashtags, image_url, link):
        message = f"{title}\n\n{body}\n\n{hashtags}\n\nSource: {link}"
        try:
            if image_url:
                return self._post_with_image(message, image_url)
            return self._post_text(message)
        except Exception as e:
            return {"success": False, "post_id": "", "error": str(e)}

    def _post_with_image(self, message, image_url):
        resp = httpx.post(f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/photos",
            data={"message": message, "url": image_url, "access_token": config.META_PAGE_ACCESS_TOKEN},
            timeout=60)
        data = resp.json()
        if "id" in data:
            return {"success": True, "post_id": data["id"], "error": ""}
        return {"success": False, "post_id": "", "error": data.get("error", {}).get("message", str(data))}

    def _post_text(self, message):
        resp = httpx.post(f"{GRAPH_API}/{config.FACEBOOK_PAGE_ID}/feed",
            data={"message": message, "access_token": config.META_PAGE_ACCESS_TOKEN},
            timeout=30)
        data = resp.json()
        if "id" in data:
            return {"success": True, "post_id": data["id"], "error": ""}
        return {"success": False, "post_id": "", "error": data.get("error", {}).get("message", str(data))}
