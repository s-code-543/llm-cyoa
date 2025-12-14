"""
URL configuration for game app.
"""
from django.urls import path
from . import views
from .models_views import list_models
from .test_views import test_endpoint

urlpatterns = [
    path('chat/completions', views.chat_completions, name='chat_completions'),
    path('models', list_models, name='list_models'),
    path('test', test_endpoint, name='test_endpoint'),
]
