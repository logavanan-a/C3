# Generated by Django 3.2.4 on 2022-07-14 15:45

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mis', '0016_auto_20220714_1237'),
    ]

    operations = [
        migrations.AddField(
            model_name='stakeholder',
            name='total',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stakeholder',
            name='total_female',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stakeholder',
            name='total_male',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stakeholder',
            name='user_name',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL),
        ),
    ]
