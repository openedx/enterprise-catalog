# Generated by Django 3.2.11 on 2022-02-07 12:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0029_contentmetadatatoqueries'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contentmetadata',
            name='catalog_queries',
        ),
        migrations.AlterField(
            model_name='contentmetadata',
            name='content_type',
            field=models.CharField(choices=[('course', 'Course'), ('courserun', 'Course Run'), ('program', 'Program'), ('learnerpathway', 'Learner Pathway')], max_length=255),
        ),
        migrations.AlterField(
            model_name='historicalcontentmetadata',
            name='content_type',
            field=models.CharField(choices=[('course', 'Course'), ('courserun', 'Course Run'), ('program', 'Program'), ('learnerpathway', 'Learner Pathway')], max_length=255),
        ),
    ]
