import os
import re
import PyPDF2
import docx
import numpy as np
import faiss
import logging
from django.conf import settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
from django.db.models import Q, QuerySet
import json

from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# Load the embedding model
EMBEDDING_MODEL = None

def get_embedding_model():
    """
    Get or initialize the embedding model
    """
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        # Use a smaller model that's good for semantic search
        # You can change this to a different model based on your needs
        EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    return EMBEDDING_MODEL

def extract_text(file_path, file_type):
    """
    Extract text from various document types
    
    Args:
        file_path (str): Path to the document
        file_type (str): Type of document (pdf, docx, txt)
        
    Returns:
        str: Extracted text
    """
    try:
        if file_type == 'pdf':
            return extract_text_from_pdf(file_path)
        elif file_type == 'docx':
            return extract_text_from_docx(file_path)
        elif file_type == 'txt':
            return extract_text_from_txt(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {str(e)}")
        raise

def extract_text_from_pdf(file_path):
    """Extract text from PDF file"""
    text = ""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(file_path):
    """Extract text from DOCX file"""
    doc = docx.Document(file_path)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_text_from_txt(file_path):
    """Extract text from plain text file"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def chunk_text(text, chunk_size=1000, overlap=200):
    """
    Split text into overlapping chunks
    
    Args:
        text (str): Text to chunk
        chunk_size (int): Maximum size of each chunk
        overlap (int): Overlap between chunks
        
    Returns:
        list: List of text chunks
    """
    if not text:
        return []
        
    # Clean the text by removing excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Initialize variables
    chunks = []
    start = 0
    
    # Create chunks with overlap
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # If not at the end of the text, try to find a good breaking point
        if end < len(text):
            # Try to break at sentence boundary
            sentence_break = text.rfind('. ', start, end)
            if sentence_break != -1 and sentence_break > start + chunk_size // 2:
                end = sentence_break + 1  # Include the period
            else:
                # Try to break at space
                space_break = text.rfind(' ', start, end)
                if space_break != -1 and space_break > start + chunk_size // 2:
                    end = space_break
        
        # Add the chunk
        chunks.append(text[start:end].strip())
        
        # Move to the next chunk with overlap
        start = end - overlap if end < len(text) else len(text)
    
    return chunks

def create_embeddings(text_chunks):
    """
    Create embeddings for chunks using SentenceTransformer
    
    Args:
        text_chunks (list): List of text chunks
        
    Returns:
        numpy.ndarray: Array of embeddings
    """
    if not text_chunks:
        return np.array([])
        
    model = get_embedding_model()
    embeddings = model.encode(text_chunks)
    
    return embeddings

def create_faiss_index(embeddings):
    """
    Create a FAISS index from embeddings
    
    Args:
        embeddings (numpy.ndarray): Array of embeddings
        
    Returns:
        faiss.Index: FAISS index
    """
    if len(embeddings) == 0:
        return None
        
    # Get the dimensionality of embeddings
    dimension = embeddings.shape[1]
    
    # Create index - using L2 distance
    index = faiss.IndexFlatL2(dimension)
    
    # Normalize embeddings for cosine similarity search
    faiss.normalize_L2(embeddings)
    
    # Add embeddings to the index
    index.add(embeddings)
    
    return index

def search_faiss_index(index, query_embedding, k=5):
    """
    Search for similar embeddings in a FAISS index
    
    Args:
        index (faiss.Index): FAISS index
        query_embedding (numpy.ndarray): Query embedding
        k (int): Number of results to return
        
    Returns:
        tuple: (distances, indices)
    """
    if index is None:
        return np.array([]), np.array([])
        
    # Reshape and normalize query embedding for search
    query_embedding = query_embedding.reshape(1, -1)
    faiss.normalize_L2(query_embedding)
    
    # Search the index
    distances, indices = index.search(query_embedding, k)
    
    return distances, indices

def search_documents(query: str, document_filter: Optional[Q] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for document chunks matching the query using vector similarity
    
    Args:
        query: The search query string
        document_filter: Optional Q object to filter documents (e.g., by status)
        limit: Maximum number of results to return
    
    Returns:
        List of dictionaries containing search results
    """
    # Filter documents if a filter was provided
    if document_filter is not None:
        documents = Document.objects.filter(document_filter)
    else:
        documents = Document.objects.all()
    
    # Get chunks for filtered documents
    chunks = DocumentChunk.objects.filter(document__in=documents)
    
    # If no chunks, return empty result
    if not chunks.exists():
        return []
    
    # Create a list of embeddings from stored chunks
    embeddings_list = []
    chunks_list = []
    
    for chunk in chunks:
        try:
            embedding = json.loads(chunk.embedding)
            embeddings_list.append(embedding)
            chunks_list.append(chunk)
        except (json.JSONDecodeError, AttributeError):
            # Skip chunks with invalid embeddings
            continue
    
    if not embeddings_list:
        return []
    
    # Convert to numpy array
    embeddings_np = np.array(embeddings_list, dtype=np.float32)
    
    # Create FAISS index
    index = faiss.IndexFlatL2(embeddings_np.shape[1])
    index.add(embeddings_np)
    
    # Create query embedding
    query_embedding = get_embedding_model().encode([query])[0]
    
    # Search
    k = min(limit, len(chunks_list))  # Return at most 'limit' results
    D, I = index.search(np.array([query_embedding], dtype=np.float32), k)
    
    # Format results
    results = []
    for i, (distance, idx) in enumerate(zip(D[0], I[0])):
        if idx < len(chunks_list):
            chunk = chunks_list[idx]
            document = chunk.document
            
            results.append({
                'document_id': document.id,
                'document_title': document.title,
                'campaign_id': document.campaign.id if document.campaign else None,
                'campaign_name': document.campaign.name if document.campaign else None,
                'chunk_id': chunk.id,
                'chunk_text': chunk.text,
                'page_number': chunk.page_number,
                'similarity_score': float(1.0 / (1.0 + distance))  # Convert distance to similarity score
            })
    
    return results 