# Backfill data migration to update content_uuid values for ContentMetadata records

from django.db import migrations


def backfill_content_uuids(apps, schema_editor):
    content_metadata = apps.get_model('catalog', 'ContentMetadata')
    for metadata in content_metadata.objects.all():
        content_uuid = metadata.json_metadata.get('uuid', None)
        metadata.content_uuid = content_uuid
        metadata.save()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0035_auto_20230306_1517'),
    ]

    operations = [
        migrations.RunPython(backfill_content_uuids, reverse_code=migrations.RunPython.noop),
    ]
