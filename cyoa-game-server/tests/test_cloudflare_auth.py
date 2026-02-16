"""
Tests for Cloudflare Access authentication middleware.

Tests cover:
- Middleware disabled (no-op behaviour)
- JWT validation and user auto-creation
- Admin email promotion/demotion
- Missing/invalid tokens
- JWKS caching
"""
import json
import time
from unittest.mock import patch, MagicMock

import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from django.test import Client, RequestFactory, override_settings
from django.contrib.auth.models import User, AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.middleware import AuthenticationMiddleware

from game.cloudflare_auth import (
    CloudflareAccessMiddleware,
    verify_cf_token,
    _get_or_create_user,
    _jwks_cache,
    _refresh_jwks,
    _get_public_keys,
    CACHE_TTL,
)


# =============================================================================
# Helpers – generate a real RSA key pair for JWT signing
# =============================================================================

def _generate_rsa_keypair():
    """Generate a fresh RSA key pair (private + public) for tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    return private_key


def _make_jwk(private_key):
    """Export the public key as a JWK dict (matching Cloudflare's format)."""
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Use PyJWT to convert to JWK
    jwk_dict = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = "test-key-1"
    jwk_dict["alg"] = "RS256"
    jwk_dict["use"] = "sig"
    return jwk_dict


def _sign_jwt(private_key, payload, headers=None):
    """Sign a JWT payload with the given RSA private key."""
    return pyjwt.encode(payload, private_key, algorithm="RS256", headers=headers)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def rsa_keypair():
    """Fresh RSA key pair for each test."""
    return _generate_rsa_keypair()


@pytest.fixture
def jwk(rsa_keypair):
    return _make_jwk(rsa_keypair)


@pytest.fixture
def cf_settings():
    """Default Cloudflare settings for tests."""
    return {
        "CLOUDFLARE_AUTH_ENABLED": True,
        "CLOUDFLARE_TEAM_DOMAIN": "https://testteam.cloudflareaccess.com",
        "CLOUDFLARE_AUD": "test-aud-tag-12345",
        "CLOUDFLARE_ADMIN_EMAILS": ["admin@example.com"],
    }


@pytest.fixture
def valid_token(rsa_keypair, cf_settings):
    """A valid signed JWT for player@example.com."""
    now = int(time.time())
    payload = {
        "aud": [cf_settings["CLOUDFLARE_AUD"]],
        "email": "player@example.com",
        "iss": cf_settings["CLOUDFLARE_TEAM_DOMAIN"],
        "iat": now,
        "exp": now + 3600,
        "sub": "test-subject-id",
        "type": "app",
    }
    return _sign_jwt(rsa_keypair, payload)


@pytest.fixture
def admin_token(rsa_keypair, cf_settings):
    """A valid signed JWT for admin@example.com."""
    now = int(time.time())
    payload = {
        "aud": [cf_settings["CLOUDFLARE_AUD"]],
        "email": "admin@example.com",
        "iss": cf_settings["CLOUDFLARE_TEAM_DOMAIN"],
        "iat": now,
        "exp": now + 3600,
        "sub": "admin-subject-id",
        "type": "app",
    }
    return _sign_jwt(rsa_keypair, payload)


@pytest.fixture
def expired_token(rsa_keypair, cf_settings):
    """An expired JWT."""
    now = int(time.time())
    payload = {
        "aud": [cf_settings["CLOUDFLARE_AUD"]],
        "email": "player@example.com",
        "iss": cf_settings["CLOUDFLARE_TEAM_DOMAIN"],
        "iat": now - 7200,
        "exp": now - 3600,
        "sub": "test-subject-id",
    }
    return _sign_jwt(rsa_keypair, payload)


@pytest.fixture(autouse=True)
def reset_jwks_cache():
    """Reset the module-level JWKS cache before each test."""
    _jwks_cache["keys"] = []
    _jwks_cache["fetched_at"] = 0
    yield
    _jwks_cache["keys"] = []
    _jwks_cache["fetched_at"] = 0


def _patch_jwks(jwk_dict):
    """Patch _get_public_keys to return keys from our test JWK."""
    public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk_dict))
    return patch("game.cloudflare_auth._get_public_keys", return_value=[public_key])


# =============================================================================
# Tests: verify_cf_token
# =============================================================================

