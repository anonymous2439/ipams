from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='accounts-register'),
    path('signup/', views.SignupView.as_view(), name='accounts-signup'),
    path('get/all/', views.get_all_accounts, name='accounts-get-all'),
    path('login/', views.login_user, name='accounts-login'),
    path('logout/', views.logout, name='accounts-logout'),
    path('profile/save/', views.save_profile, name='accounts-profile-save'),
    path('dashboard/logs', views.LogsView.as_view(), name='accounts-logs'),
]
