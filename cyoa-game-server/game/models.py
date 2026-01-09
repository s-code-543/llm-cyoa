"""
Models for CYOA game server.
"""
from django.db import models
from django.utils import timezone
import hashlib


class Prompt(models.Model):
    """
    Store different versions of prompts for the game.
    prompt_type can be 'judge' or any adventure name (e.g., 'arctic-alien', 'haunted-house').
    Each prompt_type has its own independent versioning (v1, v2, v3...).
    """
    
    prompt_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of prompt: 'judge' or adventure name (e.g., 'arctic-alien', 'haunted-house')"
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


class Configuration(models.Model):
    """
    Store preset configurations combining adventure prompt, models, and judge prompt.
    Only one configuration can be active at a time.
    """
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Name for this configuration preset"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this configuration"
    )
    adventure_prompt = models.ForeignKey(
        Prompt,
        on_delete=models.PROTECT,
        related_name='configs_as_adventure',
        help_text="Adventure/story prompt to use (any non-judge prompt)"
    )
    storyteller_model = models.CharField(
        max_length=100,
        help_text="Model to use for story generation (e.g., qwen3:4b)"
    )
    judge_prompt = models.ForeignKey(
        Prompt,
        on_delete=models.PROTECT,
        related_name='configs_as_judge',
        limit_choices_to={'prompt_type': 'judge'},
        help_text="Judge prompt to use for validation"
    )
    judge_model = models.CharField(
        max_length=100,
        help_text="Model to use for judge validation (e.g., claude-haiku-4-5)"
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this configuration is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_active', '-updated_at']
        indexes = [
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        active = " [ACTIVE]" if self.is_active else ""
        return f"{self.name}{active}"
    
    def save(self, *args, **kwargs):
        # If this configuration is being set as active, deactivate all others
        if self.is_active:
            Configuration.objects.filter(
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class ResponseCache(models.Model):
    """
    Database-backed cache for synchronizing base and moderated responses.
    Replaces in-memory cache for persistence and multi-instance support.
    """
    cache_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Cache key (session_hash-turn_number)"
    )
    response_text = models.TextField(
        help_text="The cached response from the base storyteller"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this cache entry was created"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cache_key', 'created_at']),
        ]
    
    def __str__(self):
        age = (timezone.now() - self.created_at).total_seconds()
        preview = self.response_text[:50] + "..." if len(self.response_text) > 50 else self.response_text
        return f"{self.cache_key} ({age:.1f}s ago) - {preview}"
    
    @classmethod
    def generate_key(cls, messages, system_prompt=None):
        """
        Generate a cache key from messages.
        Uses hash of first user message plus turn number.
        """
        first_msg = messages[0].get('content', '') if messages else ''
        session_hash = hashlib.sha256(first_msg.encode()).hexdigest()[:8]
        turn = len(messages)
        return f"{session_hash}-{turn}"
    
    @classmethod
    def set_response(cls, cache_key, response_text):
        """Store or update a cached response."""
        cls.objects.update_or_create(
            cache_key=cache_key,
            defaults={'response_text': response_text}
        )
    
    @classmethod
    def get_response(cls, cache_key, max_age_seconds=60):
        """
        Retrieve a cached response if it exists and isn't too old.
        Returns None if not found or expired.
        """
        try:
            cache_entry = cls.objects.get(cache_key=cache_key)
            age = (timezone.now() - cache_entry.created_at).total_seconds()
            if age > max_age_seconds:
                print(f"[CACHE] Entry {cache_key} expired ({age:.1f}s > {max_age_seconds}s)")
                cache_entry.delete()
                return None
            return cache_entry.response_text
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def wait_for_response(cls, cache_key, timeout=30.0, poll_interval=0.5):
        """
        Poll for a cached response, waiting up to timeout seconds.
        Returns response text or None if timeout.
        """
        import time
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            response = cls.get_response(cache_key, max_age_seconds=timeout)
            if response:
                return response
            time.sleep(poll_interval)
        return None
    
    @classmethod
    def cleanup_old_entries(cls, max_age_seconds=3600):
        """
        Delete cache entries older than max_age_seconds.
        Should be called periodically (e.g., via management command or cron).
        """
        cutoff = timezone.now() - timezone.timedelta(seconds=max_age_seconds)
        deleted_count, _ = cls.objects.filter(created_at__lt=cutoff).delete()
        return deleted_count

