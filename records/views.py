import json
import mimetypes

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DataError, connection
from django.db.models import Count, Subquery, F, Q, Sum
from django.forms import modelformset_factory
from django.shortcuts import render
from django.views import View
from django.http import HttpResponse, JsonResponse

from accounts.decorators import authorized_roles, authorized_record_user
from accounts.models import User, UserRole, UserRecord, RoleRequest
from .forms import AssessmentForm, CheckedRecordForm
from .models import Record, AuthorRole, Classification, PSCEDClassification, ConferenceLevel, BudgetType, \
    CollaborationType, Author, Conference, PublicationLevel, Publication, Budget, Collaboration, CheckedRecord, Upload, \
    RecordUpload, RecordType, ResearchRecord, CheckedUpload, RecordUploadStatus
from django.shortcuts import redirect
from pyexcel_xls import get_data as xls_get
from pyexcel_xlsx import get_data as xlsx_get
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from . import forms
from accounts.forms import LoginForm


FILE_LENGTH = 5242880


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
                year_from_filter = request.POST.get('year_from', '0')
                year_to_filter = request.POST.get('year_to', '0')
                classification_filter = request.POST.get('classification')
                psced_classification_filter = request.POST.get('psced_classification')
                author_filter = request.POST.get('author')
                conference_filter = request.POST.get('conference')
                publication_filter = request.POST.get('publication')
                budget_min_filter = request.POST.get('budget_min')
                budget_max_filter = request.POST.get('budget_max')
                collaborator_filter = request.POST.get('collaborator')
                if year_from_filter != '' or year_to_filter != '':
                    records = records.filter(year_accomplished__gte=year_from_filter)\
                        .filter(year_accomplished__lte=year_to_filter)
                if classification_filter != '':
                    records = records.filter(classification=classification_filter)
                if psced_classification_filter != '':
                    records = records.filter(psced_classification=psced_classification_filter)
                if author_filter != '':
                    records = records.filter(pk__in=Author.objects.filter(name__contains=author_filter).values('record_id'))
                if conference_filter != '':
                    records = records.filter(pk__in=Conference.objects.filter(title__contains=conference_filter).values('record_id'))
                if publication_filter != '':
                    publications = Publication.objects.filter(name=publication_filter)
                    if len(publications) > 0:
                        records = records.filter(publication=publications.first())
                    else:
                        records = []
                if budget_min_filter != "" or budget_max_filter != "":
                    min = 0
                    if budget_min_filter != "":
                        min = float(budget_min_filter)
                    if budget_max_filter != "":
                        max = float(budget_max_filter)
                        records = records.filter(pk__in=Budget.objects.values('record_id').annotate(Sum('budget_allocation')).filter(budget_allocation__sum__range=(min, max)).values('record_id'))
                    else:
                        records = records.filter(pk__in=Budget.objects.values('record_id').annotate(Sum('budget_allocation')).filter(Q(budget_allocation__sum__gte=min)).values('record_id'))
                if collaborator_filter != '':
                    records = records.filter(Q(pk__in=Collaboration.objects.filter(industry__contains=collaborator_filter).values('record_id')) | Q(pk__in=Collaboration.objects.filter(institution__contains=collaborator_filter).values('record_id')))
            # accounts role change
            elif request.POST.get('role-change') == 'true':
                accounts = request.POST.getlist('accounts[]')
                role_id = int(request.POST.get('role-radio'))
                for account_id in accounts:
                    user = User.objects.get(pk=int(account_id))
                    user.role = UserRole.objects.get(pk=role_id)
                    user.save()
                    RoleRequest.objects.filter(user=user).delete()
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


class Dashboard(View):
    name = 'records/dashboard.html'

    @method_decorator(login_required(login_url='/'))
    @method_decorator(authorized_roles(roles=['ktto', 'rdco']))
    def get(self, request):
        return render(request, self.name)

    def post(self, request):
        if request.is_ajax():
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


