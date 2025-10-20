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
        cursor.execute("ALTER TABLE catalog_catalogquery MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalog MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalog MODIFY enterprise_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_historicalenterprisecatalog MODIFY uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_historicalenterprisecatalog MODIFY enterprise_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_contentmetadata MODIFY content_uuid uuid NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalogroleassignment MODIFY enterprise_id uuid NULL")


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
        cursor.execute("ALTER TABLE catalog_catalogquery MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalog MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalog MODIFY enterprise_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_historicalenterprisecatalog MODIFY uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_historicalenterprisecatalog MODIFY enterprise_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_contentmetadata MODIFY content_uuid char(32) NOT NULL")
        cursor.execute("ALTER TABLE catalog_enterprisecatalogroleassignment MODIFY enterprise_id char(32) NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0043_restricted_course_m2m_field'),
    ]

    operations = [
        migrations.RunPython(
            code=apply_mariadb_migration,
            reverse_code=reverse_mariadb_migration,
        ),
    ]
