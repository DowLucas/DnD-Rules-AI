from rest_framework import serializers
from .models import Document, DocumentChunk

class ChunkSerializer(serializers.ModelSerializer):
    """Serializer for document chunks"""
    
    class Meta:
        model = DocumentChunk
        fields = ['id', 'chunk_index', 'text', 'page_number']
        read_only_fields = ['id']

class DocumentSerializer(serializers.ModelSerializer):
    """Basic serializer for documents"""
    campaign_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'file_type', 'campaign', 'campaign_name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'file_type', 'status', 'created_at', 'updated_at', 'campaign_name']
    
    def get_campaign_name(self, obj):
        return obj.campaign.name if obj.campaign else None

class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for listing documents"""
    campaign_name = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = ['id', 'title', 'file_type', 'file_size', 'campaign', 'campaign_name', 'status', 'created_at', 'updated_at', 'chunk_count']
        read_only_fields = ['id', 'file_type', 'file_size', 'status', 'created_at', 'updated_at', 'campaign_name', 'chunk_count']
    
    def get_campaign_name(self, obj):
        return obj.campaign.name if obj.campaign else None
    
    def get_chunk_count(self, obj):
        return obj.chunks.count()

class DocumentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for documents including chunks"""
    chunks = ChunkSerializer(many=True, read_only=True)
    campaign_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = [
            'id', 'title', 'description', 'file', 'file_type', 
            'file_size', 'campaign', 'campaign_name', 'status', 'created_at', 'updated_at', 'chunks'
        ]
        read_only_fields = [
            'id', 'file_type', 'file_size', 'status', 
            'created_at', 'updated_at', 'chunks', 'campaign_name'
        ]
    
    def get_campaign_name(self, obj):
        return obj.campaign.name if obj.campaign else None

class DocumentSearchResultSerializer(serializers.Serializer):
    """Serializer for document search results"""
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    campaign_id = serializers.UUIDField(allow_null=True)
    campaign_name = serializers.CharField(allow_null=True)
    chunk_id = serializers.UUIDField()
    chunk_text = serializers.CharField()
    page_number = serializers.IntegerField(allow_null=True)
    similarity_score = serializers.FloatField() 