class ViewManageDocuments(View):
    name = 'records/manage_documents.html'
    record_uploads = RecordUpload.objects.all()
    record_upload_status = RecordUploadStatus.objects.all()
    context = {
        'record_uploads': record_uploads,
        'record_upload_status': record_upload_status,
    }

    def get(self, request):
        return render(request, self.name, self.context)

    def post(self, request):
        if request.is_ajax():
            if request.POST.get('status_change', False) == 'true':
                record_upload = RecordUpload.objects.get(pk=int(request.POST.get('record_upload_id', 0)))
                record_upload.record_upload_status = RecordUploadStatus.objects.get(pk=request.POST.get('status', 0))
                record_upload.save()
                return JsonResponse({'success': True})
            else:
                data = []
                record_uploads = RecordUpload.objects.all()
                for record_upload in record_uploads:
                    data.append([record_upload.pk,
                                 record_upload.record.title,
                                 record_upload.upload.name,
                                 f'{record_upload.record_upload_status.name} <button type="button" onclick="onStatusChangeClick({record_upload.pk});">Change</button>',
                                 f'<a href="/download/document/{record_upload.pk}">Download</a>'],)
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
    # checked_uploads_status_types = CheckedUploadsStatusType.objects.all()
    uploads = Upload.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        # 'checked_uploads_status_types': checked_uploads_status_types,
        'uploads': uploads,
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

    def post(self, request, record_id):
        if request.is_ajax():
            # updating record tags
            if request.POST.get('tags_update', 'false') == 'true':
                record = Record.objects.get(pk=record_id)
                if request.POST.get('ip', 'false') == 'true':
                    record.is_ip = True
                else:
                    record.is_ip = False
                if request.POST.get('commercialization', 'false') == 'true':
                    record.for_commercialization = True
                else:
                    record.for_commercialization = False
                record.save()
                return JsonResponse({'success': True, 'is-ip': record.is_ip, 'for-commercialization': record.for_commercialization})
            # get uploaded document data
            elif request.POST.get('get_document', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                checked_uploads = CheckedUpload.objects.filter(record_upload=record_upload).order_by('-date_checked')
                comments = []
                checked_bys = []
                checked_dates = []
                for checked_upload in checked_uploads:
                    comments.append(checked_upload.comment)
                    checked_bys.append(checked_upload.checked_by.username)
                    checked_dates.append(checked_upload.date_checked)
                if record_upload is None:
                    return JsonResponse({'success': False, 'doc-title': upload.name})
                else:
                    return JsonResponse({'success': True,
                                         'doc-title': record_upload.upload.name,
                                         'doc-status': record_upload.record_upload_status.name,
                                         'is-ip': record_upload.is_ip,
                                         'for-commercialization': record_upload.for_commercialization,
                                         'comments': comments,
                                         'checked_bys': checked_bys,
                                         'checked_dates': checked_dates,
                                         'record-upload-id': record_upload.pk})
            # POSTING COMMENTS
            elif request.POST.get('post_comment', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                comment = request.POST.get('comment', '')
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                CheckedUpload(comment=comment, checked_by=request.user,
                              record_upload=record_upload).save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})


class PendingRecordView(View):
    name = 'records/profile/view_pending.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    # checked_uploads_status_types = CheckedUploadsStatusType.objects.all()
    uploads = Upload.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        # 'checked_uploads_status_types': checked_uploads_status_types,
        'uploads': uploads,
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
                adviser_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record.status, 'content': checked_record}
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
            if request.POST.get('remove', 'false') == 'true':
                del_record = Record.objects.get(pk=record_id)
                del_record.abstract_file.delete()
                del_record.delete()
                return JsonResponse({'success': True})
            # updating record tags
            elif request.POST.get('tags_update', 'false') == 'true':
                record = Record.objects.get(pk=record_id)
                if request.POST.get('ip', 'false') == 'true':
                    record.is_ip = True
                else:
                    record.is_ip = False
                if request.POST.get('commercialization', 'false') == 'true':
                    record.for_commercialization = True
                else:
                    record.for_commercialization = False
                record.save()
                return JsonResponse({'success': True, 'is-ip': record.is_ip, 'for-commercialization': record.for_commercialization})
            # get uploaded document data
            elif request.POST.get('get_document', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                checked_uploads = CheckedUpload.objects.filter(record_upload=record_upload).order_by('-date_checked')
                comments = []
                checked_bys = []
                checked_dates = []
                for checked_upload in checked_uploads:
                    comments.append(checked_upload.comment)
                    checked_bys.append(checked_upload.checked_by.username)
                    checked_dates.append(checked_upload.date_checked)
                if record_upload is None:
                    return JsonResponse({'success': False, 'doc-title': upload.name})
                else:
                    return JsonResponse({'success': True,
                                         'doc-title': record_upload.upload.name,
                                         'is-ip': record_upload.is_ip,
                                         'for-commercialization': record_upload.for_commercialization,
                                         'comments': comments,
                                         'checked_bys': checked_bys,
                                         'checked_dates': checked_dates,
                                         'record-upload-id': record_upload.pk})
            # POSTING COMMENTS
            elif request.POST.get('post_comment', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                comment = request.POST.get('comment', '')
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                CheckedUpload(comment=comment, checked_by=request.user,
                              record_upload=record_upload).save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})
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
                return redirect('records-pending')


