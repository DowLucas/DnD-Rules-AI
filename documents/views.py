from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
import os
import numpy as np
import faiss
import json
from typing import List, Dict, Any
from django.db.models import Q
from django.db import transaction

from .models import Document, DocumentChunk
from .serializers import (
    DocumentSerializer, 
    DocumentListSerializer,
    DocumentSearchResultSerializer,
    DocumentDetailSerializer,
    ChunkSerializer
)
from .utils import (
    extract_text, 
    chunk_text, 
    create_embeddings, 
    create_faiss_index, 
    search_faiss_index,
    get_embedding_model,
    search_documents
)

# Custom permission class that allows vector store endpoints without authentication
class VectorStorePermission(permissions.BasePermission):
    """
    Custom permission to allow vector store endpoints without authentication
    """
    def has_permission(self, request, view):
        # Check if the URL path contains vector_store
        path = request.path
        if 'vector_store' in path:
            return True
        # For all other actions, require authentication
        return request.user and request.user.is_authenticated

class DocumentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing documents"""
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [VectorStorePermission]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DocumentDetailSerializer
        return DocumentSerializer
    
    # Override to disable authentication for specific actions
    def get_authenticators(self):
        """
        Override to disable authentication for vector store endpoints
        Safe to use during initialization since we're checking the request path
        """
        if hasattr(self, 'request') and self.request:
            path = self.request.path
            if 'vector_store' in path:
                return []  # Return empty list to disable authentication for vector store endpoints
        return super().get_authenticators()
    
    def perform_create(self, serializer):
        """Create a new document"""
        serializer.save()
    
    @action(detail=True, methods=['get'])
    def chunks(self, request, pk=None):
        """Get all chunks for a specific document"""
        document = self.get_object()
        chunks = document.chunks.all()
        serializer = ChunkSerializer(chunks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search documents based on query"""
        query = request.query_params.get('q', '')
        if not query:
            return Response(
                {"detail": "Query parameter 'q' is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Only search completed documents
        results = search_documents(
            query, 
            document_filter=Q(status=Document.Status.COMPLETE)
        )
        
        serializer = DocumentSearchResultSerializer(results, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def retry_processing(self, request, pk=None):
        """Retry processing a failed document"""
        document = self.get_object()
        
        if document.status != Document.Status.FAILED:
            return Response(
                {"detail": "Only failed documents can be retried"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Clear existing chunks
            document.chunks.all().delete()
            # Reset status to pending
            document.status = Document.Status.PENDING
            document.save()
        
        # Processing will be handled by a background task
        
        return Response({"detail": "Document processing restarted"})
        
    @action(detail=False, methods=['get'])
    def vector_store(self, request):
        """Get information about the OpenAI vector store"""
        try:
            from .services import DocumentService
            vector_store_info = DocumentService.list_vector_store_contents()
            return Response(vector_store_info)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @action(detail=False, methods=['get'])
    def vector_store_files(self, request):
        """Get detailed information about files in the OpenAI vector store"""
        try:
            from .services import DocumentService
            # Get basic vector store info
            vector_store_info = DocumentService.list_vector_store_contents()
            
            # If there was an error, return it
            if "error" in vector_store_info:
                return Response(vector_store_info)
                
            # Transform the response to focus on files with more details
            file_list = []
            for file in vector_store_info.get('files', []):
                file_details = {
                    'id': file.get('id'),
                    'file_id': file.get('file_id'),
                    'filename': file.get('filename', 'Unknown'),
                    'status': file.get('status'),
                    'created_at': file.get('created_at'),
                    # Include any other fields you want to expose
                }
                
                # Add linked document information if available
                try:
                    file_id = file.get('file_id')
                    if file_id:
                        document = Document.objects.filter(openai_file_id=file_id).first()
                        if document:
                            file_details['document'] = {
                                'id': str(document.id),
                                'title': document.title,
                                'description': document.description,
                                'created_at': document.created_at,
                                'updated_at': document.updated_at,
                                'status': document.status,
                            }
                except Exception as doc_error:
                    file_details['document_error'] = str(doc_error)
                
                file_list.append(file_details)
            
            # Return the formatted file list    
            return Response({
                'vector_store_id': vector_store_info.get('id'),
                'vector_store_name': vector_store_info.get('name'),
                'file_count': len(file_list),
                'files': file_list
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @action(detail=False, methods=['post'])
    def vector_store_search(self, request):
        """Search the OpenAI vector store directly using the vector search API"""
        query = request.data.get('query')
        filters = request.data.get('filters')
        max_results = request.data.get('max_results', 10)
        rewrite_query = request.data.get('rewrite_query', False)
        
        if not query:
            return Response(
                {"error": "Query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .services import DocumentService
            search_results = DocumentService.search_vector_store(
                query=query,
                filters=filters,
                max_results=max_results,
                rewrite_query=rewrite_query
            )
            
            return Response(search_results)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
