# Generated by Django 4.2.9 on 2024-03-05 20:52

from django.db import connection, migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0038_alter_catalogquery_unique_together_and_more'),
    ]
    db_engine = connection.settings_dict['ENGINE']
    if 'sqlite3' in db_engine:
        operations = [
            migrations.AlterUniqueTogether(
                name='catalogquery',
                unique_together=set(),
            ),
            migrations.AlterField(
                model_name='catalogquery',
                name='content_filter_hash',
                field=models.CharField(editable=False, max_length=32, null=True, unique=True),
            ),
            migrations.RemoveField(
                model_name='catalogquery',
                name='include_exec_ed_2u_courses',
            ),
        ]
    else:
        operations = [
            migrations.AlterField(
                model_name='catalogquery',
                name='content_filter_hash',
                field=models.CharField(editable=False, max_length=32, null=True, unique=True),
            ),
            migrations.RemoveField(
                model_name='catalogquery',
                name='include_exec_ed_2u_courses',
            ),
        ]