class MyRecordView(View):
    name = 'records/profile/view_myrecords.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    # checked_uploads_status_types = CheckedUploadsStatusType.objects.all()
    uploads = Upload.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        # 'checked_uploads_status_types': checked_uploads_status_types,
        'uploads': uploads,
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
        record = Record.objects.get(pk=record_id)
        research_record = ResearchRecord.objects.filter(Q(proposal=record) | Q(research=record)).first()
        if request.user.role.pk > 3:
            is_removable = True
        for checked_record in checked_records:
            if checked_record.checked_by.role.id == 3:
                adviser_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == request.user.role.pk:
                role_checked=True
            if checked_record.status == 'declined':
                is_removable = True
        if adviser_checked['status'] == 'pending' and ktto_checked['status'] == 'pending' and rdco_checked['status'] == 'pending':
            is_removable = True
        self.context['adviser_checked'] = adviser_checked
        self.context['ktto_checked'] = ktto_checked
        self.context['rdco_checked'] = rdco_checked
        self.context['role_checked'] = role_checked
        self.context['record'] = record
        self.context['is_removable'] = is_removable
        self.context['research_record'] = research_record
        return render(request, self.name, self.context)

    def post(self, request, record_id):
        if request.is_ajax():
            # removing record
            if request.POST.get('remove', 'false') == 'true':
                del_record = Record.objects.get(pk=record_id)
                del_record.abstract_file.delete()
                del_record_uploads = RecordUpload.objects.filter(record=del_record)
                for del_record_upload in del_record_uploads:
                    del_record_upload.file.delete()
                del_record.delete()
                return JsonResponse({'success': True})
            # updating record tags
            elif request.POST.get('tags_update', 'false') == 'true':
                record = Record.objects.get(pk=record_id)
                if request.POST.get('ip', 'false') == 'true':
                    record.is_ip = True
                else:
                    record.is_ip = False
                if request.POST.get('commercialization', 'false') == 'true':
                    record.for_commercialization = True
                else:
                    record.for_commercialization = False
                record.save()
                return JsonResponse({'success': True, 'is-ip': record.is_ip, 'for-commercialization': record.for_commercialization})
            # get uploaded document data
            elif request.POST.get('get_document', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                checked_uploads = CheckedUpload.objects.filter(record_upload=record_upload).order_by('-date_checked')
                comments = []
                checked_bys = []
                checked_dates = []
                for checked_upload in checked_uploads:
                    comments.append(checked_upload.comment)
                    checked_bys.append(checked_upload.checked_by.username)
                    checked_dates.append(checked_upload.date_checked)
                if record_upload is None:
                    return JsonResponse({'success': False, 'doc-title': upload.name})
                else:
                    return JsonResponse({'success': True,
                                         'doc-title': record_upload.upload.name,
                                         'doc-status': record_upload.record_upload_status.name,
                                         'is-ip': record_upload.is_ip,
                                         'for-commercialization': record_upload.for_commercialization,
                                         'comments': comments,
                                         'checked_bys': checked_bys,
                                         'checked_dates': checked_dates,
                                         'record-upload-id': record_upload.pk})
            # POSTING COMMENTS
            elif request.POST.get('post_comment', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                comment = request.POST.get('comment', '')
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                CheckedUpload(comment=comment, checked_by=request.user, record_upload=record_upload).save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})
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
    # checked_uploads_status_types = CheckedUploadsStatusType.objects.all()
    uploads = Upload.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        # 'checked_uploads_status_types': checked_uploads_status_types,
        'uploads': uploads,
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
                adviser_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record.status, 'content': checked_record}
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
            if request.POST.get('remove', 'false') == 'true':
                del_record = Record.objects.get(pk=record_id)
                del_record.abstract_file.delete()
                del_record.delete()
                return JsonResponse({'success': True})
            # updating record tags
            elif request.POST.get('tags_update', 'false') == 'true':
                record = Record.objects.get(pk=record_id)
                if request.POST.get('ip', 'false') == 'true':
                    record.is_ip = True
                else:
                    record.is_ip = False
                if request.POST.get('commercialization', 'false') == 'true':
                    record.for_commercialization = True
                else:
                    record.for_commercialization = False
                record.save()
                return JsonResponse({'success': True, 'is-ip': record.is_ip, 'for-commercialization': record.for_commercialization})
            # get uploaded document data
            elif request.POST.get('get_document', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                checked_uploads = CheckedUpload.objects.filter(record_upload=record_upload).order_by('-date_checked')
                comments = []
                checked_bys = []
                checked_dates = []
                for checked_upload in checked_uploads:
                    comments.append(checked_upload.comment)
                    checked_bys.append(checked_upload.checked_by.username)
                    checked_dates.append(checked_upload.date_checked)
                if record_upload is None:
                    return JsonResponse({'success': False, 'doc-title': upload.name})
                else:
                    return JsonResponse({'success': True,
                                         'doc-title': record_upload.upload.name,
                                         'is-ip': record_upload.is_ip,
                                         'for-commercialization': record_upload.for_commercialization,
                                         'comments': comments,
                                         'checked_bys': checked_bys,
                                         'checked_dates': checked_dates,
                                         'record-upload-id': record_upload.pk})
            # POSTING COMMENTS
            elif request.POST.get('post_comment', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                comment = request.POST.get('comment', '')
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                CheckedUpload(comment=comment, checked_by=request.user,
                              record_upload=record_upload).save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})
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
                return redirect('records-approved')


