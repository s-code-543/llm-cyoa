"""Single-page app shell plus session, login and home APIs.

Two roles exist: players (any signed-in user) and admins (is_staff).
Admins are granted via the Cloudflare/Google sign-in mapping.
"""
import json
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .chat_api import body, error, player_api
from .models import ChatConversation, Configuration, GameSession

PLAY = 'play'
ADMIN = 'admin'


def permissions_for(user):
    if not user.is_authenticated:
        return []
    return [PLAY, ADMIN] if user.is_staff else [PLAY]


def require_permission(permission):
    """JSON API guard: 401 when signed out, 403 when the role is insufficient."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return error('unauthenticated', 'Please sign in again.', 401)
            if permission not in permissions_for(request.user):
                return error('forbidden', 'You do not have access to this.', 403)
            return view(request, *args, **kwargs)
        return never_cache(wrapped)
    return decorator


def session_payload(request):
    user = request.user
    return {
        'user': {
            'username': user.get_username(),
            'email': user.email,
            'display_name': user.email or user.get_username(),
        } if user.is_authenticated else None,
        'permissions': permissions_for(user),
        'csrf_token': get_token(request),
    }


@ensure_csrf_cookie
@never_cache
def spa(request, **_):
    """Serve the React shell for every client-side route; the API enforces access."""
    context = {'frontend_dev': settings.FRONTEND_DEV}
    if not settings.FRONTEND_DEV:
        manifest_path = settings.BASE_DIR / 'static' / 'frontend' / '.vite' / 'manifest.json'
        if not manifest_path.exists():
            return HttpResponse(
                '<!doctype html><title>Build unavailable</title><h1>The web app has not been built</h1>'
                '<p>Use the development Compose stack or build the production image.</p>',
                status=503,
            )
        entry = json.loads(manifest_path.read_text())['src/main.tsx']
        context['frontend_script'] = '/static/frontend/' + entry['file']
        context['frontend_styles'] = ['/static/frontend/' + css for css in entry.get('css', [])]
    return render(request, 'app/shell.html', context)


@ensure_csrf_cookie
@never_cache
@require_http_methods(['GET'])
def session(request):
    return JsonResponse(session_payload(request))


@never_cache
@require_http_methods(['POST'])
def login(request):
    try:
        data = body(request)
        username, password = data['username'], data['password']
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return error('invalid_request', 'Enter a username and password.', 400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return error('invalid_credentials', 'Invalid username or password.', 401)
    auth_login(request, user)
    return JsonResponse(session_payload(request))


@never_cache
@require_http_methods(['POST'])
def logout(request):
    auth_logout(request)
    return JsonResponse(session_payload(request))


@player_api
@require_http_methods(['GET'])
def home(request):
    recent = []
    conversations = ChatConversation.objects.filter(user=request.user).order_by('-updated_at')[:10]
    sessions = {
        item.session_id: item
        for item in GameSession.objects.filter(
            user=request.user, session_id__in=[c.conversation_id for c in conversations],
        )
    }
    for conversation in conversations:
        game = sessions.get(conversation.conversation_id)
        if game and not game.game_over:
            recent.append({
                'id': conversation.conversation_id,
                'title': conversation.title,
                'turn': game.turn_number,
                'max_turns': game.max_turns,
                'updated_at': conversation.updated_at.isoformat(),
            })
        if len(recent) >= 5:
            break
    configurations = Configuration.objects.filter(storyteller_model__isnull=False).select_related(
        'adventure_prompt', 'difficulty',
    )
    return JsonResponse({
        'recent_games': recent,
        'configurations': [{
            'id': config.pk,
            'name': config.name,
            'description': config.description,
            'prompt_name': config.adventure_prompt.name if config.adventure_prompt else None,
            'total_turns': config.total_turns,
            'difficulty': config.difficulty.name if config.difficulty else None,
        } for config in configurations],
    })
