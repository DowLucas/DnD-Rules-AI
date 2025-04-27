from django.urls import path
from . import api

urlpatterns = [
    # Document upload and management endpoints
    path('upload/', api.upload_document, name='upload_document'),
    path('list/', api.list_documents, name='list_documents'),
    path('<uuid:document_id>/', api.get_document, name='get_document'),
    path('<uuid:document_id>/delete/', api.delete_document, name='delete_document'),
    
    # Vector store operations
    path('search/', api.search_documents, name='search_documents'),
    path('reindex/', api.reindex_documents, name='reindex_documents'),
    
    # Admin endpoint to rebuild the entire ChromaDB index
    path('reindex_all/', api.reindex_documents, name='reindex_all_documents'),
] 