# Generated by Django 3.1.1 on 2020-12-07 23:06

from django.db import migrations


def insert_data(apps, schema_editor):
    UserRole = apps.get_model("accounts", "UserRole")
    UserRole.objects.bulk_create([
        UserRole(name='Guest'),
        UserRole(name='Student'),
        UserRole(name='Adviser'),
        UserRole(name='KTTO'),
        UserRole(name='RDCO'),
    ])


def delete_data(apps, schema_editor):
    UserRole = apps.get_model('accounts', 'UserRole')
    UserRole.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20201208_0703'),
    ]

    operations = [
        migrations.RunPython(insert_data, delete_data)
    ]