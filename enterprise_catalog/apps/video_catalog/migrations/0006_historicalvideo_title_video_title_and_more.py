# Generated by Django 4.2.13 on 2024-07-15 14:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('video_catalog', '0005_videoshortlist_is_processed'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalvideo',
            name='title',
            field=models.CharField(blank=True, help_text='Video title', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='video',
            name='title',
            field=models.CharField(blank=True, help_text='Video title', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='videoshortlist',
            name='title',
            field=models.CharField(blank=True, help_text='Video title', max_length=255, null=True),
        ),
    ]
