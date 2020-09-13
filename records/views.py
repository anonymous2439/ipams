import json
import mimetypes

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DataError, connection
from django.db.models import Count, Subquery
from django.shortcuts import render
from django.views import View
from django.http import HttpResponse, JsonResponse

from accounts.decorators import authorized_roles, authorized_record_user
from accounts.models import User, UserRole, UserRecord
from .forms import AssessmentForm, CheckedRecordForm
from .models import Record, AuthorRole, Classification, PSCEDClassification, ConferenceLevel, BudgetType, \
    CollaborationType, Author, Conference, PublicationLevel, Publication, Budget, Collaboration, CheckedRecord
from django.shortcuts import redirect
from pyexcel_xls import get_data as xls_get
from pyexcel_xlsx import get_data as xlsx_get
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from . import forms
from accounts.forms import LoginForm


class Home(View):
    name = 'records/index.html'
    
    def get(self, request):
        login_required = request.GET.get('next', False)
        context = {
            'login_required': login_required,
            'record_form': forms.RecordForm(),
            'login_form': LoginForm(),
        }
        return render(request, self.name, context)

    def post(self, request):
        if request.is_ajax():
            data = []
            checked_records = CheckedRecord.objects.filter(status='approved', checked_by__in=Subquery(User.objects.filter(role=5).values('pk')))
            records = Record.objects.filter(pk__in=Subquery(checked_records.values('record_id')))
            # graphs
            if request.POST.get('graphs'):
                basic_count = records.filter(classification=1).count()
                applied_count = records.filter(classification=2).count()
                psced_count = []
                records_per_year_count = []
                psced_per_year_count = []
                psced_classifications = PSCEDClassification.objects.all()
                records_per_year = records.values('year_accomplished').annotate(year_count=Count('year_accomplished')).order_by('year_accomplished')[:10]
                for psced in psced_classifications:
                    psced_count.append({'name': psced.name, 'count': records.filter(
                        psced_classification=PSCEDClassification.objects.get(pk=psced.id)).count()})
                for record_per_year in records_per_year:
                    records_per_year_count.append({'year': record_per_year['year_accomplished'], 'count': record_per_year['year_count']})
                with connection.cursor() as cursor:
                    cursor.execute("SELECT year_accomplished, COUNT(year_accomplished) AS year_count FROM (SELECT DISTINCT year_accomplished, psced_classification_id FROM (select year_accomplished, psced_classification_id from records_record inner join records_checkedrecord on records_record.id=record_id inner join accounts_user on records_checkedrecord.checked_by_id=accounts_user.id where accounts_user.role_id=5 and records_checkedrecord.status='approved') as recordtbl) as tbl GROUP BY year_accomplished")
                    rows = cursor.fetchall()
                    for row in rows:
                        psced_per_year_count.append({'year': row[0], 'psced_count': row[1]})
                return JsonResponse({'success': True, 'basic': basic_count, 'applied': applied_count,
                                     'psced_count': psced_count, 'records_per_year_count': records_per_year_count,
                                     'psced_per_year_count': psced_per_year_count})
            # removing records
            elif request.POST.get('remove'):
                titles = request.POST.getlist('titles[]')
                for title_id in titles:
                    del_record = Record.objects.get(pk=int(title_id))
                    del_record.abstract_file.delete()
                    del_record.delete()
                return JsonResponse({'success': True})
            # removing accounts
            elif request.POST.get('remove-accounts'):
                accounts = request.POST.getlist('accounts[]')
                success = False
                for account_id in accounts:
                    del_account = User.objects.get(pk=int(account_id))
                    if not del_account.is_superuser:
                        del_account.delete()
                        success = True
                return JsonResponse({'success': success})
            # filtering records
            elif request.POST.get('is_filtered') == 'true':
                print(request.POST)
                year_from_filter = request.POST.get('year_from', '0')
                year_to_filter = request.POST.get('year_to', '0')
                classification_filter = request.POST.get('classification')
                psced_classification_filter = request.POST.get('psced_classification')
                publication_filter = request.POST.get('publication')
                if year_from_filter != '' or year_to_filter != '':
                    records = records.filter(year_accomplished__gte=year_from_filter)\
                        .filter(year_accomplished__lte=year_to_filter)
                if classification_filter != '':
                    records = records.filter(classification=classification_filter)
                if psced_classification_filter != '':
                    records = records.filter(psced_classification=psced_classification_filter)
                if publication_filter != '':
                    publications = Publication.objects.filter(name=publication_filter)
                    if len(publications) > 0:
                        records = records.filter(publication=publications.first())
                    else:
                        records = []
            # accounts role change
            elif request.POST.get('role-change') == 'true':
                accounts = request.POST.getlist('accounts[]')
                role_id = int(request.POST.get('role-radio'))
                for account_id in accounts:
                    user = User.objects.get(pk=int(account_id))
                    user.role = UserRole.objects.get(pk=role_id)
                    user.save()
            # setting datatable records
            for record in records:
                data.append([
                    '',
                    record.pk,
                    '<a href="/record/' + str(
                    record.pk) + '">' + record.title + '</a>',
                    record.year_accomplished,
                    record.classification.name,
                    record.psced_classification.name
                ])
            return JsonResponse({"data": data})


