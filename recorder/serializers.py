from rest_framework import serializers
from .models import RecordingSession, Transcription, Campaign, NPC

class TranscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcription
        fields = ['id', 'session', 'created_at', 'text', 'chunk_number', 'language_code', 
                  'language_probability', 'words_json', 'generated_insight_text', 'full_text']
        read_only_fields = ['id', 'session', 'created_at', 'full_text']

class RecordingSessionSerializer(serializers.ModelSerializer):
    transcriptions = TranscriptionSerializer(many=True, read_only=True)
    session_number = serializers.SerializerMethodField()
    
    class Meta:
        model = RecordingSession
        fields = ['id', 'campaign', 'session_number', 'created_at', 'latest_insight_text', 
                  'latest_insight_timestamp', 'is_active', 'transcriptions']
        read_only_fields = ['id', 'campaign', 'created_at', 'latest_insight_timestamp', 'session_number']

    def get_session_number(self, obj):
        try:
            if obj.campaign:
                session_ids = list(obj.campaign.sessions.order_by('created_at').values_list('id', flat=True))
                try:
                    return session_ids.index(obj.id) + 1
                except ValueError:
                    return None
            return None
        except Exception:
            return None

class CampaignSerializer(serializers.ModelSerializer):
    sessions = RecordingSessionSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    session_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = ['id', 'user', 'name', 'description', 'created_at', 'updated_at', 
                 'session_count', 'document_count', 'sessions']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 
                           'session_count', 'document_count', 'sessions']

    def get_session_count(self, obj):
        return obj.sessions.count()
        
    def get_document_count(self, obj):
        return obj.documents.count()

class CampaignListSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    session_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = ['id', 'user', 'name', 'description', 'created_at', 'updated_at', 
                 'session_count', 'document_count']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 
                           'session_count', 'document_count']

    def get_session_count(self, obj):
        return obj.sessions.count()
        
    def get_document_count(self, obj):
        return obj.documents.count()

class NPCSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = NPC
        fields = ['id', 'campaign', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'campaign'] 