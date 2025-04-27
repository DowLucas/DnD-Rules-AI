import os
import logging
import uuid
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from django.conf import settings
from openai import OpenAI
from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    ChromaDB vector store implementation for document storage and retrieval.
    This class handles the creation, management, and querying of vector embeddings.
    """
    
    _instance = None
    _client = None
    _embedding_function = None
    _collection = None
    
    # Singleton pattern to ensure we only have one connection to the ChromaDB
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChromaVectorStore, cls).__new__(cls)
            cls._initialize()
        return cls._instance
    
    @classmethod
    def _initialize(cls):
        """Initialize the ChromaDB client and collection"""
        # Set up the ChromaDB client
        persist_directory = os.path.join(settings.BASE_DIR, 'chroma_db')
        os.makedirs(persist_directory, exist_ok=True)
        
        cls._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Use OpenAI embedding function
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        cls._embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_api_key,
            model_name="text-embedding-3-small"
        )
        
        # Get or create the collection
        collection_name = os.environ.get("CHROMA_COLLECTION_NAME", "dnd_rules")
        try:
            cls._collection = cls._client.get_collection(
                name=collection_name,
                embedding_function=cls._embedding_function
            )
            logger.info(f"Retrieved existing ChromaDB collection: {collection_name}")
        except ValueError:
            cls._collection = cls._client.create_collection(
                name=collection_name,
                embedding_function=cls._embedding_function,
                metadata={"description": "D&D Rules and Campaign Documents"}
            )
            logger.info(f"Created new ChromaDB collection: {collection_name}")
    
    @classmethod
    def add_document(cls, document_id, chunks):
        """
        Add document chunks to the vector store
        
        Args:
            document_id (str): Document ID
            chunks (list): List of document chunks with text content
            
        Returns:
            bool: Success status
        """
        if not cls._collection:
            cls._initialize()
        
        try:
            # Get document for metadata
            document = Document.objects.get(id=document_id)
            
            # Prepare data for ChromaDB
            ids = []
            documents = []
            metadatas = []
            
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{document_id}_{idx}"
                ids.append(chunk_id)
                documents.append(chunk["text"])
                
                # Create metadata dictionary without None values
                metadata = {
                    "document_id": str(document_id),
                    "document_title": document.title,
                    "chunk_index": idx,
                    "file_type": document.file_type,
                }
                
                # Add optional fields only if they're not None
                page_number = chunk.get("page_number")
                if page_number is not None:
                    metadata["page_number"] = page_number
                
                # Only add campaign_id if campaign exists
                if document.campaign:
                    metadata["campaign_id"] = str(document.campaign.id)
                
                metadatas.append(metadata)
            
            # Add to ChromaDB
            cls._collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(chunks)} chunks from document {document_id} to ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document to ChromaDB: {str(e)}")
            return False
    
    @classmethod
    def search(cls, query, limit=15, filter_dict=None):
        """
        Search for documents matching a query
        
        Args:
            query (str): Search query text
            limit (int): Maximum number of results to return
            filter_dict (dict): Optional filter criteria for search
            
        Returns:
            list: List of search results with document info and content
        """
        if not cls._collection:
            cls._initialize()
        
        try:
            # Convert filter_dict to ChromaDB format if provided
            where_filter = None
            if filter_dict:
                where_filter = {}
                for k, v in filter_dict.items():
                    if v is not None:  # Only add non-None values to filter
                        where_filter[k] = v
                
                # If all values were None, set where_filter back to None
                if not where_filter:
                    where_filter = None
            
            # Search ChromaDB
            results = cls._collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            
            if not results or not results["documents"]:
                return []
                
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results.get("distances") else None
                
                formatted_results.append({
                    "document_id": metadata.get("document_id"),
                    "document_title": metadata.get("document_title"),
                    "chunk_index": metadata.get("chunk_index"),
                    "page_number": metadata.get("page_number"),
                    "content": doc,
                    "relevance_score": 1 - (distance / 2) if distance is not None else None  # Convert distance to score
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching ChromaDB: {str(e)}")
            return []
    
    @classmethod
    def delete_document(cls, document_id):
        """
        Delete a document and all its chunks from the vector store
        
        Args:
            document_id (str): Document ID
            
        Returns:
            bool: Success status
        """
        if not cls._collection:
            cls._initialize()
        
        try:
            # Delete all chunks for this document
            cls._collection.delete(
                where={"document_id": str(document_id)}
            )
            
            logger.info(f"Deleted document {document_id} from ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document from ChromaDB: {str(e)}")
            return False
    
    @classmethod
    def reset(cls):
        """
        Reset the ChromaDB collection - DANGER: Removes all data!
        Only use for testing or complete reindexing
        
        Returns:
            bool: Success status
        """
        if not cls._client:
            cls._initialize()
        
        try:
            collection_name = os.environ.get("CHROMA_COLLECTION_NAME", "dnd_rules")
            cls._client.delete_collection(collection_name)
            logger.warning(f"Deleted ChromaDB collection: {collection_name}")
            
            # Reinitialize the collection
            cls._collection = cls._client.create_collection(
                name=collection_name,
                embedding_function=cls._embedding_function,
                metadata={"description": "D&D Rules and Campaign Documents"}
            )
            logger.info(f"Recreated ChromaDB collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting ChromaDB: {str(e)}")
            return False 