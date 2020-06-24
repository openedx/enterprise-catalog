# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2020-01-15 15:15


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0010_remove_catalogquery_title'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='catalogcontentkey',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='catalogcontentkey',
            name='catalog_query',
        ),
        migrations.RemoveField(
            model_name='catalogcontentkey',
            name='content_key',
        ),
        migrations.RemoveField(
            model_name='historicalcatalogcontentkey',
            name='catalog_query',
        ),
        migrations.RemoveField(
            model_name='historicalcatalogcontentkey',
            name='content_key',
        ),
        migrations.RemoveField(
            model_name='historicalcatalogcontentkey',
            name='history_user',
        ),
        migrations.AddField(
            model_name='contentmetadata',
            name='catalog_queries',
            field=models.ManyToManyField(to='catalog.CatalogQuery'),
        ),
        migrations.DeleteModel(
            name='CatalogContentKey',
        ),
        migrations.DeleteModel(
            name='HistoricalCatalogContentKey',
        ),
    ]
