import os
import certifi
from dotenv import load_dotenv

load_dotenv()

# Fix SSL certificates for Windows
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


def _get(key, default=""):
    return os.getenv(key, default)


GOOGLE_GENAI_API_KEY = _get("GOOGLE_GENAI_API_KEY")
META_PAGE_ACCESS_TOKEN = _get("META_PAGE_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = _get("FACEBOOK_PAGE_ID")

NEWS_TOPICS = [t.strip() for t in _get("NEWS_TOPICS", "technology").split(",")]
POLL_INTERVAL_MINUTES = int(_get("POLL_INTERVAL_MINUTES", "30"))
AUTO_MODE = _get("AUTO_MODE", "false").lower() == "true"
MAX_ARTICLES_PER_CYCLE = int(_get("MAX_ARTICLES_PER_CYCLE", "1"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "images")
DB_PATH = os.path.join(BASE_DIR, "data.db")
LOG_PATH = os.path.join(BASE_DIR, "logs", "app.log")
