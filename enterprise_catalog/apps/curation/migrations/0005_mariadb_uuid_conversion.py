# Generated migration for MariaDB UUID field conversion (Django 5.2)
"""
Migration to convert UUIDField from char(32) to uuid type for MariaDB compatibility.

See: https://www.albertyw.com/note/django-5-mariadb-uuidfield
"""

from django.db import migrations


def apply_mariadb_migration(apps, schema_editor):
    connection = schema_editor.connection
    
    if connection.vendor != 'mysql':
        return
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        if 'mariadb' not in version.lower():
            return
    
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE curation_enterprisecurationconfig MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_enterprisecurationconfig MODIFY enterprise_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalenterprisecurationconfig MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalenterprisecurationconfig MODIFY enterprise_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_highlightset MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalhighlightset MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_highlightedcontent MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalhighlightedcontent MODIFY uuid uuid NOT NULL")


def reverse_mariadb_migration(apps, schema_editor):
    connection = schema_editor.connection
    
    if connection.vendor != 'mysql':
        return
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        if 'mariadb' not in version.lower():
            return
    
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE curation_enterprisecurationconfig MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_enterprisecurationconfig MODIFY enterprise_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalenterprisecurationconfig MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalenterprisecurationconfig MODIFY enterprise_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_highlightset MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalhighlightset MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_highlightedcontent MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE curation_historicalhighlightedcontent MODIFY uuid char(32) NOT NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('curation', '0004_highlightedcontent_is_favorite_and_more'),
    ]

    operations = [
        migrations.RunPython(
            code=apply_mariadb_migration,
            reverse_code=reverse_mariadb_migration,
        ),
    ]
