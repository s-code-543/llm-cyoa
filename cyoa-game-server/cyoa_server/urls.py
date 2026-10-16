"""
URL configuration for cyoa_server project.
"""
from django.contrib import admin
from django.http import HttpResponsePermanentRedirect
from django.urls import path, re_path

from game import admin_api, admin_config_api as config_api, admin_providers_api as providers_api, app_api
from game import chat_views, chat_api, scene_images
from game import stt_views
from game import pwa_views, tts_views

LEGACY_ADMIN_PAGES = {
    'dashboard': '',
    'audit': 'audit',
    'prompts': 'prompts',
    'configurations': 'configurations',
    'providers': 'providers',
    'models': 'models',
    'difficulty': 'difficulty',
    'tts-settings': 'voice',
}


def legacy_admin_redirect(request, rest):
    section = rest.strip('/').split('/')[0]
    target = LEGACY_ADMIN_PAGES.get(section, '')
    return HttpResponsePermanentRedirect(f'/manage/{target}'.rstrip('/') or '/manage')


urlpatterns = [
    path('api/v1/session', app_api.session),
    path('api/v1/session/login', app_api.login),
    path('api/v1/session/logout', app_api.logout),
    path('api/v1/home', app_api.home),
    path('api/v1/admin/dashboard', admin_api.dashboard),
    path('api/v1/admin/audit', admin_api.audit_collection),
    path('api/v1/admin/audit/<int:log_id>', admin_api.audit_detail),
    path('api/v1/admin/prompts', admin_api.prompt_collection),
    path('api/v1/admin/prompts/<int:prompt_id>', admin_api.prompt_detail),
    path('api/v1/admin/prompts/<int:prompt_id>/versions', admin_api.prompt_new_version),
    path('api/v1/admin/prompts/<int:prompt_id>/save-to-disk', admin_api.prompt_save_to_disk),
    path('api/v1/admin/providers', providers_api.provider_collection),
    path('api/v1/admin/providers/test', providers_api.provider_test),
    path('api/v1/admin/providers/<int:provider_id>', providers_api.provider_detail),
    path('api/v1/admin/providers/<int:provider_id>/models', providers_api.provider_models),
    path('api/v1/admin/providers/<int:provider_id>/models/import', providers_api.provider_models_import),
    path('api/v1/admin/providers/<int:provider_id>/models/remove', providers_api.provider_models_remove),
    path('api/v1/admin/providers/<int:provider_id>/models/sync', providers_api.provider_models_sync),
    path('api/v1/admin/models', providers_api.model_collection),
    path('api/v1/admin/models/<int:model_id>', providers_api.model_detail),
    path('api/v1/admin/difficulty', providers_api.difficulty_collection),
    path('api/v1/admin/difficulty/<int:difficulty_id>', providers_api.difficulty_detail),
    path('api/v1/admin/tts', providers_api.tts_settings),
    path('api/v1/admin/configurations', config_api.config_collection),
    path('api/v1/admin/configurations/options', config_api.config_options),
    path('api/v1/admin/configurations/<int:config_id>', config_api.config_detail),
    # React app routes (client-side routing; the API enforces access)
    path('', app_api.spa, name='home'),
    path('login', app_api.spa, name='login_page'),
    path('chat', app_api.spa, name='chat_page'),
    path('chat/', app_api.spa),
    path('manage/', app_api.spa),
    path('manage/<path:rest>', app_api.spa),
    path('api/v1/chat/bootstrap', chat_api.bootstrap),
    path('api/v1/chat/conversations', chat_api.conversations),
    path('api/v1/chat/conversations/<str:conversation_id>', chat_api.detail),
    path('api/v1/chat/conversations/<str:conversation_id>/turns', chat_api.send),
    path('api/v1/chat/conversations/<str:conversation_id>/rollback', chat_api.rollback),
    # PWA root-level assets (must be above catch-all patterns)
    path('sw.js', pwa_views.service_worker, name='service_worker'),
    path('favicon.ico', pwa_views.favicon_ico, name='favicon_ico'),
    path('apple-touch-icon.png', pwa_views.apple_touch_icon, name='apple_touch_icon'),
    path('site.webmanifest', pwa_views.web_manifest, name='web_manifest'),
    path('offline.html', pwa_views.offline_page, name='offline_page'),

    
    path('api/v1/chat/images/<int:message_id>', scene_images.scene_image, name='scene_image'),
    path('chat/api/new', chat_views.chat_api_new_conversation, name='chat_api_new'),
    path('chat/api/send', chat_views.chat_api_send_message, name='chat_api_send'),
    path('chat/api/conversation/<str:conversation_id>', chat_views.chat_api_get_conversation, name='chat_api_get'),
    path('chat/api/conversations', chat_views.chat_api_list_conversations, name='chat_api_list'),
    path('chat/api/delete/<str:conversation_id>', chat_views.chat_api_delete_conversation, name='chat_api_delete'),
    path('chat/api/rollback', chat_views.chat_api_rollback_to_message, name='chat_api_rollback'),
    
    # STT (Speech-to-Text) API
    path('api/stt/upload', stt_views.stt_upload, name='stt_upload'),
    path('api/stt/transcribe', stt_views.stt_transcribe, name='stt_transcribe'),
    path('api/stt/recording/<str:recording_id>', stt_views.stt_recording_status, name='stt_recording_status'),
    path('api/stt/discard', stt_views.stt_discard, name='stt_discard'),
    
    # TTS (Text-to-Speech) API
    path('api/tts/generate', tts_views.tts_generate, name='tts_generate'),
    path('api/tts/audio/<str:audio_id>', tts_views.tts_audio, name='tts_audio'),
    path('api/tts/status/<str:audio_id>', tts_views.tts_status, name='tts_status'),
    
    # Django's built-in admin is kept for user and group management only.
    path('django-admin/', admin.site.urls),
    # Old bookmarks for the removed server-rendered admin pages.
    re_path(r'^admin/(?P<rest>.*)$', legacy_admin_redirect),
]