class ViewRecord(View):
    name = 'records/view.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        'checked_record_form': checked_record_form,
    }

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_record_user())
    def get(self, request, record_id):
        checked_records = CheckedRecord.objects.filter(record=Record.objects.get(pk=record_id))
        is_removable = False
        for checked_record in checked_records:
            if checked_record.status == 'declined':
                is_removable = True
        self.context['record'] = Record.objects.get(pk=record_id)
        self.context['is_removable'] = is_removable
        return render(request, self.name, self.context)


class PendingRecordView(View):
    name = 'records/profile/view_pending.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        'checked_record_form': checked_record_form,
    }

    @method_decorator(login_required(login_url='/'))
    def get(self, request, record_id):
        checked_records = CheckedRecord.objects.filter(record=Record.objects.get(pk=record_id))
        adviser_checked = {'status': 'pending'}
        ktto_checked = {'status': 'pending'}
        rdco_checked = {'status': 'pending'}
        role_checked = False
        is_owner = False
        is_removable = False
        if request.user.role.pk > 3:
            is_removable = True
        for checked_record in checked_records:
            if checked_record.checked_by.role.id == 3:
                adviser_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == request.user.role.pk:
                role_checked=True
            if checked_record.status == 'declined':
                is_removable = True
        if UserRecord.objects.filter(user=request.user, record=Record.objects.get(pk=record_id)):
            is_owner = True
        self.context['adviser_checked'] = adviser_checked
        self.context['ktto_checked'] = ktto_checked
        self.context['rdco_checked'] = rdco_checked
        self.context['role_checked'] = role_checked
        self.context['record'] = Record.objects.get(pk=record_id)
        self.context['is_owner'] = is_owner
        self.context['is_removable'] = is_removable
        return render(request, self.name, self.context)

    def post(self, request, record_id):
        if request.is_ajax():
            # removing record
            del_record = Record.objects.get(pk=record_id)
            del_record.abstract_file.delete()
            del_record.delete()
            return JsonResponse({'success': True})
        else:
            # approving or declining record
            if request.user.role.id > 2:
                checked_record_form = CheckedRecordForm(request.POST)
                if checked_record_form.is_valid():
                    checked_record = checked_record_form.save(commit=False)
                    checked_record.checked_by = request.user
                    checked_record.record = Record.objects.get(pk=record_id)
                    checked_record.status = request.POST.get('status')
                    checked_record.save()
                else:
                    print('invalid form')
                return redirect('records-view', record_id)


