# Generated by Django 2.2.18 on 2021-02-24 20:56

from django.db import migrations, models
import uuid

class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0023_catalogquery_generate_uuids'),
    ]

    operations = [
        migrations.AlterField(
            model_name='catalogquery',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
