"""
Add user ownership to ChatConversation and GameSession.
Purges all existing chat data first since this is a fresh start with auth.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def purge_chat_data(apps, schema_editor):
    """Delete all existing conversations, messages, game sessions, and audit logs."""
    ChatMessage = apps.get_model('game', 'ChatMessage')
    ChatConversation = apps.get_model('game', 'ChatConversation')
    GameSession = apps.get_model('game', 'GameSession')
    AuditLog = apps.get_model('game', 'AuditLog')
    STTRecording = apps.get_model('game', 'STTRecording')

    counts = {
        'ChatMessage': ChatMessage.objects.all().delete()[0],
        'ChatConversation': ChatConversation.objects.all().delete()[0],
        'GameSession': GameSession.objects.all().delete()[0],
        'AuditLog': AuditLog.objects.all().delete()[0],
        'STTRecording': STTRecording.objects.all().delete()[0],
    }
    for model, count in counts.items():
        if count:
            print(f"  Purged {count} {model} rows")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('game', '0007_judgestep_cleanup_and_enhancements'),
    ]

    operations = [
        # Step 1: Purge all chat/game data (no users to preserve)
        migrations.RunPython(purge_chat_data, migrations.RunPython.noop),

        # Step 2: Add non-null user FK to ChatConversation
        migrations.AddField(
            model_name='chatconversation',
            name='user',
            field=models.ForeignKey(
                default=1,
                help_text='Owner of this conversation',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='conversations',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),

        # Step 3: Add non-null user FK to GameSession
        migrations.AddField(
            model_name='gamesession',
            name='user',
            field=models.ForeignKey(
                default=1,
                help_text='Owner of this game session',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='game_sessions',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
    ]