class DeclinedRecordView(View):
    name = 'records/profile/view_declined.html'
    author_roles = AuthorRole.objects.all()
    classifications = Classification.objects.all()
    psced_classifications = PSCEDClassification.objects.all().order_by('name')
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    publication_levels = PublicationLevel.objects.all()
    # checked_uploads_status_types = CheckedUploadsStatusType.objects.all()
    uploads = Upload.objects.all()
    checked_record_form = CheckedRecordForm()
    context = {
        'author_roles': author_roles,
        'classifications': classifications,
        'psced_classifications': psced_classifications,
        'conference_levels': conference_levels,
        'budget_types': budget_types,
        'collaboration_types': collaboration_types,
        'publication_levels': publication_levels,
        # 'checked_uploads_status_types': checked_uploads_status_types,
        'uploads': uploads,
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
                adviser_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 4:
                ktto_checked = {'status': checked_record.status, 'content': checked_record}
            if checked_record.checked_by.role.id == 5:
                rdco_checked = {'status': checked_record.status, 'content': checked_record}
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
            if request.POST.get('remove', 'false') == 'true':
                del_record = Record.objects.get(pk=record_id)
                del_record.abstract_file.delete()
                del_record.delete()
                return JsonResponse({'success': True})
            # get uploaded document data
            elif request.POST.get('get_document', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                checked_uploads = CheckedUpload.objects.filter(record_upload=record_upload).order_by('-date_checked')
                comments = []
                checked_bys = []
                checked_dates = []
                for checked_upload in checked_uploads:
                    comments.append(checked_upload.comment)
                    checked_bys.append(checked_upload.checked_by.username)
                    checked_dates.append(checked_upload.date_checked)
                if record_upload is None:
                    return JsonResponse({'success': False, 'doc-title': upload.name})
                else:
                    return JsonResponse({'success': True,
                                         'doc-title': record_upload.upload.name,
                                         'is-ip': record_upload.is_ip,
                                         'for-commercialization': record_upload.for_commercialization,
                                         'comments': comments,
                                         'checked_bys': checked_bys,
                                         'checked_dates': checked_dates,
                                         'record-upload-id': record_upload.pk})
            # POSTING COMMENTS
            elif request.POST.get('post_comment', 'false') == 'true':
                upload = Upload.objects.get(pk=request.POST.get('upload_id', 0))
                record = Record.objects.get(pk=request.POST.get('record_id', 0))
                comment = request.POST.get('comment', '')
                record_upload = RecordUpload.objects.filter(upload=upload, record=record).first()
                CheckedUpload(comment=comment, checked_by=request.user,
                              record_upload=record_upload).save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})
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
                return redirect('records-declined')


