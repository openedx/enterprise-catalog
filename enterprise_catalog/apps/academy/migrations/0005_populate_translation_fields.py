from django.db import migrations
from django.db.models import Q


def batch_update_fields(queryset, field_mapping, batch_size=500):
    """
    Helper function to update fields in batches using iterator and bulk_update.
    
    Args:
        queryset: Django queryset (can be filtered)
        field_mapping: dict mapping source field -> target field (e.g., {'title': 'title_en'})
        batch_size: number of records to process at once
    """
    records_to_update = []

    for record in queryset.iterator(chunk_size=batch_size):
        updated = False

        for source_field, target_field in field_mapping.items():
            source_value = getattr(record, source_field)
            target_value = getattr(record, target_field)

            # Only copy if target is empty but source has data
            if not target_value and source_value:
                setattr(record, target_field, source_value)
                updated = True

        if updated:
            records_to_update.append(record)

        # Bulk update when batch is full
        if len(records_to_update) >= batch_size:
            queryset.model.objects.bulk_update(
                records_to_update,
                list(field_mapping.values()),
                batch_size=batch_size
            )
            records_to_update = []

    # Update any remaining records
    if records_to_update:
        queryset.model.objects.bulk_update(
            records_to_update,
            list(field_mapping.values()),
            batch_size=batch_size
        )


def populate_translation_fields(apps, schema_editor):
    """
    Populate English translation fields from original fields for Academy and Tag models.
    """
    Academy = apps.get_model('academy', 'Academy')
    Tag = apps.get_model('academy', 'Tag')

    batch_size = 500

    # Update Academy records, only fetch those needing translation
    academy_filter = (
        Q(title_en__isnull=True) | Q(title_en='') |
        Q(short_description_en__isnull=True) | Q(short_description_en='') |
        Q(long_description_en__isnull=True) | Q(long_description_en='')
    )
    batch_update_fields(
        Academy.objects.filter(academy_filter),
        {
            'title': 'title_en',
            'short_description': 'short_description_en',
            'long_description': 'long_description_en',
        },
        batch_size
    )

    # Update Tag records, only fetch those needing translation
    tag_filter = (
        Q(title_en__isnull=True) | Q(title_en='') |
        Q(description_en__isnull=True) | Q(description_en='')
    )
    batch_update_fields(
        Tag.objects.filter(tag_filter),
        {
            'title': 'title_en',
            'description': 'description_en',
        },
        batch_size
    )


class Migration(migrations.Migration):

    dependencies = [
        ('academy', '0004_academy_long_description_en_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_translation_fields, migrations.RunPython.noop),
    ]
