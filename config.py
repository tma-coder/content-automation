import os

GOOGLE_GENAI_API_KEY = os.environ.get("GOOGLE_GENAI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_IMAGE_API_KEY = os.environ.get("OPENROUTER_IMAGE_API_KEY", "")
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")
META_PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", ""))
CRON_SECRET = os.environ.get("CRON_SECRET", "")

NEWS_TOPICS = [t.strip() for t in os.environ.get("NEWS_TOPICS", "technology,AI,science").split(",")]
MAX_ARTICLES_PER_CYCLE = int(os.environ.get("MAX_ARTICLES_PER_CYCLE", "1"))
AUTO_MODE = os.environ.get("AUTO_MODE", "false").lower() == "true"
