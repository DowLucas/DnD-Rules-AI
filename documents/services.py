import os
import json
import logging
from django.conf import settings
from django.db import transaction
from .models import Document, DocumentChunk
from .utils import extract_text, chunk_text, create_embeddings

logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    def upload_document(file, title, description, user, campaign=None):
        """
        Upload a document, process it, and create the Document record
        
        Args:
            file: File object from request
            title (str): Document title
            description (str): Document description
            user: User who uploaded the document
            campaign: Optional Campaign to associate with the document
            
        Returns:
            Document: The created Document instance
        """
        try:
            with transaction.atomic():
                # Create the document record first
                document = Document.objects.create(
                    title=title,
                    description=description,
                    file=file,
                    uploaded_by=user,
                    campaign=campaign,
                    status=Document.Status.PENDING
                )
                
                # Start the processing in a background task
                # In a real application, you'd use Celery or similar
                # For now, we'll process synchronously
                DocumentService.process_document(document.id)
                
                return document
        except Exception as e:
            logger.error(f"Error uploading document: {str(e)}")
            raise

    @staticmethod
    def process_document(document_id):
        """
        Process a document - extract text, chunk it, and create embeddings
        
        Args:
            document_id: ID of the document to process
            
        Returns:
            bool: True if processing succeeded, False otherwise
        """
        try:
            document = Document.objects.get(id=document_id)
            
            # Update status to processing
            document.status = Document.Status.PROCESSING
            document.save(update_fields=['status'])
            
            # Get the file path
            file_path = document.file.path
            file_type = document.file_type
            
            # Extract text from the document
            text = extract_text(file_path, file_type)
            
            # Chunk the text
            chunks = chunk_text(text)
            
            # Get embeddings for all chunks
            embeddings = create_embeddings(chunks)
            
            # Save chunks and embeddings to the database
            with transaction.atomic():
                # Delete any existing chunks for this document
                DocumentChunk.objects.filter(document=document).delete()
                
                # Create new chunks
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    DocumentChunk.objects.create(
                        document=document,
                        chunk_index=i,
                        text=chunk,
                        embedding=embedding.tolist()  # Convert numpy array to list for JSON storage
                    )
                
                # Mark document as complete
                document.status = Document.Status.COMPLETE
                document.save(update_fields=['status'])
                
            return True
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {str(e)}")
            if Document.objects.filter(id=document_id).exists():
                document = Document.objects.get(id=document_id)
                document.status = Document.Status.FAILED
                document.save(update_fields=['status'])
            return False

    @staticmethod
    def search_documents(query_text, document_filter=None, limit=5):
        """
        Search for document chunks relevant to a query
        
        Args:
            query_text (str): Text to search for
            document_filter (Q): Django Q object to filter documents
            limit (int): Maximum number of results to return
            
        Returns:
            list: List of document chunks matching the query
        """
        from .utils import create_embeddings, search_faiss_index, search_documents
        
        try:
            results = search_documents(
                query=query_text, 
                document_filter=document_filter, 
                limit=limit
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
            return None
        except Exception as e:
            logger.error(f"Error getting document details for {document_id}: {str(e)}")
            return None
            
    @staticmethod
    def delete_document(document_id):
        """
        Delete a document and its chunks
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            bool: True if deletion succeeded, False otherwise
        """
        try:
            document = Document.objects.get(id=document_id)
            
            # Delete the file if it exists
            if document.file and os.path.isfile(document.file.path):
                os.remove(document.file.path)
                
            # Delete the document (this will cascade delete chunks)
            document.delete()
            
            return True
        except Document.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            return False 