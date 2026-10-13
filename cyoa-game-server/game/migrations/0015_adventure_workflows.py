from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('game', '0014_fix_arctic_playability_prompts')]
    operations = [
        migrations.AddField(model_name='configuration', name='workflow',
                            field=models.JSONField(default=dict, blank=True, help_text='Versioned turn workflow; empty uses the default')),
        migrations.AddField(model_name='gamesession', name='hidden_state', field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name='gamesession', name='workflow_snapshot', field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name='gamesession', name='random_seed', field=models.CharField(max_length=64, blank=True, default='')),
    ]