class MyRecordView(View):
    name = 'records/profile/view_myrecords.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        'checked_record_form': checked_record_form,
    }

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_record_user())
    def get(self, request, record_id):
        checked_records = CheckedRecord.objects.filter(record=Record.objects.get(pk=record_id))
        adviser_checked = {'status': 'pending'}
        ktto_checked = {'status': 'pending'}
        rdco_checked = {'status': 'pending'}
        role_checked = False
        is_removable = False
        if request.user.role.pk > 3:
            is_removable = True
        for checked_record in checked_records:
            if checked_record.checked_by.role.id == 3:
                adviser_checked = {'status': checked_record.status}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record.status}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record.status}
            if checked_record.checked_by.role.id == request.user.role.pk:
                role_checked=True
            if checked_record.status == 'declined':
                is_removable = True
        if UserRecord.objects.filter(user=request.user, record=Record.objects.get(pk=record_id)):
            is_owner = True
        if adviser_checked['status'] == 'pending' and ktto_checked['status'] == 'pending' and rdco_checked['status'] == 'pending':
            is_removable = True
        self.context['adviser_checked'] = adviser_checked
        self.context['ktto_checked'] = ktto_checked
        self.context['rdco_checked'] = rdco_checked
        self.context['role_checked'] = role_checked
        self.context['record'] = Record.objects.get(pk=record_id)
        self.context['is_owner'] = is_owner
        self.context['is_removable'] = is_removable
        return render(request, self.name, self.context)

    def post(self, request, record_id):
        if request.is_ajax():
            # removing record
            del_record = Record.objects.get(pk=record_id)
            del_record.abstract_file.delete()
            del_record.delete()
            return JsonResponse({'success': True})
        else:
            # approving or declining record
            if request.user.role.id > 2:
                checked_record_form = CheckedRecordForm(request.POST)
                if checked_record_form.is_valid():
                    checked_record = checked_record_form.save(commit=False)
                    checked_record.checked_by = request.user
                    checked_record.record = Record.objects.get(pk=record_id)
                    checked_record.status = request.POST.get('status')
                    checked_record.save()
                else:
                    print('invalid form')
                return redirect('records-view', record_id)


class ApprovedRecordView(View):
    name = 'records/profile/view_approved.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        'checked_record_form': checked_record_form,
    }

    @method_decorator(login_required(login_url='/'))
    def get(self, request, record_id):
        checked_records = CheckedRecord.objects.filter(record=Record.objects.get(pk=record_id))
        adviser_checked = {'status': 'pending'}
        ktto_checked = {'status': 'pending'}
        rdco_checked = {'status': 'pending'}
        role_checked = False
        is_removable = False
        if request.user.role.pk > 3:
            is_removable = True
        for checked_record in checked_records:
            if checked_record.checked_by.role.id == 3:
                adviser_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == request.user.role.pk:
                role_checked=True
            if checked_record.status == 'declined':
                is_removable = True
        if UserRecord.objects.filter(user=request.user, record=Record.objects.get(pk=record_id)):
            is_owner = True
        self.context['adviser_checked'] = adviser_checked
        self.context['ktto_checked'] = ktto_checked
        self.context['rdco_checked'] = rdco_checked
        self.context['role_checked'] = role_checked
        self.context['record'] = Record.objects.get(pk=record_id)
        self.context['is_removable'] = is_removable
        return render(request, self.name, self.context)

    def post(self, request, record_id):
        if request.is_ajax():
            # removing record
            del_record = Record.objects.get(pk=record_id)
            del_record.abstract_file.delete()
            del_record.delete()
            return JsonResponse({'success': True})
        else:
            # approving or declining record
            if request.user.role.id > 2:
                checked_record_form = CheckedRecordForm(request.POST)
                if checked_record_form.is_valid():
                    checked_record = checked_record_form.save(commit=False)
                    checked_record.checked_by = request.user
                    checked_record.record = Record.objects.get(pk=record_id)
                    checked_record.status = request.POST.get('status')
                    checked_record.save()
                else:
                    print('invalid form')
                return redirect('records-view', record_id)


class DeclinedRecordView(View):
    name = 'records/profile/view_declined.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        'checked_record_form': checked_record_form,
    }

    @method_decorator(login_required(login_url='/'))
    def get(self, request, record_id):
        checked_records = CheckedRecord.objects.filter(record=Record.objects.get(pk=record_id))
        adviser_checked = {'status': 'pending'}
        ktto_checked = {'status': 'pending'}
        rdco_checked = {'status': 'pending'}
        role_checked = False
        is_removable = False
        if request.user.role.pk > 3:
            is_removable = True
        for checked_record in checked_records:
            if checked_record.checked_by.role.id == 3:
                adviser_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record}
            if checked_record.checked_by.role.id == request.user.role.pk:
                role_checked=True
            if checked_record.status == 'declined':
                is_removable = True
        if UserRecord.objects.filter(user=request.user, record=Record.objects.get(pk=record_id)):
            is_owner = True
        self.context['adviser_checked'] = adviser_checked
        self.context['ktto_checked'] = ktto_checked
        self.context['rdco_checked'] = rdco_checked
        self.context['role_checked'] = role_checked
        self.context['record'] = Record.objects.get(pk=record_id)
        self.context['is_removable'] = is_removable
        return render(request, self.name, self.context)

    def post(self, request, record_id):
        if request.is_ajax():
            # removing record
            del_record = Record.objects.get(pk=record_id)
            del_record.abstract_file.delete()
            del_record.delete()
            return JsonResponse({'success': True})
        else:
            # approving or declining record
            if request.user.role.id > 2:
                checked_record_form = CheckedRecordForm(request.POST)
                if checked_record_form.is_valid():
                    checked_record = checked_record_form.save(commit=False)
                    checked_record.checked_by = request.user
                    checked_record.record = Record.objects.get(pk=record_id)
                    checked_record.status = request.POST.get('status')
                    checked_record.save()
                else:
                    print('invalid form')
                return redirect('records-view', record_id)


