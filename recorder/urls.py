from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import RegisterView, LoginView, LogoutView, UserDetailsView
# Remove this import as we're not using it anymore
# from documents.views import DocumentViewSet
from django.conf import settings
from django.conf.urls.static import static
from .views import spotify_token, spotify_refresh

app_name = 'recorder'

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'sessions', views.RecordingSessionViewSet)
router.register(r'transcriptions', views.TranscriptionViewSet)
# Remove the documents registration to avoid URL conflicts
# router.register(r'documents', DocumentViewSet)

# Authentication URLs
auth_urls = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/user/', UserDetailsView.as_view(), name='user-details'),
]

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
    path('', include(auth_urls)),
    
    # Spotify API endpoints
    path('spotify/token', spotify_token, name='spotify_token'),
    path('spotify/refresh', spotify_refresh, name='spotify_refresh'),
]
    
# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Serve media files during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 