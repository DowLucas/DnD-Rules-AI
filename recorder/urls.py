from django.urls import path
from . import views

app_name = 'recorder'

urlpatterns = [
    path('', views.index, name='index'),
    path('toggle-recording/', views.toggle_recording, name='toggle_recording'),
    path('get-latest-transcriptions/', views.get_latest_transcriptions, name='get_latest_transcriptions'),
    path('create-session/', views.create_session, name='create_session'),
] 