class Add(View):
    name = 'records/add.html'
    author_roles = AuthorRole.objects.all()
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    record_types = RecordType.objects.all()
    record_form = forms.RecordForm()
    publication_form = forms.PublicationForm()
    uploads = Upload.objects.all()

    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    @method_decorator(login_required(login_url='/'))
    def get(self, request):
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_types': self.record_types,
            'record_form': self.record_form,
            'publication_form': self.publication_form,
            'uploads': self.uploads,
        }
        return render(request, self.name, context)

    def post(self, request):
        error_messages = []
        record_form = forms.RecordForm(request.POST, request.FILES)
        if request.is_ajax():
            if request.POST.get("get_user_tags", 'false') == 'true':
                users = []
                advisers = []
                for user in User.objects.all():
                    users.append({'value': user.username, 'id': user.pk})
                for user in User.objects.filter(role__in=[3, 4, 5]):
                    advisers.append({'value': user.username, 'id': user.pk})
                return JsonResponse({'users': users, 'advisers': advisers})
        if record_form.is_valid() and not request.is_ajax():
            record = record_form.save(commit=False)
            file_is_valid = True
            file = record_form.cleaned_data.get('abstract_file', False)
            # check uploaded file size if valid
            if file and file.size > FILE_LENGTH:
                file_is_valid = False
            # saving record to database
            else:
                owners = json.loads(request.POST.get('owners-id'))
                adviser = json.loads(request.POST.get('adviser-id'))
                record.adviser = User.objects.get(pk=adviser[0]['id'])
                record.save()
                # if the record type is proposal, the record will also be saved in the research group
                if record.record_type.pk == 1:
                    ResearchRecord(proposal=record).save()
                # patent search files check
                for upload in Upload.objects.all():
                    if request.FILES.get(f'upload-{upload.pk}', None):
                        record_upload = RecordUpload(file=request.FILES.get(f'upload-{upload.pk}', None), record=record,
                                                     upload=upload, record_upload_status=RecordUploadStatus.objects.get(pk=1)).save()
                for owner in owners:
                    UserRecord(user=User.objects.get(pk=int(owner['id'])), record=record).save()
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
            error_messages.append({'title': 'Unable to save record', 'body': 'You must fill-in all the required fields'})
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_form': record_form,
            'publication_form': self.publication_form,
            'error_messages': error_messages,
        }
        return render(request, self.name, context)


class AddResearch(View):
    name = 'records/add_research.html'
    author_roles = AuthorRole.objects.all()
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    record_types = RecordType.objects.all()
    record_form = forms.RecordForm()
    publication_form = forms.PublicationForm()
    uploads = Upload.objects.all()

    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    @method_decorator(login_required(login_url='/'))
    def get(self, request, research_record_id):
        proposal_record = ResearchRecord.objects.get(pk=research_record_id).proposal
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_types': self.record_types,
            'record_form': self.record_form,
            'publication_form': self.publication_form,
            'uploads': self.uploads,
            'proposal_record': proposal_record,
            'research_record_id': research_record_id,
        }
        return render(request, self.name, context)

    def post(self, request, research_record_id):
        error_messages = []
        record_form = forms.RecordForm(request.POST, request.FILES)
        proposal_record = ResearchRecord.objects.get(pk=research_record_id).proposal
        if request.is_ajax():
            if request.POST.get("get_user_tags", 'false') == 'true':
                users = []
                advisers = []
                for user in User.objects.all():
                    users.append({'value': user.username, 'id': user.pk})
                for user in User.objects.filter(role__in=[3, 4, 5]):
                    advisers.append({'value': user.username, 'id': user.pk})
                return JsonResponse({'users': users, 'advisers': advisers})
        if record_form.is_valid() and not request.is_ajax():
            record = record_form.save(commit=False)
            file_is_valid = True
            file = record_form.cleaned_data.get('abstract_file', False)
            # check uploaded file size if valid
            if file and file.size > FILE_LENGTH:
                file_is_valid = False
            # saving record to database
            else:
                owners = json.loads(request.POST.get('owners-id'))
                adviser = json.loads(request.POST.get('adviser-id'))
                record.adviser = User.objects.get(pk=adviser[0]['id'])
                record.save()
                research_record = ResearchRecord.objects.get(pk=research_record_id)
                research_record.research = record
                research_record.save()
                # patent search files check
                for upload in Upload.objects.all():
                    if request.FILES.get(f'upload-{upload.pk}', None):
                        record_upload = RecordUpload(file=request.FILES.get(f'upload-{upload.pk}', None), record=record,
                                                     upload=upload).save()
                for owner in owners:
                    UserRecord(user=User.objects.get(pk=int(owner['id'])), record=record).save()
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
            'record_form': record_form,
            'publication_form': self.publication_form,
            'proposal_record': proposal_record,
            'research_record_id': research_record_id,
            'error_messages': error_messages,
        }
        return render(request, self.name, context)


