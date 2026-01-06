"""
URL configuration for cyoa_server project.
"""
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from game.admin_views import login_view

urlpatterns = [
    # Root redirect to admin
    path('', RedirectView.as_view(url='/admin/dashboard/', permanent=False)),
    
    # API endpoints
    path('v1/', include('game.urls')),
    
    # Admin interface
    path('admin/login/', login_view, name='login'),
    path('admin/logout/', auth_views.LogoutView.as_view(next_page='/admin/login/'), name='logout'),
    path('admin/', include(('game.admin_urls', 'admin'), namespace='admin')),
]
