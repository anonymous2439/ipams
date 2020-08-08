# Generated by Django 3.0.7 on 2020-08-06 08:33

from django.db import migrations


def insert_data(apps, schema_editor):
    Classification = apps.get_model('records', 'Classification')
    PSCEDClassification = apps.get_model('records', 'PSCEDClassification')
    CollaborationType = apps.get_model('records', 'CollaborationType')
    BudgetType = apps.get_model('records', 'BudgetType')
    ConferenceLevel = apps.get_model('records', 'ConferenceLevel')
    AuthorRole = apps.get_model('records', 'AuthorRole')
    PublicationLevel = apps.get_model('records', 'PublicationLevel')

    Classification.objects.bulk_create([
        Classification(name='Applied Research'),
        Classification(name='Basic Research'),
    ])

    BudgetType.objects.bulk_create([
        BudgetType(name='School'),
        BudgetType(name='Local'),
        BudgetType(name='Foreign'),
    ])

    ConferenceLevel.objects.bulk_create([
        ConferenceLevel(name='Regional'),
        ConferenceLevel(name='Local'),
        ConferenceLevel(name='National'),
        ConferenceLevel(name='International'),
    ])

    AuthorRole.objects.bulk_create([
        AuthorRole(name='Researcher'),
        AuthorRole(name='Adviser'),
        AuthorRole(name='Presenter'),
    ])

    CollaborationType.objects.bulk_create([
        CollaborationType(name="Academy"),
        CollaborationType(name="Government"),
        CollaborationType(name="Industry"),
    ])

    PSCEDClassification.objects.bulk_create([
        PSCEDClassification(id=66, name='Home Economics'),
        PSCEDClassification(id=58, name='Architecture and Town Planning'),
        PSCEDClassification(id=62, name='Agriculture, Forestry and Fisheries'),
        PSCEDClassification(id=34, name='Business Administration and Related'),
        PSCEDClassification(id=14, name='Education Science and Teacher Training'),
        PSCEDClassification(id=54, name='Engineering and Technology'),
        PSCEDClassification(id=18, name='Fine and Applied Arts'),
        PSCEDClassification(id=22, name='Humanities'),
        PSCEDClassification(id=38, name='Law and Jurisprudence'),
        PSCEDClassification(id=84, name='Mass Communication and Documentation'),
        PSCEDClassification(id=46, name='Mathematics'),
        PSCEDClassification(id=50, name='Medical and Allied'),
        PSCEDClassification(id=42, name='Natural Science'),
        PSCEDClassification(id=26, name='Religion and Theology'),
        PSCEDClassification(id=78, name='Service Trades'),
        PSCEDClassification(id=30, name='Social and Behavioral Sciences'),
        PSCEDClassification(id=52, name='Trade, Craft and Industrial'),
        PSCEDClassification(id=89, name='Other Disciplines'),
        PSCEDClassification(id=47, name='IT Related Disciplines'),
    ])

    PublicationLevel.objects.bulk_create([
        PublicationLevel(name='Local'),
        PublicationLevel(name='School'),
        PublicationLevel(name='National'),
        PublicationLevel(name='International'),
    ])


def delete_data(apps, schema_editor):
    Classification = apps.get_model('records', 'Classification')
    PSCEDClassification = apps.get_model('records', 'PSCEDClassification')
    CollaborationType = apps.get_model('records', 'CollaborationType')
    BudgetType = apps.get_model('records', 'BudgetType')
    ConferenceLevel = apps.get_model('records', 'ConferenceLevel')
    AuthorRole = apps.get_model('records', 'AuthorRole')
    PublicationLevel = apps.get_model('records', 'PublicationLevel')

    Classification.objects.all().delete()
    PSCEDClassification.objects.all().delete()
    CollaborationType.objects.all().delete()
    BudgetType.objects.all().delete()
    ConferenceLevel.objects.all().delete()
    AuthorRole.objects.all().delete()
    PublicationLevel.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(insert_data, delete_data)
    ]
