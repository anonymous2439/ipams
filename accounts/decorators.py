from django.shortcuts import redirect, render
from .models import UserRecord, User
from records.models import Record, CheckedRecord
from django.db.models import Subquery


def authorized_roles(roles=None):
    if roles is None:
        roles = []

    def decorator(view_func):
        def wrapper_func(request, *args, **kwargs):
            if request.user.is_authenticated:
                for role in roles:
                    if str.lower(request.user.role.name) == str.lower(role):
                        return view_func(request, *args, **kwargs)
                return render(request, 'accounts/unauthorized_user.html')
            return redirect('/')
        return wrapper_func
    return decorator


# authorize the owner or account above adviser
def authorized_record_user():
    def decorator(view_func):
        def wrapper_func(request, record_id, *args, **kwargs):
            checked_records = CheckedRecord.objects.filter(status='approved', checked_by__in=Subquery(User.objects.filter(role=5).values('pk')))
            records = Record.objects.filter(pk__in=Subquery(checked_records.values('record_id')))
            record = Record.objects.get(pk=record_id)
            user_records = UserRecord.objects.filter(record=record, user=request.user)
            if len(user_records) == 1 or request.user.role.name in ['KTTO', 'RDCO', 'ITSO', 'TBI'] or record in records:
                return view_func(request, record_id, *args, **kwargs)
            return render(request, 'accounts/unauthorized_user.html')
        return wrapper_func
    return decorator

