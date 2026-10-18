from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('game', '0011_ttssettings')]

    operations = [
        migrations.AddField(
            model_name='configuration',
            name='enable_tts',
            field=models.BooleanField(
                default=False,
                help_text='Enable spoken narrator playback when the TTS service is configured',
            ),
        ),
    ]
