# Generated by Django 2.2.11 on 2020-05-01 16:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0018_update_jsonfield_formatting'),
    ]

    operations = [
        migrations.AddField(
            model_name='enterprisecatalog',
            name='enterprise_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='historicalenterprisecatalog',
            name='enterprise_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
