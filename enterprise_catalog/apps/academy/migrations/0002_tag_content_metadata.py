# Generated by Django 4.2.7 on 2024-01-08 20:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0037_alter_historicalcontentmetadata_options_and_more'),
        ('academy', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='content_metadata',
            field=models.ManyToManyField(related_name='tags', to='catalog.contentmetadata'),
        ),
    ]