class Add(View):
    name = 'records/add.html'
    author_roles = AuthorRole.objects.all()
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    record_form = forms.RecordForm()
    publication_form = forms.PublicationForm()
    record = Record.objects.all()

    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    @method_decorator(login_required(login_url='/'))
    def get(self, request):
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_form': self.record_form,
            'publication_form': self.publication_form,
        }
        return render(request, self.name, context)

    def post(self, request):
        error_messages = []
        record_form = forms.RecordForm(request.POST, request.FILES)
        if record_form.is_valid():
            record = record_form.save(commit=False)
            file_is_valid = True
            file = record_form.cleaned_data.get('abstract_file', False)
            if file and file.size > 5242880:
                file_is_valid = False
            else:
                record.save()
                UserRecord(user=request.user, record=record).save()
            if record is not None and file_is_valid:
                publication_form = forms.PublicationForm(request.POST)
                if publication_form.is_valid():
                    publication = publication_form.save(commit=False)
                    publication.record = record
                    publication.save()
                author_names = request.POST.getlist('author_names[]', None)
                author_roles = request.POST.getlist('author_roles[]', None)
                conference_levels = request.POST.getlist('conference_levels[]', None)
                conference_titles = request.POST.getlist('conference_titles[]', None)
                conference_dates = request.POST.getlist('conference_dates[]', None)
                conference_venues = request.POST.getlist('conference_venues[]', None)

                budget_types = request.POST.getlist('budget_types[]', None)
                budget_allocations = request.POST.getlist('budget_allocations[]', None)
                funding_sources = request.POST.getlist('funding_sources[]', None)
                industries = request.POST.getlist('industries[]', None)
                institutions = request.POST.getlist('institutions[]', None)
                collaboration_types = request.POST.getlist('collaboration_types[]', None)
                for i, author_name in enumerate(author_names):
                    Author(name=author_name, author_role=AuthorRole.objects.get(pk=author_roles[i]), record=record).save()

                for i, conference_title in enumerate(conference_titles):
                    Conference(title=conference_title,
                               conference_level=ConferenceLevel.objects.get(pk=conference_levels[i]),
                               date=conference_dates[i], venue=conference_venues[i], record=record).save()

                for i, budget_type in enumerate(budget_types):
                    Budget(budget_type=BudgetType.objects.get(pk=budget_types[i]), budget_allocation=budget_allocations[i],
                           funding_source=funding_sources[i], record=record).save()
                for i, collaboration_type in enumerate(collaboration_types):
                    Collaboration(collaboration_type=CollaborationType.objects.get(pk=collaboration_types[i]),
                                  industry=industries[i], institution=institutions[i], record=record).save()
                return redirect('records-index')
            elif not file_is_valid:
                error = {'title': 'Unable to save record',
                         'body': 'The file cannot be more than 5 MB'}
                error_messages.append(error)
            else:
                error = {'title': 'Unable to save record', 'body': 'A record with the same record information already exists'}
                error_messages.append(error)
        else:
            error_messages.append({'title': 'Unable to save record', 'body': 'Some fields contains invalid values while trying to save the record'})
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_form': self.record_form,
            'publication_form': self.publication_form,
            'error_messages': error_messages,
        }
        return render(request, self.name, context)


