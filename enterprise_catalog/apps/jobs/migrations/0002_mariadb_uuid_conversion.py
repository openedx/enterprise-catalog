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
        cursor.execute("ALTER TABLE jobs_jobenterprise MODIFY enterprise_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE jobs_historicaljobenterprise MODIFY enterprise_uuid uuid NOT NULL")


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
        cursor.execute("ALTER TABLE jobs_jobenterprise MODIFY enterprise_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE jobs_historicaljobenterprise MODIFY enterprise_uuid char(32) NOT NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            code=apply_mariadb_migration,
            reverse_code=reverse_mariadb_migration,
        ),
    ]
