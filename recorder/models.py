from django.db import models
from django.conf import settings
import uuid

# Create your models here.

class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at'] # Show newest campaigns first

    def __str__(self):
        # Assuming standard User model has username
        # Check if user object exists before accessing username
        if self.user:
            return f"{self.name} (User: {self.user.username})"
        return f"{self.name} (User: Unknown)"
    
    @property
    def document_count(self):
        """Return the number of documents associated with this campaign"""
        return self.documents.count()


class RecordingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='sessions') # Link to Campaign
    # name = models.CharField(max_length=255) # Name might be redundant if we use "Session N" within a campaign
    created_at = models.DateTimeField(auto_now_add=True)
    latest_insight_text = models.TextField(null=True, blank=True)
    latest_insight_timestamp = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # Order sessions within a campaign by creation time
        ordering = ['created_at']

    def __str__(self):
        # Try to determine session number within the campaign
        try:
            # Ensure campaign object exists before accessing related sessions
            if self.campaign:
                 # Note: This can be inefficient if you have many sessions per campaign
                session_ids = list(self.campaign.sessions.order_by('created_at').values_list('id', flat=True))
                try:
                    session_index = session_ids.index(self.id) + 1
                    return f"Session {session_index} ({self.campaign.name})"
                except ValueError:
                    # Should not happen if self.id is in the list, but handle defensively
                     return f"Session {self.id} ({self.campaign.name})"
            else:
                return f"Orphaned Session {self.id}"
        except Exception as e: # Catch potential exceptions during related object access
             # Log the error e for debugging if needed
             return f"Session {self.id} (Error determining campaign)"


class Transcription(models.Model):
    session = models.ForeignKey(RecordingSession, on_delete=models.CASCADE, related_name='transcriptions', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.TextField()
    chunk_number = models.IntegerField()
    language_code = models.CharField(max_length=10, null=True, blank=True)
    language_probability = models.FloatField(null=True, blank=True)
    words_json = models.JSONField(null=True, blank=True)  # Store the detailed word information
    generated_insight_text = models.TextField(null=True, blank=True) # Insight generated after this chunk
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Session {self.session.name} - Chunk {self.chunk_number}"
    
    @property
    def full_text(self):
        """Returns the full text as a properly formatted string."""
        if not self.words_json:
            return self.text
        
        # Combine words with appropriate spacing
        text_parts = []
        for word in self.words_json:
            if word['type'] == 'audio_event':
                text_parts.append(f"({word['text']})")
            else:
                text_parts.append(word['text'])
        
        return ' '.join(text_parts)