class TestVerifyCfToken:
    """Unit tests for the JWT verification function."""

    @override_settings(CLOUDFLARE_AUD="test-aud-tag-12345")
    def test_valid_token(self, rsa_keypair, jwk, valid_token):
        with _patch_jwks(jwk):
            payload = verify_cf_token(valid_token)
        assert payload is not None
        assert payload["email"] == "player@example.com"

    @override_settings(CLOUDFLARE_AUD="test-aud-tag-12345")
    def test_expired_token(self, rsa_keypair, jwk, expired_token):
        with _patch_jwks(jwk):
            payload = verify_cf_token(expired_token)
        assert payload is None

    @override_settings(CLOUDFLARE_AUD="wrong-audience")
    def test_wrong_audience(self, rsa_keypair, jwk, valid_token):
        with _patch_jwks(jwk):
            payload = verify_cf_token(valid_token)
        assert payload is None

    @override_settings(CLOUDFLARE_AUD="test-aud-tag-12345")
    def test_tampered_token(self, jwk):
        with _patch_jwks(jwk):
            payload = verify_cf_token("not.a.real.jwt")
        assert payload is None

    @override_settings(CLOUDFLARE_AUD="")
    def test_missing_aud_setting(self, valid_token):
        payload = verify_cf_token(valid_token)
        assert payload is None

    @override_settings(CLOUDFLARE_AUD="test-aud-tag-12345")
    def test_no_public_keys(self, valid_token):
        with patch("game.cloudflare_auth._get_public_keys", return_value=[]):
            payload = verify_cf_token(valid_token)
        assert payload is None

    @override_settings(CLOUDFLARE_AUD="test-aud-tag-12345")
    def test_wrong_key(self, jwk, valid_token):
        """Token signed with one key, validator has a different key."""
        other_keypair = _generate_rsa_keypair()
        other_jwk = _make_jwk(other_keypair)
        with _patch_jwks(other_jwk):
            payload = verify_cf_token(valid_token)
        assert payload is None


# =============================================================================
# Tests: _get_or_create_user
# =============================================================================

class TestGetOrCreateUser:
    """Unit tests for user auto-creation and admin promotion."""

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=["admin@example.com"])
    def test_creates_new_user(self, db):
        user = _get_or_create_user("newuser@example.com")
        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert not user.is_staff
        assert not user.is_superuser

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=["admin@example.com"])
    def test_creates_admin_user(self, db):
        user = _get_or_create_user("admin@example.com")
        assert user.email == "admin@example.com"
        assert user.is_staff
        assert user.is_superuser

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=["admin@example.com"])
    def test_returns_existing_user(self, db):
        existing = User.objects.create_user("existing", email="existing@test.com")
        user = _get_or_create_user("existing@test.com")
        assert user.pk == existing.pk

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=["player@example.com"])
    def test_promotes_existing_user_to_admin(self, db):
        user = User.objects.create_user("player", email="player@example.com")
        assert not user.is_staff
        updated = _get_or_create_user("player@example.com")
        assert updated.pk == user.pk
        assert updated.is_staff
        assert updated.is_superuser

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=[])
    def test_demotes_user_when_removed_from_admin_list(self, db):
        user = User.objects.create_user(
            "wasadmin", email="wasadmin@example.com",
            is_staff=True, is_superuser=True,
        )
        updated = _get_or_create_user("wasadmin@example.com")
        assert not updated.is_staff
        assert not updated.is_superuser

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=[])
    def test_deduplicates_username(self, db):
        User.objects.create_user("duplicate", email="other@test.com")
        user = _get_or_create_user("duplicate@example.com")
        assert user.username == "duplicate1"

    @override_settings(CLOUDFLARE_ADMIN_EMAILS=["ADMIN@Example.COM"])
    def test_case_insensitive_admin_email(self, db):
        user = _get_or_create_user("admin@example.com")
        assert user.is_staff


# =============================================================================
# Tests: CloudflareAccessMiddleware (integration)
# =============================================================================

class TestMiddlewareDisabled:
    """When CLOUDFLARE_AUTH_ENABLED is False the middleware is a no-op."""

    @override_settings(CLOUDFLARE_AUTH_ENABLED=False)
    def test_requests_pass_through(self, db):
        """Normal unauthenticated request is not blocked."""
        client = Client()
        resp = client.get("/admin/login/")
        assert resp.status_code == 200

    @override_settings(CLOUDFLARE_AUTH_ENABLED=False)
    def test_login_required_still_works(self, db):
        """@login_required still redirects unauthenticated users."""
        client = Client()
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url


