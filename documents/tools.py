import json
import logging
from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from .vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

# Define input/output models for our tools
class SearchQuery(BaseModel):
    """Input for the document search tool"""
    query: str = Field(..., description="The search query to find relevant information")
    limit: int = Field(5, description="Maximum number of results to return", ge=1, le=20)
    campaign_id: Optional[str] = Field(None, description="Optional campaign ID to restrict search")

class SearchResult(TypedDict):
    """Single search result item"""
    document_id: str
    document_title: str
    content: str
    page_number: Optional[int]
    relevance_score: Optional[float]

class SearchResults(BaseModel):
    """Output from the document search tool"""
    results: List[SearchResult]

# Custom agent tools
def search_rules_tool(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search the D&D rules knowledge base for information.
    
    Args:
        query: The search query related to D&D rules
        limit: Maximum number of results to return
        
    Returns:
        List of relevant document sections with content
    """
    logger.info(f"Searching rules with query: {query}, limit: {limit}")
    
    # Use the ChromaVectorStore to search
    vector_store = ChromaVectorStore()
    results = vector_store.search(
        query=query,
        limit=limit,
        # No campaign filter for general rules search
        filter_dict=None
    )
    
    # Format for agent consumption
    formatted_results = []
    for result in results:
        formatted_results.append({
            "document_title": result.get("document_title", "Unknown"),
            "content": result.get("content", ""),
            "page_number": result.get("page_number"),
            "relevance_score": result.get("relevance_score")
        })
    
    logger.info(f"Found {len(formatted_results)} results for rules search")
    return formatted_results

def search_campaign_documents_tool(query: str, campaign_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search campaign-specific documents for information.
    
    Args:
        query: The search query for campaign documents
        campaign_id: The campaign ID to search within
        limit: Maximum number of results to return
        
    Returns:
        List of relevant document sections from the campaign
    """
    logger.info(f"Searching campaign documents with query: {query}, campaign: {campaign_id}, limit: {limit}")
    
    # Use the ChromaVectorStore to search with campaign filter
    vector_store = ChromaVectorStore()
    results = vector_store.search(
        query=query,
        limit=limit,
        filter_dict={"campaign_id": campaign_id}
    )
    
    # Format for agent consumption
    formatted_results = []
    for result in results:
        formatted_results.append({
            "document_title": result.get("document_title", "Unknown"),
            "content": result.get("content", ""),
            "page_number": result.get("page_number"),
            "relevance_score": result.get("relevance_score")
        })
    
    logger.info(f"Found {len(formatted_results)} results for campaign document search")
    return formatted_results

# Create function definitions for the OpenAI tool schema
def get_search_rules_schema():
    """Generate a valid schema for the search_rules_tool"""
    return {
        "name": "search_rules_tool", 
        "description": "Search the D&D rules knowledge base for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query related to D&D rules"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return"
                }
            },
            "required": ["query"]
        }
    }

def get_search_campaign_documents_schema():
    """Generate a valid schema for the search_campaign_documents_tool"""
    return {
        "name": "search_campaign_documents_tool",
        "description": "Search campaign-specific documents for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query for campaign documents"
                },
                "campaign_id": {
                    "type": "string",
                    "description": "The campaign ID to search within"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return"
                }
            },
            "required": ["query", "campaign_id"]
        }
    }

# Define functions to register with the Agent SDK
def get_agent_tools():
    """
    Get the tools to register with the OpenAI Agent
    
    Returns:
        list: List of functions that can be used as tools
    """
    # Map the functions to their schema definitions
    tool_definitions = [
        {"schema": get_search_rules_schema(), "function": search_rules_tool},
        {"schema": get_search_campaign_documents_schema(), "function": search_campaign_documents_tool}
    ]
    
    return tool_definitions 