from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('game', '0012_configuration_enable_tts')]
    operations = [
        migrations.CreateModel(
            name='ChatSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.UUIDField()),
                ('operation', models.CharField(max_length=16)),
                ('payload_hash', models.CharField(max_length=64)),
                ('status', models.CharField(default='pending', max_length=16)),
                ('response', models.JSONField(default=dict)),
                ('http_status', models.PositiveSmallIntegerField(default=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='game.chatconversation')),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('conversation', 'request_id'), name='unique_chat_request'),
                models.UniqueConstraint(fields=('conversation',), condition=models.Q(status='pending'), name='one_pending_chat_submission'),
            ]},
        ),
    ]
