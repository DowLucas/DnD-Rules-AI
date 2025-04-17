from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'recorder'

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'sessions', views.RecordingSessionViewSet)
router.register(r'transcriptions', views.TranscriptionViewSet)

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('api/', include(router.urls)),
]
    
# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 