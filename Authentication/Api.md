# Complete Authentication API Documentation

## Overview
এই API আপনার Django প্রজেক্টে সম্পূর্ণ authentication functionality প্রদান করে। এটি REST Framework, Simple JWT, এবং Allauth এর সাথে integrate করা।

## Base URL
```
http://your-domain.com/auth/
```

## Authentication
JWT (JSON Web Token) ব্যবহার করে authentication করা হয়। Header এ Bearer token পাঠাতে হবে:
```
Authorization: Bearer your_access_token_here
```

## Response Format
সব response consistent format এ আসবে:
```json
{
  "success": true/false,
  "message": "Success/Error message",
  "data": {},  // Optional data object
  "errors": {} // Optional errors object
}
```

## API Endpoints

### 1. User Registration
**POST** `/auth/register/`

**Request Body:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "strongPassword123",
  "password_confirm": "strongPassword123",
  "first_name": "John",
  "last_name": "Doe",
  "user_type": "customer",  // customer, dealer, admin
  "phone_number": "01712345678",  // Optional, Bangladesh format
  "address": "Dhaka, Bangladesh"  // Optional
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "User registered successfully",
  "data": {
    "user": {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "date_joined": "2025-09-07T10:30:00Z",
      "is_active": true,
      "profile": {
        "user_type": "customer",
        "phone_number": "01712345678",
        "address": "Dhaka, Bangladesh",
        "is_verified": false
      }
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  }
}
```

### 2. User Login
**POST** `/auth/login/`

**Request Body:**
```json
{
  "username_or_email": "john_doe",  // Username বা email দিতে পারেন
  "password": "strongPassword123"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "user": {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "date_joined": "2025-09-07T10:30:00Z",
      "is_active": true,
      "profile": {
        "user_type": "customer",
        "phone_number": "01712345678",
        "address": "Dhaka, Bangladesh",
        "is_verified": false
      }
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  }
}
```

### 3. User Logout
**POST** `/auth/logout/`
**Authentication Required**

**Request Body:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."  // Refresh token
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Successfully logged out"
}
```

### 4. Token Refresh
**POST** `/auth/token/refresh/`

**Request Body:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Token refreshed successfully",
  "data": {
    "tokens": {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."  // New refresh token (if ROTATE_REFRESH_TOKENS is True)
    }
  }
}
```

### 5. Verify Token
**GET** `/auth/token/verify/`
**Authentication Required**

**Response (200):**
```json
{
  "success": true,
  "valid": true,
  "data": {
    "user": {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "date_joined": "2025-09-07T10:30:00Z",
      "is_active": true,
      "profile": {
        "user_type": "customer",
        "phone_number": "01712345678",
        "address": "Dhaka, Bangladesh",
        "is_verified": false
      }
    }
  }
}
```

### 6. Get User Profile
**GET** `/auth/profile/`
**Authentication Required**

**Response (200):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "date_joined": "2025-09-07T10:30:00Z",
      "is_active": true,
      "profile": {
        "user_type": "customer",
        "phone_number": "01712345678",
        "address": "Dhaka, Bangladesh",
        "is_verified": false
      }
    }
  }
}
```

### 7. Update User Profile
**PUT/PATCH** `/auth/profile/`
**Authentication Required**

**Request Body (PATCH for partial update):**
```json
{
  "user_type": "dealer",
  "phone_number": "01798765432",
  "address": "Chittagong, Bangladesh",
  "first_name": "John Updated",
  "last_name": "Doe Updated"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "data": {
    "user": {
      // Updated user object
    }
  }
}
```

### 8. Check Username Availability
**GET** `/auth/check-username/?username=john_doe`

**Response (200):**
```json
{
  "success": true,
  "data": {
    "available": false,  // true if available
    "username": "john_doe"
  }
}
```

### 9. Check Email Availability
**GET** `/auth/check-email/?email=john@example.com`

**Response (200):**
```json
{
  "success": true,
  "data": {
    "available": false,  // true if available
    "email": "john@example.com"
  }
}
```

### 10. User Dashboard
**GET** `/auth/dashboard/`
**Authentication Required**

**Response (200):**
```json
{
  "success": true,
  "data": {
    "user": {
      // User object
    },
    "stats": {
      "user_type": "Customer",
      "is_verified": false,
      "member_since": "September 2025"
    }
  }
}
```

## Password Reset (Using dj-rest-auth)

### 11. Request Password Reset
**POST** `/auth/password/reset/`

**Request Body:**
```json
{
  "email": "john@example.com"
}
```

### 12. Confirm Password Reset
**POST** `/auth/password/reset/confirm/`

**Request Body:**
```json
{
  "uid": "encoded_user_id",
  "token": "reset_token",
  "new_password1": "newStrongPassword123",
  "new_password2": "newStrongPassword123"
}
```

### 13. Change Password
**POST** `/auth/password/change/`
**Authentication Required**

**Request Body:**
```json
{
  "old_password": "oldPassword123",
  "new_password1": "newStrongPassword123",
  "new_password2": "newStrongPassword123"
}
```

## Social Authentication (Google)

### 14. Google OAuth
**POST** `/auth/registration/google/`

**Request Body:**
```json
{
  "access_token": "google_access_token",
  "code": "google_auth_code"
}
```

## Error Responses

### Validation Error (400):
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "username": ["This field is required."],
    "password": ["This password is too short."]
  }
}
```

### Authentication Error (401):
```json
{
  "success": false,
  "message": "Authentication failed",
  "error": "Token is invalid or expired"
}
```

### Permission Error (403):
```json
{
  "success": false,
  "message": "Permission denied"
}
```

## Phone Number Format
বাংলাদেশী ফোন নাম্বারের জন্য supported formats:
- `01712345678`
- `+8801712345678`
- `+88 017 1234 5678`
- `017-1234-5678`

## Settings Configuration

আপনার `settings/base.py` ফাইলে এই configurations যোগ করুন:

```python
# Frontend URL for password reset emails
FRONTEND_URL = 'http://localhost:3000'  # Your frontend URL

# Email settings for password reset
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Your SMTP host
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'your-email@gmail.com'
```

## Usage Example (JavaScript/Frontend)

```