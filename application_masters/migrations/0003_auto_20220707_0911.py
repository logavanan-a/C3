# Generated by Django 3.2.4 on 2022-07-07 09:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('application_masters', '0002_auto_20220705_1607'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='awc',
            options={'verbose_name_plural': 'AWC'},
        ),
        migrations.AlterModelOptions(
            name='fossilahsession',
            options={'verbose_name_plural': 'Fossil AH session'},
        ),
        migrations.AlterModelOptions(
            name='fossilahsessioncategory',
            options={'verbose_name_plural': 'Fossil AH session category'},
        ),
        migrations.AlterModelOptions(
            name='fossildlsessioncategory',
            options={'verbose_name_plural': 'Fossil DL session category'},
        ),
        migrations.AlterModelOptions(
            name='fossildlsessionconfig',
            options={'verbose_name_plural': 'Fossil DL config'},
        ),
    ]
