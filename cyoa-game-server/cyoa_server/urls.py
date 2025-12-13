"""
URL configuration for cyoa_server project.
"""
from django.urls import path, include

urlpatterns = [
    path('v1/', include('game.urls')),
]
