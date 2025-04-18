from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
import os

from .models import Document, DocumentChunk
from recorder.models import Campaign
from .serializers import DocumentSerializer, DocumentDetailSerializer, DocumentSearchResultSerializer
from .services import DocumentService
from .exceptions import DocumentProcessingError, DocumentNotFoundException


class DocumentViewSet(viewsets.ModelViewSet):
    """
    API endpoints for document management
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter documents to only show those belonging to the current user"""
        user = self.request.user
        
        # Get campaign_id from query params if provided
        campaign_id = self.request.query_params.get('campaign_id')
        
        queryset = Document.objects.filter(
            Q(uploaded_by=user) | Q(campaign__user=user)
        ).select_related('campaign')
        
        # Further filter by campaign if campaign_id is provided
        if campaign_id:
            queryset = queryset.filter(campaign_id=campaign_id)
            
        return queryset
    
    def perform_create(self, serializer):
        """Set the uploaded_by field to the current user when creating a document"""
        document = serializer.save(uploaded_by=self.request.user)
        
        # Process the document in background (this could be moved to a Celery task)
        try:
            DocumentService.process_document(document.id)
        except DocumentProcessingError as e:
            # Log the error but don't fail the request
            document.status = Document.Status.FAILED
            document.save()
    
    def retrieve(self, request, *args, **kwargs):
        """Return detailed information about a document"""
        document = self.get_object()
        
        try:
            document_details = DocumentService.get_document_details(document.id)
            serializer = DocumentDetailSerializer(document_details)
            return Response(serializer.data)
        except DocumentNotFoundException:
            return Response(
                {"error": "Document not found or not processed yet"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download the original document file"""
        document = self.get_object()
        file_path = document.file.path
        
        if os.path.exists(file_path):
            response = FileResponse(
                open(file_path, 'rb'),
                as_attachment=True,
                filename=os.path.basename(file_path)
            )
            return response
        else:
            return Response(
                {"error": "File not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search for documents using semantic search"""
        query = request.data.get('query')
        campaign_id = request.data.get('campaign_id')
        limit = request.data.get('limit', 5)
        
        if not query:
            return Response(
                {"error": "Query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Build document filter
            doc_filter = Q(status=Document.Status.COMPLETE)
            
            # Only include documents the user has access to
            user_filter = Q(uploaded_by=request.user) | Q(campaign__user=request.user)
            doc_filter &= user_filter
            
            # Filter by campaign if specified
            if campaign_id:
                campaign_filter = Q(campaign_id=campaign_id)
                doc_filter &= campaign_filter
            
            search_results = DocumentService.search_documents(
                query_text=query,
                document_filter=doc_filter,
                limit=limit
            )
            
            serializer = DocumentSearchResultSerializer(search_results, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def campaign_documents(self, request):
        """Get all documents for a specific campaign"""
        campaign_id = request.query_params.get('campaign_id')
        
        if not campaign_id:
            return Response(
                {"error": "campaign_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Verify the user has access to this campaign
        campaign = get_object_or_404(Campaign, id=campaign_id)
        if campaign.user != request.user:
            return Response(
                {"error": "You do not have permission to access this campaign"},
                status=status.HTTP_403_FORBIDDEN
            )
            
        documents = Document.objects.filter(campaign=campaign)
        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data) 