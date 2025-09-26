from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile
import re


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model"""
    class Meta:
        model = UserProfile
        fields = ['user_type', 'phone_number', 'address', 'is_verified']
        read_only_fields = ['is_verified']


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model with profile information"""
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                 'date_joined', 'is_active', 'profile']
        read_only_fields = ['id', 'date_joined', 'is_active']


class RegisterSerializer(serializers.ModelSerializer):
    """Enhanced registration serializer with profile fields"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    user_type = serializers.ChoiceField(
        choices=UserProfile.USER_TYPE_CHOICES, 
        default='customer'
    )
    phone_number = serializers.CharField(max_length=15, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 
                 'first_name', 'last_name', 'user_type', 'phone_number', 'address']

    def validate_username(self, value):
        """Validate username format"""
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise serializers.ValidationError(
                "Username can only contain letters, numbers, and underscores."
            )
        return value

    def validate_phone_number(self, value):
        """Validate phone number format (Bangladesh format)"""
        if value:
            # Remove spaces and common separators
            clean_number = re.sub(r'[\s\-\(\)]', '', value)
            # Check for Bangladesh phone number format
            if not re.match(r'^(\+88)?01[3-9]\d{8}$', clean_number):
                raise serializers.ValidationError(
                    "Enter a valid Bangladeshi phone number (e.g., 01712345678 or +8801712345678)"
                )
        return value

    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password_confirm": "Password fields didn't match."
            })
        return attrs

    def create(self, validated_data):
        """Create user with profile"""
        # Remove profile fields from user data
        user_type = validated_data.pop('user_type', 'customer')
        phone_number = validated_data.pop('phone_number', '')
        address = validated_data.pop('address', '')
        validated_data.pop('password_confirm')

        # Create user
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email'),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )

        # Update profile (created by signal)
        profile = user.profile
        profile.user_type = user_type
        profile.phone_number = phone_number
        profile.address = address
        profile.save()

        return user


class LoginSerializer(serializers.Serializer):
    """Enhanced login serializer"""
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Authenticate user with username or email"""
        username_or_email = attrs.get('username_or_email')
        password = attrs.get('password')

        if not username_or_email or not password:
            raise serializers.ValidationError("Must include username/email and password.")

        # Try to authenticate with username first
        user = authenticate(username=username_or_email, password=password)
        
        # If authentication fails, try with email
        if not user:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass

        if not user:
            raise serializers.ValidationError("Invalid credentials.")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        attrs['user'] = user
        return attrs


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Update user profile serializer"""
    user_type = serializers.ChoiceField(choices=UserProfile.USER_TYPE_CHOICES)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)

    class Meta:
        model = UserProfile
        fields = ['user_type', 'phone_number', 'address', 'first_name', 'last_name']

    def validate_phone_number(self, value):
        """Validate phone number format (Bangladesh format)"""
        if value:
            # Remove spaces and common separators
            clean_number = re.sub(r'[\s\-\(\)]', '', value)
            # Check for Bangladesh phone number format
            if not re.match(r'^(\+88)?01[3-9]\d{8}$', clean_number):
                raise serializers.ValidationError(
                    "Enter a valid Bangladeshi phone number (e.g., 01712345678 or +8801712345678)"
                )
        return value

    def update(self, instance, validated_data):
        """Update profile and user data"""
        # Update user fields if provided
        user_data = validated_data.pop('user', {})
        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save()

        # Update profile fields
        return super().update(instance, validated_data)