class TestMiddlewareEnabled:
    """When CLOUDFLARE_AUTH_ENABLED is True, JWT authentication is active."""

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=["admin@example.com"],
    )
    def test_valid_token_authenticates_user(self, db, rsa_keypair, jwk, valid_token):
        """A valid CF JWT in the header creates + authenticates a user."""
        client = Client()
        with _patch_jwks(jwk), \
             patch("game.cloudflare_auth._refresh_jwks"):
            resp = client.get("/", HTTP_CF_ACCESS_JWT_ASSERTION=valid_token)
        assert resp.status_code == 200
        assert User.objects.filter(email="player@example.com").exists()

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=["admin@example.com"],
    )
    def test_admin_token_creates_staff_user(self, db, rsa_keypair, jwk, admin_token):
        """A token with an admin email creates a staff user."""
        client = Client()
        with _patch_jwks(jwk), \
             patch("game.cloudflare_auth._refresh_jwks"):
            resp = client.get("/", HTTP_CF_ACCESS_JWT_ASSERTION=admin_token)
        assert resp.status_code == 200
        user = User.objects.get(email="admin@example.com")
        assert user.is_staff
        assert user.is_superuser

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=[],
    )
    def test_no_token_falls_through_to_login_required(self, db):
        """Without a CF header, @login_required redirects to login."""
        client = Client()
        with patch("game.cloudflare_auth._refresh_jwks"):
            resp = client.get("/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=[],
    )
    def test_invalid_token_falls_through(self, db):
        """A garbage token doesn't crash; falls through to login."""
        client = Client()
        with patch("game.cloudflare_auth._refresh_jwks"):
            resp = client.get("/", HTTP_CF_ACCESS_JWT_ASSERTION="garbage.token.here")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=[],
    )
    def test_expired_token_falls_through(self, db, rsa_keypair, jwk, expired_token):
        """An expired JWT doesn't authenticate; triggers login redirect."""
        client = Client()
        with _patch_jwks(jwk), \
             patch("game.cloudflare_auth._refresh_jwks"):
            resp = client.get("/", HTTP_CF_ACCESS_JWT_ASSERTION=expired_token)
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    @override_settings(
        CLOUDFLARE_AUTH_ENABLED=True,
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
        CLOUDFLARE_ADMIN_EMAILS=[],
    )
    def test_already_authenticated_skips_jwt(self, db, user, auth_client):
        """If user is already in session, middleware skips JWT check."""
        with patch("game.cloudflare_auth._refresh_jwks"):
            resp = auth_client.get("/")
        assert resp.status_code == 200


# =============================================================================
# Tests: JWKS Cache
# =============================================================================

class TestJwksCache:
    """Tests for the JWKS key-fetching and caching logic."""

    @override_settings(
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com"
    )
    def test_refresh_jwks_populates_cache(self, jwk):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [jwk]}
        mock_resp.raise_for_status = MagicMock()

        with patch("game.cloudflare_auth.requests.get", return_value=mock_resp):
            _refresh_jwks()

        assert len(_jwks_cache["keys"]) == 1
        assert _jwks_cache["fetched_at"] > 0

    @override_settings(
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com"
    )
    def test_refresh_jwks_survives_network_error(self):
        with patch("game.cloudflare_auth.requests.get", side_effect=Exception("boom")):
            _refresh_jwks()  # Should not raise
        assert _jwks_cache["keys"] == []

    @override_settings(
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
    )
    def test_get_public_keys_calls_refresh_when_stale(self, jwk):
        _jwks_cache["fetched_at"] = time.time() - CACHE_TTL - 1

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [jwk]}
        mock_resp.raise_for_status = MagicMock()

        with patch("game.cloudflare_auth.requests.get", return_value=mock_resp) as mock_get:
            keys = _get_public_keys()

        mock_get.assert_called_once()
        assert len(keys) == 1

    @override_settings(
        CLOUDFLARE_TEAM_DOMAIN="https://testteam.cloudflareaccess.com",
        CLOUDFLARE_AUD="test-aud-tag-12345",
    )
    def test_get_public_keys_uses_cache_when_fresh(self, jwk):
        _jwks_cache["keys"] = [jwk]
        _jwks_cache["fetched_at"] = time.time()

        with patch("game.cloudflare_auth.requests.get") as mock_get:
            keys = _get_public_keys()

        mock_get.assert_not_called()
        assert len(keys) == 1
