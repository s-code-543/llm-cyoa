"""
URL configuration for cyoa_server project.
"""
from django.urls import path, include
from game import chat_views
from game import stt_views
from game import pwa_views, tts_views

urlpatterns = [
    # PWA root-level assets (must be above catch-all patterns)
    path('sw.js', pwa_views.service_worker, name='service_worker'),
    path('favicon.ico', pwa_views.favicon_ico, name='favicon_ico'),
    path('apple-touch-icon.png', pwa_views.apple_touch_icon, name='apple_touch_icon'),
    path('site.webmanifest', pwa_views.web_manifest, name='web_manifest'),
    path('offline.html', pwa_views.offline_page, name='offline_page'),

    # Home page
    path('', chat_views.home_page, name='home'),
    
    # Chat interface
    path('chat/', chat_views.chat_page, name='chat_page'),
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
    
    # Admin interface
    path('admin/', include(('game.admin_urls', 'app'), namespace='admin')),
]
