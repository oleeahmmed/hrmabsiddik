from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'authentication'

router = DefaultRouter()

urlpatterns = [
    # Custom Authentication endpoints
    # path('register/', views.RegisterView.as_view(), name='register'),
    # path('login/', views.LoginView.as_view(), name='login'),
    # path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # # Token management
    # path('token/refresh/', views.CustomTokenRefreshView.as_view(), name='token_refresh'),
    # path('token/verify/', views.verify_token, name='verify_token'),
    
    # # Profile management
    # path('profile/', views.ProfileView.as_view(), name='profile'),
    # path('dashboard/', views.user_dashboard, name='dashboard'),
    
    # # Utility endpoints
    # path('check-username/', views.check_username, name='check_username'),
    # path('check-email/', views.check_email, name='check_email'),
    
    # # Django Allauth integration for password reset and social auth
    # path('password/', include('dj_rest_auth.urls')),  # This includes password reset
    # path('registration/', include('dj_rest_auth.registration.urls')),  # Social registration
    # path('social/', include('allauth.socialaccount.urls')),  # Social auth URLs
]

urlpatterns += router.urls