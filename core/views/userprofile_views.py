from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from .base_views import CompanyFilterMixin, CompanyRequiredMixin, CompanyOwnershipMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import UserProfile, Company, Project, Task

User = get_user_model()


class UserProfileFilterForm(forms.Form):
    """Filter form for User Profiles"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by name, email, phone...',
        })
    )
    department = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Department'
        })
    )
    is_active = forms.ChoiceField(
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class UserProfileForm(forms.ModelForm):
    """Form for UserProfile with validation"""
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email'})
    )
    
    class Meta:
        model = UserProfile
        fields = [
            'company', 'phone_number', 'date_of_birth', 'gender', 'profile_picture',
            'address_line1', 'address_line2', 'city', 'state', 'zip_code', 'country',
            'designation', 'department', 'employee_id', 'joining_date',
            'bio', 'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relation', 'is_active'
        ]
        widgets = {
            'company': forms.Select(attrs={'class': 'input'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Phone Number'
            }),
            'date_of_birth': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'input'}),
            'profile_picture': forms.FileInput(attrs={'class': 'input'}),
            'address_line1': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 1'
            }),
            'address_line2': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 2'
            }),
            'city': forms.TextInput(attrs={'class': 'input', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'input', 'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'class': 'input', 'placeholder': 'ZIP'}),
            'country': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Country'}),
            'designation': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Designation'
            }),
            'department': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Department'
            }),
            'employee_id': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Employee ID'
            }),
            'joining_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'bio': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Emergency Contact Name'
            }),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Emergency Contact Phone'
            }),
            'emergency_contact_relation': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Relation'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter companies based on user's access
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
            self.fields['company'].queryset = Company.objects.filter(
                id__in=company_ids,
                is_active=True
            )
        
        # Pre-populate user fields if editing
        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
    
    def clean_employee_id(self):
        """Validate employee_id uniqueness within company"""
        employee_id = self.cleaned_data.get('employee_id')
        company = self.cleaned_data.get('company')
        
        if employee_id and company:
            existing = UserProfile.objects.filter(
                employee_id=employee_id,
                company=company
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    'Employee ID must be unique within the company.'
                )
        
        return employee_id
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        
        # Update user fields
        user = profile.user
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.email = self.cleaned_data.get('email', '')
        
        if commit:
            user.save()
            profile.save()
            self.save_m2m()
        
        return profile


class UserProfileListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List latest 10 user profiles
    Permission: core.view_userprofile
    """
    model = UserProfile
    template_name = 'core/userprofile_list.html'
    context_object_name = 'profiles'
    paginate_by = 10
    permission_required = 'core.view_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view user profiles.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('user', 'company')
        self.filter_form = UserProfileFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                search = data['search']
                queryset = queryset.filter(
                    Q(user__first_name__icontains=search) |
                    Q(user__last_name__icontains=search) |
                    Q(user__email__icontains=search) |
                    Q(user__username__icontains=search) |
                    Q(phone_number__icontains=search) |
                    Q(employee_id__icontains=search)
                )
            
            if data.get('department'):
                queryset = queryset.filter(department__icontains=data['department'])
            
            if data.get('is_active') == 'true':
                queryset = queryset.filter(is_active=True)
            elif data.get('is_active') == 'false':
                queryset = queryset.filter(is_active=False)
        
        return queryset.order_by('-created_at')[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_profiles'] = self.get_queryset().count()
        return context


class UserProfileListAllView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List all user profiles
    Permission: core.view_userprofile
    """
    model = UserProfile
    template_name = 'core/userprofile_list_all.html'
    context_object_name = 'profiles'
    paginate_by = 50
    permission_required = 'core.view_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view user profiles.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('user', 'company')
        self.filter_form = UserProfileFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                search = data['search']
                queryset = queryset.filter(
                    Q(user__first_name__icontains=search) |
                    Q(user__last_name__icontains=search) |
                    Q(user__email__icontains=search) |
                    Q(user__username__icontains=search) |
                    Q(phone_number__icontains=search) |
                    Q(employee_id__icontains=search)
                )
            
            if data.get('department'):
                queryset = queryset.filter(department__icontains=data['department'])
            
            if data.get('is_active') == 'true':
                queryset = queryset.filter(is_active=True)
            elif data.get('is_active') == 'false':
                queryset = queryset.filter(is_active=False)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_profiles'] = self.get_queryset().count()
        return context


class UserProfileCreateView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a new user profile
    Permission: core.add_userprofile
    """
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:userprofile_list')
    permission_required = 'core.add_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create user profiles.')
        return redirect('core:userprofile_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(
                self.request,
                'User Profile created successfully!'
            )
            return response
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    form.add_error(field, error)
            return self.form_invalid(form)


class UserProfileUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a user profile
    Permission: core.change_userprofile
    """
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:userprofile_list')
    permission_required = 'core.change_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update user profiles.')
        return redirect('core:userprofile_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(
                self.request,
                'User Profile updated successfully!'
            )
            return response
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    form.add_error(field, error)
            return self.form_invalid(form)


class UserProfileDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View user profile details
    Permission: core.view_userprofile
    """
    model = UserProfile
    template_name = 'form.html'
    permission_required = 'core.view_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view user profile details.')
        return redirect('core:userprofile_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()
        
        # Get statistics
        context['stats'] = {
            'managed_projects': Project.objects.filter(
                project_manager=profile.user
            ).count(),
            'led_projects': Project.objects.filter(
                technical_lead=profile.user
            ).count(),
            'assigned_tasks': Task.objects.filter(
                assigned_by=profile.user
            ).count(),
            'my_tasks': Task.objects.filter(
                assigned_to=profile.user
            ).count(),
        }
        
        # Recent activities
        context['recent_projects'] = Project.objects.filter(
            Q(project_manager=profile.user) | Q(technical_lead=profile.user)
        ).distinct().order_by('-created_at')[:5]
        
        context['recent_tasks'] = Task.objects.filter(
            assigned_to=profile.user
        ).order_by('-created_at')[:10]
        
        return context


class UserProfilePrintView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    Print user profile details
    Permission: core.view_userprofile
    """
    model = UserProfile
    template_name = 'core/userprofile_print.html'
    permission_required = 'core.view_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view user profile details.')
        return redirect('core:userprofile_list')


class UserProfileDeleteView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DeleteView):
    """
    Delete a user profile
    Permission: core.delete_userprofile
    """
    model = UserProfile
    template_name = 'core/userprofile_confirm_delete.html'
    success_url = reverse_lazy('core:userprofile_list')
    permission_required = 'core.delete_userprofile'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete user profiles.')
        return redirect('core:userprofile_list')
    
    def delete(self, request, *args, **kwargs):
        profile = self.get_object()
        profile_name = profile.get_full_name()
        messages.success(request, f'User Profile "{profile_name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)


# ==================== MY PROFILE VIEWS ====================

class MyProfileView(LoginRequiredMixin, CommonContextMixin, DetailView):
    """View own profile - No special permission required"""
    model = UserProfile
    template_name = 'core/my_profile.html'
    
    def get_object(self):
        return self.request.user.profile
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()
        
        # Get user's statistics
        managed_projects = Project.objects.filter(project_manager=self.request.user)
        led_projects = Project.objects.filter(technical_lead=self.request.user)
        assigned_tasks = Task.objects.filter(assigned_by=self.request.user)
        
        context.update({
            'managed_projects': managed_projects,
            'led_projects': led_projects,
            'total_assigned_tasks': assigned_tasks.count(),
            'pending_tasks': assigned_tasks.filter(status__in=['todo', 'in_progress']).count(),
            'completed_tasks': assigned_tasks.filter(status='completed').count(),
        })
        
        return context


class MyProfileUpdateView(LoginRequiredMixin, CommonContextMixin, UpdateView):
    """Update own profile - No special permission required"""
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:my_profile')
    
    def get_object(self):
        return self.request.user.profile
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, 'Your profile updated successfully!')
        return super().form_valid(form)