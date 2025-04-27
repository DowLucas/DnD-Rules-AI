from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
import os
import logging
import json

from .models import Document, DocumentChunk
from recorder.models import Campaign
from .serializers import DocumentSerializer, DocumentDetailSerializer, DocumentSearchResultSerializer
from .services import DocumentService
from .exceptions import DocumentProcessingError, DocumentNotFoundException
from .vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

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
        # Get the file, title, description from the request
        file = self.request.FILES.get('file')
        title = self.request.data.get('title')
        description = self.request.data.get('description', '')
        campaign_id = self.request.data.get('campaign')
        
        # If we don't have a file (for example in a test), fall back to normal behavior
        if not file:
            return serializer.save(uploaded_by=self.request.user)
        
        campaign = None
        if campaign_id:
            try:
                campaign = Campaign.objects.get(id=campaign_id)
                # Ensure the user has access to this campaign
                if campaign.user != self.request.user:
                    raise PermissionError("You do not have permission to add documents to this campaign")
            except Campaign.DoesNotExist:
                pass
        
        try:
            # Use upload_document instead of process_document
            document = DocumentService.upload_document(
                file=file,
                title=title,
                description=description,
                user=self.request.user,
                campaign=campaign
            )
            # Update the serializer instance to reference the created document
            if hasattr(serializer, 'instance'):
                serializer.instance = document
            return document
        except Exception as e:
            # Log the error
            logger.error(f"Error uploading document: {str(e)}")
            # Let the exception propagate to give proper error response
            raise
    
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
        """Search for documents using semantic search with ChromaDB"""
        query = request.data.get('query')
        campaign_id = request.data.get('campaign_id')
        limit = int(request.data.get('limit', 15))
        
        if not query:
            return Response(
                {"error": "Query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Perform search using ChromaDB
            results = DocumentService.search_documents(
                query_text=query,
                campaign_id=campaign_id,
                limit=limit
            )
            
            return Response({'results': results})
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

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_document(request):
    """
    Upload, process, and index a document.
    
    This endpoint handles the complete process of:
    1. Uploading the document file
    2. Processing and chunking the document text
    3. Adding the chunks to the ChromaDB vector store
    
    The document will be associated with the current user and optionally a campaign.
    
    Expected format: multipart/form-data with:
    - file: The document file
    - title: Document title
    - description: (optional) Document description
    - campaign_id: (optional) Campaign ID to associate with
    """
    # Get required fields
    file = request.FILES.get('file')
    title = request.data.get('title')
    description = request.data.get('description', '')
    campaign_id = request.data.get('campaign_id')
    
    if not file:
        return Response({'error': 'Document file is required.'}, 
                      status=status.HTTP_400_BAD_REQUEST)
    
    if not title:
        return Response({'error': 'Document title is required.'}, 
                      status=status.HTTP_400_BAD_REQUEST)
    
    # Get campaign if ID provided
    campaign = None
    if campaign_id:
        from recorder.models import Campaign
        try:
            campaign = Campaign.objects.get(id=campaign_id, user=request.user)
        except Campaign.DoesNotExist:
            return Response({'error': f'Campaign with ID {campaign_id} not found.'}, 
                          status=status.HTTP_404_NOT_FOUND)
    
    try:
        # Upload and process document
        document = DocumentService.upload_document(
            file=file,
            title=title,
            description=description,
            user=request.user,
            campaign=campaign
        )
        
        # Return the document details
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        return Response({'error': f'Failed to process document: {str(e)}'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_documents(request):
    """
    List all documents for the authenticated user.
    
    Optional filtering by campaign ID using query parameter ?campaign_id=X
    """
    campaign_id = request.query_params.get('campaign_id')
    
    # Filter documents
    documents = Document.objects.filter(uploaded_by=request.user)
    if campaign_id:
        documents = documents.filter(campaign_id=campaign_id)
    
    # Serialize and return
    serializer = DocumentSerializer(documents, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_document(request, document_id):
    """
    Get details of a specific document including its chunks.
    """
    try:
        # Verify the document belongs to the user
        document = Document.objects.get(id=document_id, uploaded_by=request.user)
        
        # Get document details
        document_details = DocumentService.get_document_details(document_id)
        if document_details:
            return Response(document_details)
        else:
            return Response({'error': 'Failed to retrieve document details.'}, 
                           status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Document.DoesNotExist:
        return Response({'error': f'Document with ID {document_id} not found.'}, 
                       status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error getting document details: {str(e)}")
        return Response({'error': f'Failed to retrieve document: {str(e)}'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_document(request, document_id):
    """
    Delete a document and its chunks from the database and vector store.
    """
    try:
        # Verify the document belongs to the user
        document = Document.objects.get(id=document_id, uploaded_by=request.user)
        
        # Delete the document
        success = DocumentService.delete_document(document_id)
        if success:
            return Response({'message': f'Document {document_id} deleted successfully.'})
        else:
            return Response({'error': 'Failed to delete document.'}, 
                           status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Document.DoesNotExist:
        return Response({'error': f'Document with ID {document_id} not found.'}, 
                       status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        return Response({'error': f'Failed to delete document: {str(e)}'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def search_documents(request):
    """
    Search for documents based on a query.
    
    Expected POST data:
    {
        "query": "What are the rules for advantage?",
        "campaign_id": "optional-campaign-id",
        "limit": 5
    }
    """
    # Get search parameters
    query = request.data.get('query')
    campaign_id = request.data.get('campaign_id')
    limit = int(request.data.get('limit', 15))
    
    if not query:
        return Response({'error': 'Search query is required.'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Perform search
    results = DocumentService.search_documents(
        query_text=query,
        campaign_id=campaign_id,
        limit=limit
    )
    
    return Response({'results': results})

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reindex_documents(request):
    """
    Reindex all documents in the vector store.
    This is an admin-only operation.
    """
    # Check if user is admin or superuser
    if not request.user.is_staff and not request.user.is_superuser:
        return Response({'error': 'Only administrators can reindex documents.'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Perform reindexing
    success = DocumentService.reindex_all_documents()
    if success:
        return Response({'message': 'Successfully reindexed all documents.'})
    else:
        return Response({'error': 'Failed to reindex documents.'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR) 