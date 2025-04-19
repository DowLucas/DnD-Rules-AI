import os
import json
import logging
import time
from django.conf import settings
from django.db import transaction
from openai import OpenAI, APIError, RateLimitError
from .models import Document, DocumentChunk
from .utils import extract_text, chunk_text, create_embeddings

logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    def upload_document(file, title, description, user, campaign=None):
        """
        Create the Document record, upload file to OpenAI, and associate with Vector Store.
        Local processing (chunking, embedding) is removed as OpenAI handles this.
        
        Args:
            file: File object from request
            title (str): Document title
            description (str): Document description
            user: User who uploaded the document
            campaign: Optional Campaign to associate with the document
            
        Returns:
            Document: The created Document instance with OpenAI File ID
        """
        openai_client = OpenAI()
        vector_store_id = os.environ.get('VECTOR_STORE_ID')

        if not vector_store_id:
            logger.error("VECTOR_STORE_ID environment variable not set.")
            raise ValueError("Vector Store ID is not configured in the environment.")

        openai_file_id = None
        document = None
        
        try:
            # Create the document record first to store metadata
            # Status is PENDING until OpenAI confirms processing
            document = Document.objects.create(
                title=title,
                description=description,
                file=file, # Still save locally for reference/backup?
                uploaded_by=user,
                campaign=campaign,
                status=Document.Status.PENDING # Initial status
            )
            logger.info(f"Created local Document record {document.id} for {title}")

            # 1. Upload the file to OpenAI
            logger.info(f"Uploading file {file.name} to OpenAI...")
            start_time = time.time()
            # Pass the file object directly from the request
            openai_file = openai_client.files.create(
                file=file,
                purpose="assistants" # Purpose required for assistants/vector stores
            )
            openai_file_id = openai_file.id
            upload_duration = time.time() - start_time
            logger.info(f"Successfully uploaded file to OpenAI. File ID: {openai_file_id} ({upload_duration:.2f}s)")
            
            # Update local document with OpenAI File ID
            document.openai_file_id = openai_file_id
            document.status = Document.Status.PROCESSING # Mark as processing by OpenAI
            document.save(update_fields=['openai_file_id', 'status'])

            # 2. Add the file to the Vector Store
            logger.info(f"Adding OpenAI File {openai_file_id} to Vector Store {vector_store_id}...")
            start_time = time.time()
            vector_store_file = openai_client.beta.vector_stores.files.create(
                vector_store_id=vector_store_id,
                file_id=openai_file_id
            )
            add_duration = time.time() - start_time
            logger.info(f"Successfully added file {openai_file_id} to vector store {vector_store_id}. Status: {vector_store_file.status} ({add_duration:.2f}s)")
            
            # Note: Actual processing/chunking by OpenAI happens asynchronously.
            # We can't reliably set status to COMPLETE here immediately.
            # We rely on the vector_store_file.status, but might need a background task
            # or webhook later to confirm completion if precise status is critical.
            if vector_store_file.status == 'completed':
                 document.status = Document.Status.COMPLETE
            elif vector_store_file.status == 'failed':
                 document.status = Document.Status.FAILED
            else: # in_progress, cancelled
                 document.status = Document.Status.PROCESSING 
            document.save(update_fields=['status'])
                
            return document
        
        except (APIError, RateLimitError) as e:
            logger.error(f"OpenAI API error during document upload/association: {e}")
            if document:
                document.status = Document.Status.FAILED
                document.save(update_fields=['status'])
            # Clean up OpenAI file if upload succeeded but association failed?
            if openai_file_id:
                 logger.warning(f"Attempting to delete uploaded OpenAI file {openai_file_id} due to error.")
                 try:
                      openai_client.files.delete(openai_file_id)
                 except Exception as delete_err:
                      logger.error(f"Failed to delete OpenAI file {openai_file_id}: {delete_err}")
            raise # Re-raise the original error
        except Exception as e:
            logger.error(f"Unexpected error in upload_document service: {str(e)}")
            if document:
                document.status = Document.Status.FAILED
                document.save(update_fields=['status'])
            # Add cleanup logic for OpenAI file if applicable
            if openai_file_id:
                 logger.warning(f"Attempting to delete uploaded OpenAI file {openai_file_id} due to unexpected error.")
                 try:
                      openai_client.files.delete(openai_file_id)
                 except Exception as delete_err:
                      logger.error(f"Failed to delete OpenAI file {openai_file_id}: {delete_err}")
            raise

    @staticmethod
    def process_document(document_id):
        """
        DEPRECATED: This method is no longer needed as processing (chunking, embedding)
        is handled by OpenAI when adding files to a vector store.
        """
        logger.warning("DocumentService.process_document is deprecated and should not be called.")
        # Optionally update status if it was somehow left in PENDING without OpenAI ID
        try:
             doc = Document.objects.get(id=document_id)
             if doc.status == Document.Status.PENDING and not doc.openai_file_id:
                  doc.status = Document.Status.FAILED
                  doc.save(update_fields=['status'])
        except Document.DoesNotExist:
             pass # Document doesn't exist, nothing to do
        return False # Indicate failure as this path shouldn't be used

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
            # Chunks are no longer stored locally
            # chunks = document.chunks.all().order_by('chunk_index')
            
            return {
                'id': document.id,
                'title': document.title,
                'description': document.description,
                'openai_file_id': document.openai_file_id, # Include OpenAI ID
                'file_type': document.file_type,
                'file_size': document.file_size,
                'uploaded_by': document.uploaded_by.username if document.uploaded_by else None,
                'campaign': document.campaign.id if document.campaign else None,
                'campaign_name': document.campaign.name if document.campaign else None,
                'created_at': document.created_at,
                'updated_at': document.updated_at,
                'status': document.status,
                # 'chunks': [] # Remove chunks as they are not stored locally anymore
            }
        except Document.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting document details for {document_id}: {str(e)}")
            return None
            
    @staticmethod
    def delete_document(document_id):
        """
        Delete a document locally and attempt to delete the corresponding file from OpenAI.
        """
        openai_client = OpenAI()
        try:
            document = Document.objects.get(id=document_id)
            openai_file_id_to_delete = document.openai_file_id
            local_file_path = document.file.path if document.file else None

            # 1. Delete the local document record (cascades delete chunks if any)
            document.delete()
            logger.info(f"Successfully deleted local Document record {document_id}")

            # 2. Delete the local file if it exists
            if local_file_path and os.path.isfile(local_file_path):
                try:
                    os.remove(local_file_path)
                    logger.info(f"Successfully deleted local file {local_file_path}")
                except OSError as e:
                    logger.error(f"Error deleting local file {local_file_path}: {e}")
            
            # 3. Delete the file from OpenAI if an ID exists
            if openai_file_id_to_delete:
                logger.info(f"Attempting to delete OpenAI file {openai_file_id_to_delete}...")
                try:
                    delete_status = openai_client.files.delete(openai_file_id_to_delete)
                    if delete_status.deleted:
                         logger.info(f"Successfully deleted OpenAI file {openai_file_id_to_delete}.")
                    else:
                         logger.warning(f"OpenAI reported file {openai_file_id_to_delete} was not deleted (status: {delete_status}).")
                except APIError as e:
                     logger.error(f"OpenAI API error deleting file {openai_file_id_to_delete}: {e}")
                     # Decide if this should cause the overall function to return False
                except Exception as e:
                     logger.error(f"Unexpected error deleting OpenAI file {openai_file_id_to_delete}: {e}")
            
            return True
        except Document.DoesNotExist:
            logger.warning(f"Attempted to delete non-existent document with ID {document_id}")
            return False
        except Exception as e:
            logger.error(f"Error during document deletion process for ID {document_id}: {str(e)}")
            return False 