# Generated by Django 3.2.4 on 2022-09-20 17:04

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sites', '0002_alter_domain_unique'),
        ('mis', '0061_auto_20220920_1127'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportSection7',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.PositiveIntegerField(choices=[(1, 'Active'), (2, 'Inactive')], db_index=True, default=1)),
                ('server_created_on', models.DateTimeField(auto_now_add=True)),
                ('server_modified_on', models.DateTimeField(auto_now=True)),
                ('name_of_block', models.CharField(blank=True, max_length=250, null=True)),
                ('name_of_panchayat', models.CharField(blank=True, max_length=250, null=True)),
                ('name_of_village', models.CharField(blank=True, max_length=250, null=True)),
                ('school_name', models.CharField(blank=True, max_length=250, null=True)),
                ('no_of_participants', models.CharField(blank=True, max_length=250, null=True)),
                ('number_issues_discussed', models.CharField(blank=True, max_length=250, null=True)),
                ('number_decision_taken', models.CharField(blank=True, max_length=250, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='createdmis_reportsection7_related', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='modifiedmis_reportsection7_related', to=settings.AUTH_USER_MODEL)),
                ('site', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='sites.site')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='mis.task')),
            ],
            options={
                'verbose_name_plural': 'Report Section7',
            },
        ),
    ]
