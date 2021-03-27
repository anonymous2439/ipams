from django.urls import path
from . import views
from records import views as record_views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='accounts-register'),
    path('signup/', views.SignupView.as_view(), name='accounts-signup'),
    path('get/all/', views.get_all_accounts, name='accounts-get-all'),
    path('login/', views.login_user, name='accounts-login'),
    path('logout/', views.logout, name='accounts-logout'),
    path('profile/save/', views.save_profile, name='accounts-profile-save'),
    path('help/', views.HelpView.as_view(), name='accounts-help'),
    path('manual/', views.ManualView.as_view(), name='accounts-manual'),
    path('password/change', views.change_password, name='accounts-change-password'),
    path('profile/pending/count', views.get_pending_count, name='accounts-get-pending-count'),
]
