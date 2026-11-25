import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local development settings without requiring python-dotenv. Existing
# process environment variables take precedence over values in the file.
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(name.strip(), value)

DEBUG = os.getenv("DJANGO_DEBUG") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or ("local-development-only" if DEBUG else "")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
ROOT_URLCONF = "spotter.urls"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
WHITENOISE_ROOT = BASE_DIR / "frontend" / "dist"
WHITENOISE_INDEX_FILE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
