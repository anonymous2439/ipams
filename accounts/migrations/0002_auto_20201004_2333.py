# Generated by Django 3.1.1 on 2020-10-04 15:33

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('records', '0001_initial'),
        ('accounts', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='userrecord',
            name='record',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='records.record'),
        ),
        migrations.AddField(
            model_name='userrecord',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups'),
        ),
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.ForeignKey(default=5, on_delete=django.db.models.deletion.CASCADE, to='accounts.userrole'),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions'),
        ),
    ]
