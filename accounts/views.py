from django.contrib import messages
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.shortcuts import redirect
from . import forms
from .decorators import authorized_roles
from .models import User, UserRole, RoleRequest, Course
from django.db.models import Q


class RegisterView(View):
    name = 'accounts/register.html'

    def get(self, request):
        form = forms.RegistrationForm()
        return render(request, self.name, {'form': form, 'hide_profile': True})

    def post(self, request):
        form = forms.RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_password()
            if password:
                user.set_password(password)
                user.save()
                login(request, user)
                return redirect('/')
            messages.error(request, 'Password did not match!')
        else:
            if not form.cleaned_data.get('username'):
                messages.error(request, 'Username not available')
            elif not form.cleaned_data.get('email'):
                messages.error(request, 'That E-mail is already in used by another user')
            else:
                messages.error(request, 'Invalid form')
        form = forms.RegistrationForm()
        return render(request, self.name, {'form': form, 'hide_profile': True})


class SignupView(View):
    name = 'accounts/signup.html'

    def get(self, request):
        form = forms.SignupForm()
        return render(request, self.name, {'form': form, 'hide_profile': True})

    def post(self, request):
        if request.is_ajax():
            if request.POST.get("get_courses", 'false') == 'true':
                courses = []
                for course in Course.objects.all():
                    courses.append({'value': course.name, 'id': course.pk})
                return JsonResponse({'courses': courses})
            else:
                return JsonResponse({'success': 'false'})
        else:
            form = forms.SignupForm(request.POST)
            if form.is_valid():
                user = form.save(commit=False)
                password = form.cleaned_password()
                if password:
                    user.set_password(password)
                    user.role = UserRole.objects.get(pk=1)
                    user.save()
                    RoleRequest(user=user, role=UserRole.objects.get(pk=int(request.POST.get('role', 0)))).save()
                    login(request, user)
                    return redirect('/')
                error_message = 'Password did not match!'
            else:
                if not form.cleaned_data.get('username'):
                    error_message = 'Username not available'
                elif not form.cleaned_data.get('email'):
                    error_message = 'That E-mail is already in used by another user'
                else:
                    error_message = 'Invalid form'
            if error_message:
                messages.error(request, error_message)
            form = forms.RegistrationForm()
            return render(request, self.name, {'form': form, 'hide_profile': True})


def login_user(request):
    if request.method == 'POST':
        form = forms.LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                messages.success(request, f'Welcome {username}')
                if request.POST.get('next'):
                    return redirect(request.POST.get('next'))
            else:
                messages.error(request, 'Invalid Username/Password')
    return redirect('records-index')


def logout(request):
    auth_logout(request)
    messages.success(request, 'You are now logged out from the system...')
    return redirect('/')


@authorized_roles(roles=['adviser', 'ktto', 'rdco'])
def get_all_accounts(request):
    if request.method == 'POST':
        accounts = None
        if str.lower(request.user.role.name) == 'adviser':
            accounts = User.objects.filter(Q(role=UserRole.objects.get(pk=1)) | Q(role=UserRole.objects.get(pk=2)))
        else:
            accounts = User.objects.all()
        data = []
        for account in accounts:
            role = ''
            role_request = RoleRequest.objects.filter(user=account).first()
            if role_request:
                role = f'<a>{role_request.role.name}</a>'
            data.append([
                '',
                account.pk,
                str(account.username),
                f'{account.last_name}, {account.first_name} {account.last_name}',
                account.role.name,
                role,
            ])
        return JsonResponse({'data': data})


def save_profile(request):
    if request.method == 'POST':
        user = request.user
        first_name = request.POST.get('first_name')
        middle_name = request.POST.get('middle_name')
        last_name = request.POST.get('last_name')
        contact_no = request.POST.get('contact_no')
        if first_name != '':
            user.first_name = first_name
        if middle_name != '':
            user.middle_name = middle_name
        if last_name != '':
            user.last_name = last_name
        if contact_no != '':
            user.contact_no = contact_no
        user.save()
    return JsonResponse({'message': 'success'})

