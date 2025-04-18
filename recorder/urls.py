from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import RegisterView, LoginView, LogoutView, UserDetailsView
from documents.views import DocumentViewSet
from django.conf import settings
from django.conf.urls.static import static

app_name = 'recorder'

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'sessions', views.RecordingSessionViewSet)
router.register(r'transcriptions', views.TranscriptionViewSet)
router.register(r'documents', DocumentViewSet)

# Authentication URLs
auth_urls = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/user/', UserDetailsView.as_view(), name='user-details'),
]

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('api/', include(router.urls)),
    path('api/', include(auth_urls)),
]
    
# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Serve media files during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 