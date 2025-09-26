from allauth.account.forms import SignupForm
from django import forms
from .models import UserProfile  # Profile মডেল ইমপোর্ট

class CustomSignupForm(SignupForm):
    phone_number = forms.CharField(max_length=15, required=False, label='ফোন নাম্বার')

    def save(self, request):
        # ডিফল্ট ইউজার সেভ করা
        user = super().save(request)
        # প্রোফাইল তৈরি করে ফোন নাম্বার সেভ করা
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data['phone_number']
        profile.save()
        return user