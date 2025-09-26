from allauth.account.adapter import DefaultAccountAdapter
from django.contrib import messages

class CustomAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form):
          # ডিফল্ট সেভ করা
        user = super().save_user(request, user, form)
          # কাস্টম মেসেজ যোগ করা
        messages.success(request, f'ওয়েলকাম, {user.username}! তোমার ইমেল ভেরিফাই করো।')
        return user