class ParseExcel(View):
    def post(self, request):
        try:
            excel_file = request.FILES['file']
            data = {}
            if str(excel_file).split('.')[-1] == 'xls':
                data = xls_get(excel_file, column_limit=50)
            elif str(excel_file).split('.')[-1] == 'xlsx':
                data = xlsx_get(excel_file, column_limit=50)
            data = data['ResearchProductivity'][6:][0:]
            for d in data:
                if d[0] != 'end of records':
                    title = d[1]
                    year_accomplished = d[2]
                    classification = 1
                    psced_classification = d[5]
                    if not d[3]:
                        classification = 2
                    conference_level = 1
                    conference_title = d[9]
                    conference_date = d[14]
                    conference_venue = d[15]
                    if d[11]:
                        conference_level = 2
                    elif d[12]:
                        conference_level = 3
                    elif d[13]:
                        conference_level = 4
                    record_len = len(Record.objects.filter(title=title, year_accomplished=year_accomplished,
                                                 classification=Classification.objects.get(pk=classification),
                                                 psced_classification=PSCEDClassification.objects.get(
                                                     pk=psced_classification)))
                    if record_len == 0:
                        record = Record(title=title, year_accomplished=year_accomplished,
                                        classification=Classification.objects.get(pk=classification),
                                        psced_classification=PSCEDClassification.objects.get(pk=psced_classification))
                        record.save()
                        UserRecord(record=record, user=request.user).save()
                    else:
                        continue
                    Conference(title=conference_title,
                               conference_level=ConferenceLevel.objects.get(pk=conference_level),
                               date=conference_date, venue=conference_venue, record=record).save()
                    if d[16]:
                        publication_name = d[23]
                        sn_list = "".join(d[24].split()).split(',')
                        isbn = ''
                        issn = ''
                        isi = ''
                        for sn in sn_list:
                            if sn.upper().find('ISBN:') >= 0:
                                isbn = sn.replace('ISBN:', '')
                            elif sn.upper().find('ISSN:') >= 0:
                                issn = sn.replace('ISSN:', '')
                            elif sn.upper().find('ISI:') >= 0:
                                isi = sn.replace('ISI:', '')
                        publication_level = 1
                        if d[20]:
                            publication_level = 2
                        elif d[21]:
                            publication_level = 3
                        elif d[22]:
                            publication_level = 4
                        year_published = d[18]
                        Publication(name=publication_name, isbn=isbn, issn=issn, isi=isi,
                                    publication_level=PublicationLevel.objects.get(pk=publication_level),
                                    year_published=year_published, record=record).save()
                    if d[25]:
                        budget_type = 1
                        budget_allocation = d[30]
                        funding_source = d[31]
                        if d[28]:
                            budget_type = 2
                        elif d[20]:
                            budget_type = 3
                        Budget(budget_type=BudgetType.objects.get(pk=budget_type),
                               budget_allocation=budget_allocation,
                               funding_source=funding_source, record=record).save()
                    if d[32]:
                        industry = d[34]
                        institution = d[35]
                        collaboration_type = 1
                        if len(d) >= 38:
                            if d[37]:
                                collaboration_type = 2

                        elif len(d) >= 39:
                            if d[38]:
                                collaboration_type = 3
                        Collaboration(collaboration_type=CollaborationType.objects.get(pk=collaboration_type),
                                      industry=industry, institution=institution, record=record).save()
                else:
                    break
            messages.success(request, 'Import Success!')
        except (MultiValueDictKeyError, KeyError, ValueError, OSError):
            messages.error(request, "Some rows have invalid values")
            print('Multivaluedictkeyerror/KeyError/ValueError/OSError')
        except (DataError, ValidationError):
            messages.error(request, "The form is invalid")
            print('DataError/ValidationError')
        return redirect('records-index')


@authorized_roles(roles=['adviser', 'ktto', 'rdco'])
def download_format(request):
    fl_path = '/media'
    filename = 'data.xlsx'
    fl = open('media/data.xlsx', 'rb')
    mime_type, _ = mimetypes.guess_type(fl_path)
    response = HttpResponse(fl, content_type=mime_type)
    response['Content-Disposition'] = "attachment; filename=%s" % filename
    return response


@authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco'])
def download_abstract(request, record_id):
    record = Record.objects.get(pk=record_id)
    filename = record.abstract_file.name.split('/')[-1]
    response = HttpResponse(record.abstract_file, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename=%s' % filename

    return response


class MyRecordsView(View):
    template_name = 'records/profile/my_records.html'

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        user_records = UserRecord.objects.filter(user=request.user)
        data = []
        for user_record in user_records:
            adviser_checked = f'<div class="badge badge-secondary">pending</div>'
            ktto_checked = f'<div class="badge badge-secondary">pending</div>'
            rdco_checked = f'<div class="badge badge-secondary">pending</div>'
            for checked_record in CheckedRecord.objects.filter(record=user_record.record):
                if checked_record.status == 'approved':
                    badge = 'success'
                elif checked_record.status == 'declined':
                    badge = 'danger'
                else:
                    badge = 'secondary'
                record_status = f'<div class="badge badge-{badge}">{checked_record.status}</div>'
                if checked_record.checked_by.role.pk == 3:
                    adviser_checked = record_status
                elif checked_record.checked_by.role.pk == 4:
                    ktto_checked = record_status
                elif checked_record.checked_by.role.pk == 5:
                    rdco_checked = record_status
            data.append([
                user_record.record.pk,
                '<a href="/record/myrecords/' + str(
                    user_record.record.pk) + '">' + user_record.record.title + '</a>',
                adviser_checked,
                ktto_checked,
                rdco_checked,
            ])
        return JsonResponse({"data": data})


class PendingRecordsView(View):
    template_name = 'records/profile/pending_records.html'

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        if request.user.role.id == 3:
            with connection.cursor() as cursor:
                cursor.execute("select records_record.id, records_record.title, records_checkedrecord.checked_by_id from records_record left join records_checkedrecord on records_record.id = records_checkedrecord.record_id where checked_by_id is NULL;")
                rows = cursor.fetchall()

            data = []
            for row in rows:
                data.append([
                    row[0],
                    '<a href="/record/pending/' + str(row[0]) + '">' + row[1] + '</a>',
                ])
        elif request.user.role.id == 4:
            with connection.cursor() as cursor:
                cursor.execute("SELECT records_record.id, records_record.title FROM records_record INNER JOIN records_checkedrecord ON records_record.id = records_checkedrecord.record_id INNER JOIN accounts_user ON records_checkedrecord.checked_by_id = accounts_user.id WHERE accounts_user.role_id = 3 AND records_checkedrecord.status = 'approved' AND records_record.id NOT IN (SELECT records_checkedrecord.record_id FROM records_checkedrecord INNER JOIN accounts_user ON records_checkedrecord.checked_by_id = accounts_user.id WHERE accounts_user.role_id = 4)")
                rows = cursor.fetchall()
            data = []
            for row in rows:
                data.append([
                    row[0],
                    f'<a href="/record/pending/{row[0]}">{row[1]}</a>'
                ])

        elif request.user.role.id == 5:
            with connection.cursor() as cursor:
                cursor.execute("SELECT records_record.id, records_record.title FROM records_record INNER JOIN records_checkedrecord ON records_record.id = records_checkedrecord.record_id INNER JOIN accounts_user ON records_checkedrecord.checked_by_id = accounts_user.id WHERE accounts_user.role_id = 4 AND records_checkedrecord.status = 'approved' AND records_record.id NOT IN (SELECT records_checkedrecord.record_id FROM records_checkedrecord INNER JOIN accounts_user ON records_checkedrecord.checked_by_id = accounts_user.id WHERE accounts_user.role_id = 5)")
                rows = cursor.fetchall()
            data = []
            for row in rows:
                data.append([
                    row[0],
                    f'<a href="/record/pending/{row[0]}">{row[1]}</a>'
                ])
        return JsonResponse({"data": data})


class ApprovedRecordsView(View):
    template_name = 'records/profile/approved_records.html'

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        checked_records = CheckedRecord.objects.filter(checked_by=request.user, status='approved')
        data = []
        for checked_record in checked_records:
            data.append([
                checked_record.record.pk,
                f'<a href="/record/approved/{checked_record.record.pk}">{checked_record.record.title}</a>'
            ])
        return JsonResponse({'data':data})


class DeclinedRecordsView(View):
    template_name = 'records/profile/declined_records.html'

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        checked_records = CheckedRecord.objects.filter(checked_by=request.user, status='declined')
        data = []
        for checked_record in checked_records:
            data.append([
                checked_record.record.pk,
                f'<a href="/record/declined/{checked_record.record.pk}">{checked_record.record.title}</a>'
            ])
        return JsonResponse({'data': data})
