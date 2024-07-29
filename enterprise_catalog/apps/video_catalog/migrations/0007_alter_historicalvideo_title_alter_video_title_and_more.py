# Generated by Django 4.2.14 on 2024-07-29 16:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('video_catalog', '0006_historicalvideo_title_video_title_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalvideo',
            name='title',
            field=models.CharField(default='', help_text='Video title', max_length=255),
        ),
        migrations.AlterField(
            model_name='video',
            name='title',
            field=models.CharField(default='', help_text='Video title', max_length=255),
        ),
        migrations.AlterField(
            model_name='videoshortlist',
            name='title',
            field=models.CharField(default='', help_text='Video title', max_length=255),
        ),
    ]
