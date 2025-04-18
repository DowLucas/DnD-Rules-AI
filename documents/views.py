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

class DocumentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing documents"""
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DocumentDetailSerializer
        return DocumentSerializer
    
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
