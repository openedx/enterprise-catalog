# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2020-01-27 19:12
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_auto_20200115_1515'),
    ]

    operations = [
        migrations.AlterField(
            model_name='enterprisecatalog',
            name='enterprise_uuid',
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name='historicalenterprisecatalog',
            name='enterprise_uuid',
            field=models.UUIDField(db_index=True),
        ),
    ]
