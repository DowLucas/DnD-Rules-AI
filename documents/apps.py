from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'
    
    def ready(self):
        """
        Method called when the Django application is ready.
        Lists the contents of the vector store.
        """
        # Import services here to avoid circular imports
        try:
            from .services import DocumentService
            import os
            
            # Check if project ID is set
            project_id = os.environ.get('OPENAI_PROJECT_ID', 'proj_G4NvFcOxfJHoDAHb8CtH3iEM')
            logger.info(f"Using OpenAI Project ID: {project_id}")
            
            # Check if vector store ID is set before attempting to list contents
            vector_store_id = os.environ.get('VECTOR_STORE_ID')
            if not vector_store_id:
                logger.warning("VECTOR_STORE_ID environment variable not set. Skipping vector store listing.")
                return
            
            logger.info(f"Using Vector Store ID: {vector_store_id}")
            
            # List vector store contents
            logger.info("Listing OpenAI Vector Store contents...")
            try:
                vector_store_info = DocumentService.list_vector_store_contents()
                if "error" in vector_store_info:
                    logger.error(f"Failed to list vector store contents: {vector_store_info['error']}")
                else:
                    logger.info(f"Vector Store: {vector_store_info['name']} (ID: {vector_store_info['id']})")
                    logger.info(f"File count: {vector_store_info['file_count']}")
                    
                    # List each file in the vector store
                    if vector_store_info['file_count'] > 0:
                        logger.info("Files in Vector Store:")
                        for idx, file in enumerate(vector_store_info['files'], 1):
                            # Handle the case where file_id might not be present
                            file_id = file.get('file_id', file.get('id', 'unknown'))
                            status = file.get('status', 'unknown')
                            filename = file.get('filename', 'Unknown name')
                            
                            # Print file information in a clear format
                            logger.info(f"  {idx}. File: {filename}")
                            logger.info(f"     ID: {file_id}")
                            logger.info(f"     Status: {status}")
                    else:
                        logger.info("No files found in the Vector Store.")
            except Exception as e:
                logger.error(f"Error in ready method when listing vector store: {str(e)}")
        except ImportError as e:
            logger.error(f"Import error in ready method: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in ready method: {str(e)}")
