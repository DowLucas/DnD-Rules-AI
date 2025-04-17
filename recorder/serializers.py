from rest_framework import serializers
from .models import RecordingSession, Transcription

class TranscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcription
        fields = ['id', 'created_at', 'text', 'chunk_number', 'language_code', 
                  'language_probability', 'words_json', 'generated_insight_text', 'full_text']
        read_only_fields = ['id', 'created_at']

class RecordingSessionSerializer(serializers.ModelSerializer):
    transcriptions = TranscriptionSerializer(many=True, read_only=True)
    
    class Meta:
        model = RecordingSession
        fields = ['id', 'name', 'created_at', 'latest_insight_text', 
                  'latest_insight_timestamp', 'is_active', 'transcriptions']
        read_only_fields = ['id', 'created_at', 'latest_insight_timestamp'] 