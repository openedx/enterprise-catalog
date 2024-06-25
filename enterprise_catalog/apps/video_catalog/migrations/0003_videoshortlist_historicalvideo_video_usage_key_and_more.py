# Generated by Django 4.2.13 on 2024-06-26 10:19

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('video_catalog', '0002_alter_video_parent_content_metadata'),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoShortlist',
            fields=[
                ('video_usage_key', models.CharField(help_text='Video Xblock Usage Key', max_length=255, primary_key=True, serialize=False)),
            ],
            options={
                'verbose_name': 'Shortlisted Video',
                'verbose_name_plural': 'Shortlisted Videos',
            },
        ),
        migrations.AddField(
            model_name='historicalvideo',
            name='video_usage_key',
            field=models.CharField(default=django.utils.timezone.now, help_text='Video Xblock Usage Key', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='video',
            name='video_usage_key',
            field=models.CharField(default=django.utils.timezone.now, help_text='Video Xblock Usage Key', max_length=255),
            preserve_default=False,
        ),
    ]
