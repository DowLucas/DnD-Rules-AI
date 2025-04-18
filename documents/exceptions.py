class DocumentProcessingError(Exception):
    """Exception raised when document processing fails"""
    pass

class DocumentNotFoundException(Exception):
    """Exception raised when a document is not found"""
    pass

class InvalidQueryError(Exception):
    """Exception raised when a search query is invalid"""
    pass 