class Edit(View):
    name = 'records/edit.html'
    author_roles = AuthorRole.objects.all()
    conference_levels = ConferenceLevel.objects.all()
    budget_types = BudgetType.objects.all()
    collaboration_types = CollaborationType.objects.all()
    record_types = RecordType.objects.all()
    record_form = forms.RecordForm()
    publication_form = forms.PublicationForm()
    uploads = Upload.objects.all()

    @method_decorator(authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco']))
    @method_decorator(login_required(login_url='/'))
    def get(self, request, record_id):
        record = Record.objects.get(pk=record_id)
        authors = Author.objects.filter(record=record)
        conferences = Conference.objects.filter(record=record)
        budgets = Budget.objects.filter(record=record)
        collaborations = Collaboration.objects.filter(record=record)
        record_form = forms.RecordForm(instance=record)
        publication_form = forms.PublicationForm(instance=Publication.objects.get(record=record))
        publication_name = Publication.objects.get(record=record).name
        context = {
            'author_roles': self.author_roles,
            'conference_levels': self.conference_levels,
            'budget_types': self.budget_types,
            'collaboration_types': self.collaboration_types,
            'record_types': self.record_types,
            'record_form': record_form,
            'publication_form': publication_form,
            'publication_name': publication_name,
            'record': record,
            'authors': authors,
            'conferences': conferences,
            'budgets': budgets,
            'collaborations': collaborations,
            'uploads': self.uploads,
        }
        return render(request, self.name, context)

    def post(self, request, record_id):
        error_messages = []
        record_instance = Record.objects.get(pk=record_id)
        record_form = forms.RecordForm(request.POST, request.FILES, instance=Record.objects.get(pk=record_id))
        if request.is_ajax():
            if request.POST.get("get_user_tags", 'false') == 'true':
                users = []
                for user in User.objects.all():
                    users.append({'value': user.username, 'id': user.pk})
                return JsonResponse({'users': users})
        if record_form.is_valid() and not request.is_ajax():
            record = record_form.save(commit=False)
            if record is None:
                record = record_instance
            record.record_type = record_instance.record_type
            file_is_valid = True
            file = record_form.cleaned_data.get('abstract_file', False)
            # check uploaded file size if valid
            if file and file.size > FILE_LENGTH:
                file_is_valid = False
            # saving record to database
            else:
                record.save()
                # patent search files check
                for upload in Upload.objects.all():
                    if request.FILES.get(f'upload-{upload.pk}', None):
                        record_upload = RecordUpload.objects.filter(record=record, upload=upload).first()
                        if record_upload is not None:
                            record_upload.file = request.FILES.get(f'upload-{upload.pk}', None)
                            record_upload.save()
                        else:
                            record_upload = RecordUpload(file=request.FILES.get(f'upload-{upload.pk}', None), record=record,
                                                     upload=upload, record_upload_status=RecordUploadStatus.objects.get(pk=1)).save()
            if record is not None and file_is_valid:
                publication_form = forms.PublicationForm(request.POST, instance=Publication.objects.get(record=record))
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

                Author.objects.filter(record=record).delete()
                for i, author_name in enumerate(author_names):
                    Author(name=author_name, author_role=AuthorRole.objects.get(pk=author_roles[i]), record=record).save()

                Conference.objects.filter(record=record).delete()
                for i, conference_title in enumerate(conference_titles):
                    Conference(title=conference_title,
                               conference_level=ConferenceLevel.objects.get(pk=conference_levels[i]),
                               date=conference_dates[i], venue=conference_venues[i], record=record).save()

                Budget.objects.filter(record=record).delete()
                for i, budget_type in enumerate(budget_types):
                    Budget(budget_type=BudgetType.objects.get(pk=budget_types[i]), budget_allocation=budget_allocations[i],
                           funding_source=funding_sources[i], record=record).save()
                Collaboration.objects.filter(record=record).delete()
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
                    else:
                        Publication(record=record).save()
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


@authorized_roles(roles=['student', 'adviser', 'ktto', 'rdco'])
def download_document(request, record_upload_id):
    record_upload = RecordUpload.objects.get(pk=record_upload_id)
    filename = record_upload.file.name.split('/')[-1]
    response = HttpResponse(record_upload.file, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename=%s' % filename

    return response


# table view of all my records
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
                cursor.execute(f"select records_record.id, records_record.title, records_checkedrecord.checked_by_id from records_record left join records_checkedrecord on records_record.id = records_checkedrecord.record_id where checked_by_id is NULL and records_record.adviser_id = {request.user.pk}")
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
