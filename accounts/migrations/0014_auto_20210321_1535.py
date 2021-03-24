# Generated by Django 3.1.5 on 2021-03-21 15:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_department_college'),
    ]

    operations = [
        migrations.AlterField(
            model_name='college',
            name='code',
            field=models.CharField(default=None, max_length=10),
        ),
        migrations.AlterField(
            model_name='college',
            name='name',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='department',
            name='code',
            field=models.CharField(default=None, max_length=10),
        ),
        migrations.AlterField(
            model_name='department',
            name='name',
            field=models.CharField(max_length=100),
        ),
    ]