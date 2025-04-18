# Generated by Django 5.2 on 2025-04-18 12:12

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recorder', '0005_transcription_generated_insight_text_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='recordingsession',
            options={'ordering': ['created_at']},
        ),
        migrations.RemoveField(
            model_name='recordingsession',
            name='name',
        ),
        migrations.CreateModel(
            name='Campaign',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaigns', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='recordingsession',
            name='campaign',
            field=models.ForeignKey(default='00000000-0000-0000-0000-000000000000', on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='recorder.campaign'),
            preserve_default=False,
        ),
    ]
