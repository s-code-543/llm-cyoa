"""
Management command to clean up old TTS audio files.

Usage:
    python manage.py cleanup_tts_audio [--days N] [--dry-run]

Example:
    # Clean up files older than 7 days
    python manage.py cleanup_tts_audio

    # Clean up files older than 30 days
    python manage.py cleanup_tts_audio --days 30

    # Preview what would be deleted without actually deleting
    python manage.py cleanup_tts_audio --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pathlib import Path
from django.conf import settings

from game.models import TTSAudio, TTSSettings


class Command(BaseCommand):
    help = 'Clean up old TTS audio files from disk and database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Number of days to retain files (default: use TTSSettings value)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get retention days from options or settings
        if options['days'] is not None:
            retention_days = options['days']
        else:
            tts_settings = TTSSettings.get_settings()
            retention_days = tts_settings.audio_retention_days
        
        self.stdout.write(f"Cleaning up TTS audio files older than {retention_days} days...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No files will be deleted"))
        
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        # Find old records
        old_records = TTSAudio.objects.filter(created_at__lt=cutoff_date)
        total_count = old_records.count()
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No old files to clean up"))
            return
        
        self.stdout.write(f"Found {total_count} records to process...")
        
        files_deleted = 0
        files_missing = 0
        files_failed = 0
        records_deleted = 0
        
        MEDIA_ROOT = getattr(settings, 'MEDIA_ROOT', settings.BASE_DIR / 'media')
        TTS_AUDIO_DIR = Path(MEDIA_ROOT) / 'tts_audio'
        
        for record in old_records:
            # Check if file exists
            if record.file_path:
                file_path = Path(MEDIA_ROOT) / record.file_path
                
                # Security: Verify file is within TTS_AUDIO_DIR before deleting
                try:
                    resolved_path = file_path.resolve()
                    if not resolved_path.is_relative_to(TTS_AUDIO_DIR.resolve()):
                        self.stdout.write(self.style.ERROR(f"  Security: Skipping file outside TTS directory: {record.file_path}"))
                        continue
                except (ValueError, OSError) as e:
                    self.stdout.write(self.style.ERROR(f"  Path resolution error for {record.file_path}: {e}"))
                    continue
                
                if file_path.exists():
                    if not dry_run:
                        try:
                            file_path.unlink()
                            files_deleted += 1
                            self.stdout.write(f"  Deleted: {record.file_path}")
                        except Exception as e:
                            files_failed += 1
                            self.stdout.write(self.style.ERROR(f"  Failed to delete {record.file_path}: {e}"))
                    else:
                        files_deleted += 1
                        self.stdout.write(f"  Would delete: {record.file_path}")
                else:
                    files_missing += 1
                    if not dry_run:
                        self.stdout.write(self.style.WARNING(f"  File already missing: {record.file_path}"))
            
            # Delete database record
            if not dry_run:
                try:
                    record.delete()
                    records_deleted += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Failed to delete record {record.id}: {e}"))
            else:
                records_deleted += 1
        
        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN COMPLETE:"))
            self.stdout.write(f"  Would delete {files_deleted} files")
            self.stdout.write(f"  {files_missing} files already missing")
            self.stdout.write(f"  Would remove {records_deleted} database records")
        else:
            self.stdout.write(self.style.SUCCESS(f"CLEANUP COMPLETE:"))
            self.stdout.write(f"  Deleted {files_deleted} files")
            self.stdout.write(f"  {files_missing} files already missing")
            if files_failed > 0:
                self.stdout.write(self.style.WARNING(f"  Failed to delete {files_failed} files"))
            self.stdout.write(f"  Removed {records_deleted} database records")
