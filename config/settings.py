import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")




DEBUG = os.getenv("DEBUG", "1") == "1"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")






INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "marks",
    "widget_tweaks",
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'config.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'config.wsgi.application'








DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "postgres"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}








AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]








LANGUAGE_CODE = 'ru-ru'


TIME_ZONE = 'UTC'


USE_I18N = True


USE_TZ = True








STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'






DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'


CSRF_TRUSTED_ORIGINS = [
    "https://automarks.tw1.ru",
    "https://www.automarks.tw1.ru"
]


# Базовый домен коротких ссылок сокращателя. Дефолт — наш прод-домен.
# Если позже понадобится брендовый (напр. https://l.el-ed.ru) — меняется только эта переменная.
SHORTLINK_BASE_DOMAIN = os.getenv("SHORTLINK_BASE_DOMAIN", "https://automarks.tw1.ru")


# Авто-sync справочника UTM: CSV-экспорт вкладок Google Sheet (medium/source/campaign).
UTM_DICTIONARY_CSV_URLS = {
    "medium": os.getenv("UTM_DICTIONARY_MEDIUM_CSV_URL", ""),
    "source": os.getenv("UTM_DICTIONARY_SOURCE_CSV_URL", ""),
    "campaign": os.getenv("UTM_DICTIONARY_CAMPAIGN_CSV_URL", ""),
}


TELEGRAM_NOTIFY_BOT_TOKEN = os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "")
TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID = os.getenv("TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID", "")
TELEGRAM_NOTIFY_STATUS_CHAT_ID = os.getenv("TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
TASKS_PLATFORM_NAME = os.getenv("TASKS_PLATFORM_NAME", "")
WEEKLY_TASKS_REPORT_CHAT_ID = os.getenv("WEEKLY_TASKS_REPORT_CHAT_ID", "")
WEEKLY_TASKS_REPORT_TZ = os.getenv("WEEKLY_TASKS_REPORT_TZ", "Europe/Moscow")
TASKS_TIME_ZONE = os.getenv("TASKS_TIME_ZONE", TIME_ZONE or "UTC")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


# --- Раздел TikTok-воронок (порт el-tiktok-funnels-auto) ---------------------
# Токен-гейт на Дев-панель + Кабинеты (один общий, server-side аналог X-Dev-Token).
FUNNELS_DEV_TOKEN = os.getenv("FUNNELS_DEV_TOKEN", "")
# Константы для генерации JS-скрипта лендинга.
YM_COUNTER_ID = os.getenv("YM_COUNTER_ID", "")
WEBHOOK_URL = os.getenv("FUNNELS_WEBHOOK_URL", "")
WEBHOOK_TOKEN = os.getenv("FUNNELS_WEBHOOK_TOKEN", "")
# База для рекламной UTM-ссылки (домен лендингов).
LANDING_BASE_URL = os.getenv("LANDING_BASE_URL", "https://go-egeland.ru")
# Синхронный dual-write воронок/кабинетов в склад через вебхук n8n `funnel-sync`.
N8N_SYNC_URL = os.getenv("N8N_SYNC_URL", "")
N8N_SYNC_TOKEN = os.getenv("N8N_SYNC_TOKEN", "")
# Чат Telegram для уведомлений о новых заявках на воронку (опц.).
FUNNELS_NOTIFY_CHAT_ID = os.getenv("FUNNELS_NOTIFY_CHAT_ID", "")
