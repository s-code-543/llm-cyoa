from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0018_alter_configuration_classifier_model_and_more")]
    operations = [migrations.AddField(model_name="configuration", name="is_active", field=models.BooleanField(default=True, help_text="Published and playable by users"))]
