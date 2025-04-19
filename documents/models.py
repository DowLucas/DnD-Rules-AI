import uuid
import os
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from recorder.models import Campaign

User = get_user_model()

def document_upload_path(instance, filename):
    """Determine the upload path for document files"""
    # Create path like: documents/campaign_{id}/{filename}
    if instance.campaign:
        return f'documents/campaign_{instance.campaign.id}/{filename}'
    # Fallback to user path if no campaign
    return f'documents/user_{instance.uploaded_by.id}/{filename}'

class Document(models.Model):
    """Model for storing document metadata"""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETE = 'COMPLETE', 'Complete'
        FAILED = 'FAILED', 'Failed'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to=document_upload_path)
    openai_file_id = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="OpenAI File ID")
    file_type = models.CharField(max_length=10)  # pdf, docx, txt, etc.
    file_size = models.PositiveIntegerField(default=0)  # Size in bytes
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='documents')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current processing status of the document"
    )
    
    def __str__(self):
        return self.title
    
    def get_file_extension(self):
        """Return the file extension"""
        return self.file.name.split('.')[-1]
    
    def save(self, *args, **kwargs):
        # Set file type based on file extension if not already set
        if not self.file_type and self.file:
            self.file_type = self.get_file_extension()
            
        # Set file size if not already set
        if self.file and not self.file_size and hasattr(self.file, 'size'):
            self.file_size = self.file.size
            
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']

class DocumentChunk(models.Model):
    """Model for storing document chunks with vector embeddings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()  # Position of chunk in the document
    text = models.TextField()  # The actual text chunk
    embedding = models.JSONField(null=True, blank=True)  # Store embedding as JSON array
    page_number = models.PositiveIntegerField(null=True, blank=True)  # Optional page number if available
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.document.title} - Chunk {self.chunk_index}"
    
    class Meta:
        ordering = ['document', 'chunk_index']
        unique_together = ['document', 'chunk_index']
