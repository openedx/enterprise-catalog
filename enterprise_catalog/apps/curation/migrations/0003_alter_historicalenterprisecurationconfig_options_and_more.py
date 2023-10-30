# Generated by Django 4.2.5 on 2023-10-30 07:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curation', '0002_add_can_only_view_highlight_sets'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='historicalenterprisecurationconfig',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical Enterprise curation', 'verbose_name_plural': 'historical Enterprise curations'},
        ),
        migrations.AlterModelOptions(
            name='historicalhighlightedcontent',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical highlighted content', 'verbose_name_plural': 'historical highlighted contents'},
        ),
        migrations.AlterModelOptions(
            name='historicalhighlightset',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical highlight set', 'verbose_name_plural': 'historical highlight sets'},
        ),
        migrations.AlterField(
            model_name='historicalenterprisecurationconfig',
            name='history_date',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='historicalhighlightedcontent',
            name='history_date',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='historicalhighlightset',
            name='history_date',
            field=models.DateTimeField(db_index=True),
        ),
    ]
