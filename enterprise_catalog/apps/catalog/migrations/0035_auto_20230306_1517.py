# Adding content_uuid uuid field to the content metadata table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0034_include_exec_ed_help_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentmetadata',
            name='content_uuid',
            field=models.UUIDField(blank=True, help_text='The UUID that represents a piece of content. This value is usually a secondary identifier to content_key in the enterprise environment.', null=True, verbose_name='Content UUID'),
        ),
        migrations.AddField(
            model_name='historicalcontentmetadata',
            name='content_uuid',
            field=models.UUIDField(blank=True, help_text='The UUID that represents a piece of content. This value is usually a secondary identifier to content_key in the enterprise environment.', null=True, verbose_name='Content UUID'),
        ),
    ]
