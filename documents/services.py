import os
import json
import logging
import time
from django.conf import settings
from django.db import transaction
from openai import OpenAI, APIError, RateLimitError
from .models import Document, DocumentChunk
from .utils import extract_text, chunk_text, create_embeddings
from .vector_store import ChromaVectorStore

# Force reload - code has been updated
logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    def upload_document(file, title, description, user, campaign=None):
        """
        Create the Document record, process the file, and add to ChromaDB vector store.
        
        Args:
            file: File object from request
            title (str): Document title
            description (str): Document description
            user: User who uploaded the document
            campaign: Optional Campaign to associate with the document
            
        Returns:
            Document: The created Document instance
        """
        document = None
        
        try:
            # Create the document record
            document = Document.objects.create(
                title=title,
                description=description,
                file=file,
                uploaded_by=user,
                campaign=campaign,
                status=Document.Status.PENDING
            )
            logger.info(f"Created Document record {document.id} for {title}")

            # Process document in a transaction
            with transaction.atomic():
                # Extract text from document
                document_text = extract_text(document.file.path)
                if not document_text:
                    logger.error(f"Failed to extract text from document {document.id}")
                    document.status = Document.Status.FAILED
                    document.save(update_fields=['status'])
                    return document
                
                # Split into chunks
                chunks = chunk_text(document_text, chunk_size=1000, overlap=100)
                logger.info(f"Split document {document.id} into {len(chunks)} chunks")
                
                # Create chunks in database
                db_chunks = []
                for idx, chunk in enumerate(chunks):
                    # Extract page number if available (for PDFs)
                    page_number = None
                    chunk_content = chunk
                    if isinstance(chunk, dict) and 'page' in chunk:
                        page_number = chunk['page']
                        chunk_content = chunk['text']
                    
                    # Create chunk object
                    chunk_obj = {
                        "text": chunk_content,
                        "chunk_index": idx,
                        "page_number": page_number
                    }
                    db_chunks.append(chunk_obj)
                    
                    # Create DB record (optional, we could just use ChromaDB)
                    DocumentChunk.objects.create(
                        document=document,
                        chunk_index=idx,
                        text=chunk_content,
                        page_number=page_number
                    )
                
                # Add chunks to ChromaDB vector store
                vector_store = ChromaVectorStore()
                success = vector_store.add_document(document.id, db_chunks)
                
                if success:
                    document.status = Document.Status.COMPLETE
                    document.save(update_fields=['status'])
                    logger.info(f"Successfully added document {document.id} to vector store")
                else:
                    document.status = Document.Status.FAILED
                    document.save(update_fields=['status'])
                    logger.error(f"Failed to add document {document.id} to vector store")
                
                return document
        
        except Exception as e:
            logger.error(f"Error in upload_document service: {str(e)}")
            if document:
                document.status = Document.Status.FAILED
                document.save(update_fields=['status'])
            raise

    @staticmethod
    def delete_document(document_id):
        """
        Delete a document and its chunks from the database and vector store
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            bool: Success status
        """
        try:
            document = Document.objects.get(id=document_id)
            
            # Delete from ChromaDB first
            vector_store = ChromaVectorStore()
            vector_store.delete_document(document_id)
            
            # Now delete from database
            document.delete()
            
            logger.info(f"Successfully deleted document {document_id}")
            return True
        
        except Document.DoesNotExist:
            logger.warning(f"Document {document_id} not found for deletion")
            return False
        
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            return False

    @staticmethod
    def search_documents(query_text, campaign_id=None, limit=15):
        """
        Search for document chunks relevant to a query
        
        Args:
            query_text (str): Text to search for
            campaign_id (str): Optional campaign ID to filter by
            limit (int): Maximum number of results to return
            
        Returns:
            list: List of document chunks matching the query
        """
        try:
            # Create filter dict if campaign_id is provided
            filter_dict = {"campaign_id": campaign_id} if campaign_id else None
            
            # Search using ChromaDB
            vector_store = ChromaVectorStore()
            results = vector_store.search(
                query=query_text,
                limit=limit,
                filter_dict=filter_dict
            )
            
            return results
        
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return []
            
    @staticmethod
    def get_document_details(document_id):
        """
        Get details of a document including its chunks
        
        Args:
            document_id: ID of the document
            
        Returns:
            dict: Document details
        """
        try:
            document = Document.objects.get(id=document_id)
            chunks = document.chunks.all().order_by('chunk_index')
            
            return {
                'id': document.id,
                'title': document.title,
                'description': document.description,
                'file_type': document.file_type,
                'file_size': document.file_size,
                'uploaded_by': document.uploaded_by.username if document.uploaded_by else None,
                'campaign': document.campaign.id if document.campaign else None,
                'campaign_name': document.campaign.name if document.campaign else None,
                'created_at': document.created_at,
                'updated_at': document.updated_at,
                'status': document.status,
                'chunks': [
                    {
                        'id': chunk.id,
                        'chunk_index': chunk.chunk_index,
                        'text': chunk.text,
                        'page_number': chunk.page_number
                    }
                    for chunk in chunks
                ]
            }
        
        except Document.DoesNotExist:
            logger.warning(f"Document {document_id} not found")
            return None
        
        except Exception as e:
            logger.error(f"Error getting document details for {document_id}: {str(e)}")
            return None

    @staticmethod
    def reindex_all_documents():
        """
        Reindex all documents in the ChromaDB vector store
        This is useful when changing embedding models or vector store settings
        
        Returns:
            bool: Success status
        """
        try:
            # Reset the vector store
            vector_store = ChromaVectorStore()
            vector_store.reset()
            
            # Get all documents
            documents = Document.objects.all()
            logger.info(f"Reindexing {documents.count()} documents")
            
            # Process each document
            for document in documents:
                # Extract text from document
                document_text = extract_text(document.file.path)
                if not document_text:
                    logger.error(f"Failed to extract text from document {document.id}")
                    continue
                
                # Split into chunks
                chunks = chunk_text(document_text, chunk_size=1000, overlap=100)
                
                # Prepare chunks format
                db_chunks = []
                for idx, chunk_text in enumerate(chunks):
                    # Extract page number if available
                    page_number = None
                    if isinstance(chunk_text, dict) and 'page' in chunk_text:
                        page_number = chunk_text['page']
                        chunk_text = chunk_text['text']
                    
                    # Create chunk
                    chunk = {
                        "text": chunk_text,
                        "chunk_index": idx,
                        "page_number": page_number
                    }
                    db_chunks.append(chunk)
                
                # Add to vector store
                success = vector_store.add_document(document.id, db_chunks)
                if success:
                    document.status = Document.Status.COMPLETE
                    document.save(update_fields=['status'])
                    logger.info(f"Successfully reindexed document {document.id}")
                else:
                    document.status = Document.Status.FAILED
                    document.save(update_fields=['status'])
                    logger.error(f"Failed to reindex document {document.id}")
            
            logger.info("Reindexing complete")
            return True
        
        except Exception as e:
            logger.error(f"Error reindexing documents: {str(e)}")
            return False

# End of DocumentService class 