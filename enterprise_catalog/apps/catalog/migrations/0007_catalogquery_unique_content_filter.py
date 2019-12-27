# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2019-12-27 18:50
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_misc_field_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogquery',
            name='content_filter_hash',
            field=models.CharField(editable=False, max_length=32, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='catalogquery',
            name='content_filter',
            field=jsonfield.fields.JSONField(default=dict, help_text="Query parameters which will be used to filter the discovery service's search/all endpoint results, specified as a JSON object. An empty JSON object means that all available content items will be included in the catalog."),
        ),
    ]
