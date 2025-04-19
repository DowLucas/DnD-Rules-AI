from rest_framework import serializers
from .models import Document, DocumentChunk

class ChunkSerializer(serializers.ModelSerializer):
    """Serializer for document chunks"""
    
    class Meta:
        model = DocumentChunk
        fields = ['id', 'chunk_index', 'text', 'page_number']
        read_only_fields = ['id']

class DocumentSerializer(serializers.ModelSerializer):
    """Basic serializer for documents, used in the upload response."""
    campaign_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        # Add openai_file_id, remove file (as it's not needed in response)
        fields = ['id', 'title', 'openai_file_id', 'file_type', 'campaign', 'campaign_name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'openai_file_id', 'file_type', 'status', 'created_at', 'updated_at', 'campaign_name']
    
    def get_campaign_name(self, obj):
        return obj.campaign.name if obj.campaign else None

class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for listing documents. Keep local file info for now."""
    campaign_name = serializers.SerializerMethodField()
    # chunk_count = serializers.SerializerMethodField() # Remove chunk count as chunks are not local
    
    class Meta:
        model = Document
        # Add openai_file_id
        fields = ['id', 'title', 'openai_file_id', 'file_type', 'file_size', 'campaign', 'campaign_name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'openai_file_id', 'file_type', 'file_size', 'status', 'created_at', 'updated_at', 'campaign_name']
    
    def get_campaign_name(self, obj):
        return obj.campaign.name if obj.campaign else None
    
    # def get_chunk_count(self, obj):
    #     return obj.chunks.count() # Chunks no longer local

class DocumentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for documents including chunks. Remove chunks."""
    # chunks = ChunkSerializer(many=True, read_only=True) # Remove chunks
    campaign_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        # Add openai_file_id, remove file and chunks
        fields = [
            'id', 'title', 'description', 'openai_file_id',
            'file_type', 'file_size', 'campaign', 'campaign_name', 
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'openai_file_id', 'file_type', 'file_size', 'status', 
            'created_at', 'updated_at', 'campaign_name'
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