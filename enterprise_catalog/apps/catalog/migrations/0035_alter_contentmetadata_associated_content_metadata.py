# Generated by Django 3.2.16 on 2022-12-06 15:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0034_include_exec_ed_help_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentmetadata',
            name='associated_content_metadata',
            field=models.ManyToManyField(blank=True, related_name='_catalog_contentmetadata_associated_content_metadata_+', to='catalog.ContentMetadata'),
        ),
    ]
