# Generated by Django 3.2.21 on 2023-09-26 18:35

import collections
from django.db import migrations, models
import jsonfield.encoder
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0036_auto_20230306_1550'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='historicalcontentmetadata',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical Content Metadata', 'verbose_name_plural': 'historical Content Metadata'},
        ),
        migrations.AlterModelOptions(
            name='historicalenterprisecatalog',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical Enterprise Catalog', 'verbose_name_plural': 'historical Enterprise Catalogs'},
        ),
        migrations.AlterField(
            model_name='catalogquery',
            name='content_filter',
            field=jsonfield.fields.JSONField(default=dict, dump_kwargs={'cls': jsonfield.encoder.JSONEncoder, 'ensure_ascii': False, 'indent': 4, 'separators': (',', ':')}, help_text="Query parameters which will be used to filter the discovery service's search/all endpoint results, specified as a JSON object.", load_kwargs={'object_pairs_hook': collections.OrderedDict}),
        ),
        migrations.AlterField(
            model_name='contentmetadata',
            name='associated_content_metadata',
            field=models.ManyToManyField(blank=True, related_name='_catalog_contentmetadata_associated_content_metadata_+', to='catalog.ContentMetadata'),
        ),
    ]
