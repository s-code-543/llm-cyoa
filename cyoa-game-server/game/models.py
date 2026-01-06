"""
Models for CYOA game server.
"""
from django.db import models
from django.utils import timezone


class Prompt(models.Model):
    """
    Store different versions of prompts for the game.
    Examples: judge prompts for different game types, storyteller prompts, etc.
    """
    PROMPT_TYPES = [
        ('judge', 'Judge Prompt'),
        ('storyteller', 'Storyteller Prompt'),
        ('test', 'Test Prompt'),
    ]
    
    prompt_type = models.CharField(
        max_length=50,
        choices=PROMPT_TYPES,
        db_index=True,
        help_text="Type of prompt (judge, storyteller, etc.)"
    )
    version = models.IntegerField(
        help_text="Version number (1, 2, 3, ...)"
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="User-friendly description of this version"
    )
    prompt_text = models.TextField(
        help_text="The actual prompt content"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether this prompt is currently active for API calls"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['prompt_type', 'version']
        ordering = ['prompt_type', '-version']
        indexes = [
            models.Index(fields=['prompt_type', 'is_active']),
        ]
    
    def __str__(self):
        active = " [ACTIVE]" if self.is_active else ""
        return f"{self.get_prompt_type_display()} v{self.version}{active}"
    
    def save(self, *args, **kwargs):
        # If this prompt is being set as active, deactivate all other prompts of the same type
        if self.is_active:
            Prompt.objects.filter(
                prompt_type=self.prompt_type,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """
    Track corrections made by the judge to storyteller outputs.
    """
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    original_text = models.TextField(
        help_text="Original output from storyteller LLM"
    )
    refined_text = models.TextField(
        help_text="Final output after judge review"
    )
    was_modified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if judge made changes, False if passed through unchanged"
    )
    prompt_used = models.ForeignKey(
        Prompt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Which judge prompt was active during this request"
    )
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'was_modified']),
        ]
    
    def __str__(self):
        modified = "MODIFIED" if self.was_modified else "UNCHANGED"
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {modified}"
