from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'recorder'

urlpatterns = [
    path('', views.index, name='index'),
    path('toggle-recording/', views.toggle_recording, name='toggle_recording'),
    path('get-latest-transcriptions/', views.get_latest_transcriptions, name='get_latest_transcriptions'),
    path('create-session/', views.create_session, name='create_session'),
    path('get-latest-insight/', views.get_latest_insight, name='get_latest_insight'),
    path('force-insight/', views.force_insight, name='force_insight'),
]

# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 