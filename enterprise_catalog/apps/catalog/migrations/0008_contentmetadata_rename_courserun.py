# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2020-01-03 17:44


import jsonfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_catalogquery_unique_content_filter'),
    ]

    operations = [
        migrations.AlterField(
            model_name='catalogquery',
            name='content_filter',
            field=jsonfield.fields.JSONField(default=dict, help_text="Query parameters which will be used to filter the discovery service's search/all endpoint results, specified as a JSON object."),
        ),
        migrations.AlterField(
            model_name='contentmetadata',
            name='content_type',
            field=models.CharField(choices=[('course', 'Course'), ('courserun', 'Course Run'), ('program', 'Program')], max_length=255),
        ),
        migrations.AlterField(
            model_name='historicalcontentmetadata',
            name='content_type',
            field=models.CharField(choices=[('course', 'Course'), ('courserun', 'Course Run'), ('program', 'Program')], max_length=255),
        ),
    ]
