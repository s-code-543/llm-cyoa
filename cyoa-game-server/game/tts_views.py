"""
Text-to-Speech API views for generating audio from text.
"""
import os
import hashlib
import logging
from pathlib import Path
from datetime import timedelta
from django.utils import timezone

from django.conf import settings
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from openai import OpenAI

from .models import TTSAudio, TTSSettings

logger = logging.getLogger(__name__)

# Configuration for OpenAI TTS
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set - TTS will not work")

# Media root for storing TTS audio
MEDIA_ROOT = getattr(settings, 'MEDIA_ROOT', settings.BASE_DIR / 'media')
TTS_AUDIO_DIR = Path(MEDIA_ROOT) / 'tts_audio'


def ensure_tts_dir():
    """Ensure the TTS audio directory exists."""
    TTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of text for deduplication."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def cleanup_old_tts_files(retention_days: int = 7):
    """
    Clean up TTS audio files older than retention_days.
    
    Strategy: Piggyback cleanup on request processing to avoid needing Celery.
    This runs during normal operation when users generate new TTS audio.
    
    Args:
        retention_days: Number of days to keep audio files
        
    Returns:
        Tuple of (files_deleted, records_deleted)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        # Find old records
        old_records = TTSAudio.objects.filter(created_at__lt=cutoff_date)
        
        files_deleted = 0
        records_deleted = 0
        
        for record in old_records:
            # Delete physical file if it exists
            if record.file_path:
                file_path = Path(MEDIA_ROOT) / record.file_path
                
                # Security: Verify file is within TTS_AUDIO_DIR before deleting
                try:
                    resolved_path = file_path.resolve()
                    if not resolved_path.is_relative_to(TTS_AUDIO_DIR.resolve()):
                        logger.error(f"Security: Attempted to delete file outside TTS directory: {record.file_path}")
                        continue
                except (ValueError, OSError) as e:
                    logger.error(f"Path resolution error for {record.file_path}: {e}")
                    continue
                
                if file_path.exists():
                    try:
                        file_path.unlink()
                        files_deleted += 1
                        logger.info(f"Deleted old TTS file: {record.file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete TTS file {record.file_path}: {e}")
            
            # Delete database record
            try:
                record.delete()
                records_deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete TTS record {record.id}: {e}")
        
        if files_deleted > 0 or records_deleted > 0:
            logger.info(f"TTS cleanup: deleted {files_deleted} files, {records_deleted} DB records")
        
        return files_deleted, records_deleted
        
    except Exception as e:
        logger.error(f"TTS cleanup failed: {e}")
        return 0, 0


@require_http_methods(["POST"])
def tts_generate(request):
    """
    Generate TTS audio from text.
    Checks for existing audio with same text/voice/model before generating.
    
    Request JSON:
    {
        "text": "Text to convert to speech",
        "voice": "alloy",  // optional, uses settings default
        "model": "tts-1"   // optional, uses settings default
    }
    
    Response JSON:
    {
        "audio_id": "uuid",
        "status": "completed" | "pending" | "failed",
        "url": "/api/tts/audio/<uuid>"  // if completed
    }
    """
    # Get TTS settings
    tts_settings = TTSSettings.get_settings()
    
    if not tts_settings.enabled:
        return JsonResponse({
            'error': 'TTS service is disabled'
        }, status=503)
    
    if not OPENAI_API_KEY:
        return JsonResponse({
            'error': 'TTS service not configured (missing API key)'
        }, status=503)
    
    # Run automatic cleanup if enabled (piggyback on request)
    if tts_settings.auto_cleanup_enabled:
        # Run cleanup asynchronously in a try/except so it doesn't block the request
        try:
            cleanup_old_tts_files(tts_settings.audio_retention_days)
        except Exception as e:
            logger.error(f"Auto-cleanup failed (non-fatal): {e}")
    
    # Parse request
    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'Text is required'}, status=400)
    
    # Check text length against settings
    if len(text) > tts_settings.max_text_length:
        return JsonResponse({
            'error': f'Text too long (max {tts_settings.max_text_length} characters)'
        }, status=400)
    
    # Use settings defaults if not provided
    voice = data.get('voice') or tts_settings.openai_voice
    model = data.get('model') or tts_settings.openai_model
    
    # Validate voice
    valid_voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
    if voice not in valid_voices:
        return JsonResponse({'error': f'Invalid voice. Must be one of: {", ".join(valid_voices)}'}, status=400)
    
    # Validate model
    valid_models = ['tts-1', 'tts-1-hd']
    if model not in valid_models:
        return JsonResponse({'error': f'Invalid model. Must be one of: {", ".join(valid_models)}'}, status=400)
    
    # Compute text hash for deduplication
    text_hash = compute_text_hash(text)
    
    # Check if we already have this audio
    existing = TTSAudio.objects.filter(
        text_hash=text_hash,
        voice=voice,
        model=model,
        status='completed'
    ).first()
    
    if existing and existing.file_path:
        audio_path = Path(MEDIA_ROOT) / existing.file_path
        if audio_path.exists():
            logger.info(f"Returning cached TTS audio: {existing.id}")
            return JsonResponse({
                'audio_id': str(existing.id),
                'status': 'completed',
                'url': f'/api/tts/audio/{existing.id}'
            })
        else:
            # File missing, mark as failed
            existing.status = 'failed'
            existing.error_text = 'Audio file not found on disk'
            existing.save()
    
    # Create new TTS audio record
    ensure_tts_dir()
    
    tts_audio = TTSAudio.objects.create(
        text=text,
        text_hash=text_hash,
        voice=voice,
        model=model,
        status='generating'
    )
    
    # Generate audio using OpenAI
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format='mp3'
        )
        
        # Save audio file
        file_name = f"{tts_audio.id}.mp3"
        relative_path = f"tts_audio/{file_name}"
        file_path = Path(MEDIA_ROOT) / relative_path
        
        # Write audio to file
        with open(file_path, 'wb') as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)
        
        # Update record
        tts_audio.file_path = relative_path
        tts_audio.status = 'completed'
        tts_audio.save()
        
        logger.info(f"Generated TTS audio: {tts_audio.id} ({voice}, {len(text)} chars)")
        
        return JsonResponse({
            'audio_id': str(tts_audio.id),
            'status': 'completed',
            'url': f'/api/tts/audio/{tts_audio.id}'
        })
        
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        tts_audio.status = 'failed'
        tts_audio.error_text = str(e)
        tts_audio.save()
        
        return JsonResponse({
            'audio_id': str(tts_audio.id),
            'status': 'failed',
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def tts_audio(request, audio_id):
    """
    Stream/download generated TTS audio file.
    
    URL: /api/tts/audio/<uuid>
    """
    try:
        tts_audio = TTSAudio.objects.get(id=audio_id)
    except TTSAudio.DoesNotExist:
        return JsonResponse({'error': 'Audio not found'}, status=404)
    
    if tts_audio.status != 'completed':
        return JsonResponse({
            'error': f'Audio not ready (status: {tts_audio.status})'
        }, status=404)
    
    if not tts_audio.file_path:
        return JsonResponse({'error': 'Audio file path not set'}, status=404)
    
    audio_path = Path(MEDIA_ROOT) / tts_audio.file_path
    
    # Security: Verify file is within TTS_AUDIO_DIR before serving
    try:
        resolved_path = audio_path.resolve()
        if not resolved_path.is_relative_to(TTS_AUDIO_DIR.resolve()):
            logger.error(f"Security: Attempted to access file outside TTS directory: {tts_audio.file_path}")
            return JsonResponse({'error': 'Invalid file path'}, status=403)
    except (ValueError, OSError):
        return JsonResponse({'error': 'Invalid file path'}, status=403)
    
    if not audio_path.exists():
        return JsonResponse({'error': 'Audio file not found on disk'}, status=404)
    
    # Stream the audio file
    response = FileResponse(open(audio_path, 'rb'), content_type='audio/mpeg')
    response['Content-Disposition'] = f'inline; filename="{audio_id}.mp3"'
    return response


@require_http_methods(["GET"])
def tts_status(request, audio_id):
    """
    Get status of a TTS audio generation.
    
    URL: /api/tts/status/<uuid>
    
    Response JSON:
    {
        "audio_id": "uuid",
        "status": "completed" | "generating" | "failed",
        "url": "/api/tts/audio/<uuid>",  // if completed
        "error": "error message"          // if failed
    }
    """
    try:
        tts_audio = TTSAudio.objects.get(id=audio_id)
    except TTSAudio.DoesNotExist:
        return JsonResponse({'error': 'Audio not found'}, status=404)
    
    response_data = {
        'audio_id': str(tts_audio.id),
        'status': tts_audio.status,
    }
    
    if tts_audio.status == 'completed':
        response_data['url'] = f'/api/tts/audio/{tts_audio.id}'
    elif tts_audio.status == 'failed':
        response_data['error'] = tts_audio.error_text
    
    return JsonResponse(response_data)
