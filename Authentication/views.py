from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth.models import User
from django.contrib.auth import logout

from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer, 
    ProfileUpdateSerializer
)
from .models import UserProfile
# Swagger imports
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class RegisterView(APIView):
    """User registration endpoint"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'message': 'User registered successfully',
                'data': {
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'message': 'Registration failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """User login endpoint"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'message': 'Login successful',
                'data': {
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Login failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """User logout endpoint"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            logout(request)
            return Response({
                'success': True,
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Logout failed',
                'error': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenRefreshView(TokenRefreshView):
    """Custom token refresh view with consistent response format"""
    
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            return Response({
                'success': True,
                'message': 'Token refreshed successfully',
                'data': {
                    'tokens': response.data
                }
            }, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({
                'success': False,
                'message': 'Token refresh failed',
                'error': 'Token is invalid or expired'
            }, status=status.HTTP_401_UNAUTHORIZED)


class ProfileView(RetrieveUpdateAPIView):
    """User profile view"""
    serializer_class = ProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.profile

    def get(self, request, *args, **kwargs):
        """Get user profile"""
        user = request.user
        return Response({
            'success': True,
            'data': {
                'user': UserSerializer(user).data
            }
        }, status=status.HTTP_200_OK)

    def put(self, request, *args, **kwargs):
        """Update user profile"""
        try:
            self.update(request, *args, **kwargs)
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {
                    'user': UserSerializer(request.user).data
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Profile update failed',
                'errors': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, *args, **kwargs):
        """Partially update user profile"""
        try:
            self.partial_update(request, *args, **kwargs)
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {
                    'user': UserSerializer(request.user).data
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Profile update failed',
                'errors': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def verify_token(request):
    """Verify if token is valid"""
    return Response({
        'success': True,
        'valid': True,
        'data': {
            'user': UserSerializer(request.user).data
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def check_username(request):
    """Check if username is available"""
    username = request.GET.get('username')
    if not username:
        return Response({
            'success': False,
            'message': 'Username parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exists = User.objects.filter(username=username).exists()
    return Response({
        'success': True,
        'data': {
            'available': not exists,
            'username': username
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def check_email(request):
    """Check if email is available"""
    email = request.GET.get('email')
    if not email:
        return Response({
            'success': False,
            'message': 'Email parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exists = User.objects.filter(email=email).exists()
    return Response({
        'success': True,
        'data': {
            'available': not exists,
            'email': email
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_dashboard(request):
    """User dashboard data"""
    user = request.user
    profile = user.profile
    
    # Basic dashboard stats
    dashboard_data = {
        'user': UserSerializer(user).data,
        'stats': {
            'user_type': profile.get_user_type_display(),
            'is_verified': profile.is_verified,
            'member_since': user.date_joined.strftime('%B %Y'),
        }
    }
    
    return Response({
        'success': True,
        'data': dashboard_data
    }, status=status.HTTP_200_OK)