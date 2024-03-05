# Generated by Django 4.2.9 on 2024-03-05 18:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0037_alter_historicalcontentmetadata_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='catalogquery',
            name='include_exec_ed_2u_courses',
            field=models.BooleanField(blank=True, help_text="Specifies whether the catalog is allowed to include exec ed (2U) courses.  This means that, when the content_filter specifies that 'course' content types should be included in the catalog, executive-education-2u course types won't be excluded from the content of the associated catalog.", null=True),
        ),
    ]
