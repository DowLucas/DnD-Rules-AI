from django.db import models
import uuid

# Create your models here.

class RecordingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    latest_insight_text = models.TextField(null=True, blank=True)
    latest_insight_timestamp = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

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
