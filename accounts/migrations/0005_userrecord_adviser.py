# Generated by Django 3.1.1 on 2020-09-15 02:45

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_auto_20200827_1219'),
    ]

    operations = [
        migrations.AddField(
            model_name='userrecord',
            name='adviser',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='userrecord_adviser_set', to=settings.AUTH_USER_MODEL),
        ),
    ]
