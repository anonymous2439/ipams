# Generated by Django 3.1.1 on 2020-11-27 06:47

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0003_auto_20201116_1526'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='checkedupload',
            name='status',
        ),
    ]
