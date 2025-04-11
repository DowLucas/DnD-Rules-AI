from django.db import models

# Create your models here.

class RecordingSession(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
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
    language_code = models.CharField(max_length=10, null=True)
    language_probability = models.FloatField(null=True)
    words_json = models.JSONField(null=True)  # Store the detailed word information
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Chunk {self.chunk_number} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    
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
