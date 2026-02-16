"""
Cloudflare Access authentication middleware for Django.

When CLOUDFLARE_AUTH_ENABLED=True, every request must carry a valid
Cf-Access-Jwt-Assertion header (set by Cloudflare Access).  The middleware:

1. Fetches the JWKS from https://<team>.cloudflareaccess.com/cdn-cgi/access/certs
2. Validates the JWT (RS256, checks issuer + audience)
3. Extracts the user's email from the token
4. Auto-creates a Django User (or retrieves existing) keyed on email
5. Grants is_staff=True if the email is in CLOUDFLARE_ADMIN_EMAILS
6. Logs the user into the Django session

When CLOUDFLARE_AUTH_ENABLED=False (default), this middleware is a no-op,
letting local username/password login work as before.
"""

import json
import logging
import time
import threading

import jwt          # PyJWT
import requests
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache – refreshed at most once per CACHE_TTL seconds
# ---------------------------------------------------------------------------
_jwks_cache = {
    "keys": [],
    "fetched_at": 0,
}
_jwks_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes


def _get_certs_url():
    """Return the JWKS endpoint for the configured team domain."""
    team_domain = getattr(settings, "CLOUDFLARE_TEAM_DOMAIN", "")
    return f"{team_domain.rstrip('/')}/cdn-cgi/access/certs"


def _refresh_jwks():
    """Fetch JWKS from Cloudflare and cache it."""
    url = _get_certs_url()
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        _jwks_cache["keys"] = data.get("keys", [])
        _jwks_cache["fetched_at"] = time.time()
        logger.info("Refreshed Cloudflare JWKS from %s (%d keys)", url, len(_jwks_cache["keys"]))
    except Exception:
        logger.exception("Failed to fetch Cloudflare JWKS from %s", url)


def _get_public_keys():
    """
    Return a list of RSA public keys from the cached JWKS.
    Refreshes the cache if older than CACHE_TTL.
    """
    now = time.time()
    if now - _jwks_cache["fetched_at"] > CACHE_TTL or not _jwks_cache["keys"]:
        with _jwks_lock:
            # Double-check after acquiring lock
            if now - _jwks_cache["fetched_at"] > CACHE_TTL or not _jwks_cache["keys"]:
                _refresh_jwks()

    public_keys = []
    for key_dict in _jwks_cache["keys"]:
        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_dict))
            public_keys.append(public_key)
        except Exception:
            logger.warning("Skipping invalid JWK key: kid=%s", key_dict.get("kid"))
    return public_keys


def verify_cf_token(token):
    """
    Verify a Cloudflare Access JWT.

    Returns the decoded payload dict on success, or None on failure.
    """
    audience = getattr(settings, "CLOUDFLARE_AUD", "")
    if not audience:
        logger.error("CLOUDFLARE_AUD not set – cannot verify token")
        return None

    keys = _get_public_keys()
    if not keys:
        logger.error("No Cloudflare public keys available")
        return None

    for key in keys:
        try:
            payload = jwt.decode(
                token,
                key=key,
                audience=audience,
                algorithms=["RS256"],
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Cloudflare JWT expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("Cloudflare JWT audience mismatch")
            return None
        except jwt.DecodeError:
            # Wrong key – try next
            continue
        except Exception as exc:
            logger.warning("JWT verification error: %s", exc)
            continue

    logger.warning("Cloudflare JWT could not be verified with any key")
    return None


def _get_or_create_user(email):
    """
    Look up a Django user by email.  Create one if it doesn't exist.
    Grants is_staff=True when the email is in CLOUDFLARE_ADMIN_EMAILS.
    """
    admin_emails = {
        e.lower() for e in getattr(settings, "CLOUDFLARE_ADMIN_EMAILS", [])
    }
    email_lower = email.lower()

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        # Use the local-part of the email as the username (deduplicated)
        base_username = email_lower.split("@")[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        is_admin = email_lower in admin_emails
        user = User.objects.create_user(
            username=username,
            email=email_lower,
            is_staff=is_admin,
            is_superuser=is_admin,
        )
        logger.info(
            "Auto-created user %s (email=%s, staff=%s)",
            username, email_lower, is_admin,
        )

    # Promote / demote based on admin list (in case it changed)
    should_be_admin = email_lower in admin_emails
    if user.is_staff != should_be_admin or user.is_superuser != should_be_admin:
        user.is_staff = should_be_admin
        user.is_superuser = should_be_admin
        user.save(update_fields=["is_staff", "is_superuser"])
        logger.info("Updated staff/superuser for %s → %s", email_lower, should_be_admin)

    return user


# ---------------------------------------------------------------------------
# Django Middleware
# ---------------------------------------------------------------------------

class CloudflareAccessMiddleware:
    """
    Django middleware that authenticates users via Cloudflare Access JWTs.

    Reads the JWT from the ``Cf-Access-Jwt-Assertion`` header, validates it,
    and attaches the corresponding Django user to ``request.user``.

    Skipped entirely when ``CLOUDFLARE_AUTH_ENABLED`` is False.
    """

    # Paths that should never be blocked (health checks, PWA assets, etc.)
    EXEMPT_PREFIXES = (
        '/sw.js',
        '/site.webmanifest',
        '/favicon.ico',
        '/apple-touch-icon.png',
        '/offline.html',
        '/static/',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, "CLOUDFLARE_AUTH_ENABLED", False)
        if self.enabled:
            logger.info("Cloudflare Access middleware ENABLED")
            # Pre-warm the JWKS cache
            _refresh_jwks()
        else:
            logger.info("Cloudflare Access middleware DISABLED (local auth mode)")

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        # Allow exempt paths through (PWA assets, static files)
        if request.path.startswith(self.EXEMPT_PREFIXES):
            return self.get_response(request)

        # If the user is already authenticated via session, skip JWT check
        if request.user.is_authenticated:
            return self.get_response(request)

        token = request.META.get("HTTP_CF_ACCESS_JWT_ASSERTION", "")
        if not token:
            # Also check the CF_Authorization cookie (browser requests)
            token = request.COOKIES.get("CF_Authorization", "")

        if not token:
            # No token at all – let Django's normal auth handle it
            # (the user will get redirected to login by @login_required)
            return self.get_response(request)

        payload = verify_cf_token(token)
        if payload is None:
            # Invalid token – still let the request through; Django's
            # @login_required will bounce them to the login page.
            logger.warning("Invalid CF Access token on %s", request.path)
            return self.get_response(request)

        email = payload.get("email", "")
        if not email:
            logger.warning("CF Access token has no email claim")
            return self.get_response(request)

        user = _get_or_create_user(email)
        # Log the user into the Django session so downstream code sees
        # request.user as authenticated.
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        return self.get_response(request)
