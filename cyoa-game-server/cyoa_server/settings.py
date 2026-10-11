"""
Django settings for cyoa_server project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', '1').lower() in ('1', 'true', 'yes')

if not DEBUG and SECRET_KEY == 'dev-secret-key-change-in-production':
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('DJANGO_SECRET_KEY is required in production')

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'cyoa.mac.stargate.lan,cyoa.chat-sdp.org,localhost,127.0.0.1,cyoa-game-server,host.docker.internal').split(',')

# Proxy SSL awareness
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', 'https://cyoa.mac.stargate.lan,https://cyoa.chat-sdp.org').split(',') if origin.strip()]
SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SECURE_COOKIES', '0') == '1'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
FRONTEND_DEV = os.environ.get('FRONTEND_DEV', '0') == '1'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'game',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'game.cors_middleware.PWACorsMiddleware',  # Add CORS headers to PWA assets
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'game.cloudflare_auth.CloudflareAccessMiddleware',  # after AuthenticationMiddleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cyoa_server.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'cyoa_server.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': Path(os.environ.get('DJANGO_DATABASE_PATH', str(BASE_DIR / 'db' / 'db.sqlite3'))),
    }
}

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Anthropic API Configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('DJANGO_MEDIA_ROOT', str(BASE_DIR / 'media')))

# Login URL
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/admin/login/'

# ---------------------------------------------------------------------------
# Cloudflare Access (Zero Trust) authentication
# ---------------------------------------------------------------------------
# Set CLOUDFLARE_AUTH_ENABLED=True once the tunnel + Access app are live.
# When False the middleware is a no-op and normal Django login is used.
CLOUDFLARE_AUTH_ENABLED = os.environ.get('CLOUDFLARE_AUTH_ENABLED', '').lower() in ('1', 'true', 'yes')

# Your Cloudflare One team domain, e.g. https://myteam.cloudflareaccess.com
CLOUDFLARE_TEAM_DOMAIN = os.environ.get('CLOUDFLARE_TEAM_DOMAIN', '')

# The Application Audience (AUD) tag — found in Zero Trust → Access → Applications → your app
CLOUDFLARE_AUD = os.environ.get('CLOUDFLARE_AUD', '')

# Emails that get is_staff + is_superuser when auto-created (comma-separated)
CLOUDFLARE_ADMIN_EMAILS = [
    e.strip() for e in os.environ.get('CLOUDFLARE_ADMIN_EMAILS', '').split(',')
    if e.strip()
]

# Correlate versioned player mutations without logging payloads or provider keys.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'chat_console': {'class': 'logging.StreamHandler'}},
    'loggers': {'game.chat_api': {'handlers': ['chat_console'], 'level': 'INFO', 'propagate': False}},
}
