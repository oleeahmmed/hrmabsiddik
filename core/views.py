from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum, Avg, F
from django.contrib import messages
from django.utils import timezone
from django.shortcuts import redirect, get_object_or_404
from django import forms
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model

from .models import (
    Company, Project, Task, ProjectRole, ProjectMember, 
    ProjectReport, TaskComment, TaskChecklist, DailyTimeLog, UserProfile
)
from hr_payroll.models import Employee

User = get_user_model()


# ==================== Helper Mixin ====================

class CompanyFilterMixin:
    """Mixin to handle company filtering logic"""
    
    def get_user_company(self):
        """Get the user's company from UserProfile"""
        try:
            if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
                return self.request.user.profile.company
        except Exception:
            pass
        return Company.get_active_company()
    
    def filter_queryset_by_company(self, queryset):
        """Filter queryset by user's company"""
        user_company = self.get_user_company()
        if user_company:
            queryset = queryset.filter(company=user_company)
        return queryset


# ==================== USER PROFILE VIEWS ====================

class UserProfileFilterForm(forms.Form):
    """Filter form for User Profiles"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by name, email, phone...',
        })
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    department = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Department'})
    )
    is_active = forms.ChoiceField(
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class UserProfileForm(forms.ModelForm):
    """Form for UserProfile"""
    # User fields
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
            'phone_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone Number'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'input'}),
            'profile_picture': forms.FileInput(attrs={'class': 'input'}),
            'address_line1': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Address Line 1'}),
            'address_line2': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Address Line 2'}),
            'city': forms.TextInput(attrs={'class': 'input', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'input', 'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'class': 'input', 'placeholder': 'ZIP Code'}),
            'country': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Country'}),
            'designation': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Designation'}),
            'department': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Department'}),
            'employee_id': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Employee ID'}),
            'joining_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'bio': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Bio'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Emergency Contact Name'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Emergency Contact Phone'}),
            'emergency_contact_relation': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Relation'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }
    
        def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.instance and self.instance.pk:
                    # Pre-populate user fields
                    self.fields['first_name'].initial = self.instance.user.first_name
                    self.fields['last_name'].initial = self.instance.user.last_name
                    self.fields['email'].initial = self.instance.user.email
            
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


class UserProfileListView(LoginRequiredMixin, ListView):
    model = UserProfile
    template_name = 'core/userprofile_list.html'
    context_object_name = 'profiles'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = UserProfile.objects.select_related('user', 'company')
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
            
            if data.get('company'):
                queryset = queryset.filter(company=data['company'])
            
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


class UserProfileCreateView(LoginRequiredMixin, CreateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'core/userprofile_form.html'
    success_url = reverse_lazy('core:userprofile_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create User Profile'
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'User Profile created successfully!')
        return super().form_valid(form)


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'core/userprofile_form.html'
    success_url = reverse_lazy('core:userprofile_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Update User Profile'
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'User Profile updated successfully!')
        return super().form_valid(form)


class UserProfileDeleteView(LoginRequiredMixin, DeleteView):
    model = UserProfile
    template_name = 'core/userprofile_confirm_delete.html'
    success_url = reverse_lazy('core:userprofile_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'User Profile deleted successfully!')
        return super().delete(request, *args, **kwargs)


class UserProfileDetailView(LoginRequiredMixin, DetailView):
    model = UserProfile
    template_name = 'core/userprofile_detail.html'
    context_object_name = 'profile'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()
        
        # Get user's managed projects
        managed_projects = Project.objects.filter(project_manager=profile.user)
        led_projects = Project.objects.filter(technical_lead=profile.user)
        
        # Get user's assigned tasks
        assigned_tasks = Task.objects.filter(assigned_by=profile.user)
        
        # Get user's comments
        comments = TaskComment.objects.filter(commented_by=profile.user)
        
        # Get user's reports
        reports = ProjectReport.objects.filter(reported_by=profile.user)
        
        context.update({
            'managed_projects': managed_projects,
            'led_projects': led_projects,
            'assigned_tasks_count': assigned_tasks.count(),
            'comments_count': comments.count(),
            'reports_count': reports.count(),
            'age': profile.get_age(),
        })
        
        return context


class MyProfileView(LoginRequiredMixin, DetailView):
    """View for logged-in user to see their own profile"""
    model = UserProfile
    template_name = 'core/my_profile.html'
    context_object_name = 'profile'
    
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


class MyProfileUpdateView(LoginRequiredMixin, UpdateView):
    """View for logged-in user to update their own profile"""
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'core/my_profile_form.html'
    success_url = reverse_lazy('core:my_profile')
    
    def get_object(self):
        return self.request.user.profile
    
    def form_valid(self, form):
        messages.success(self.request, 'Your profile updated successfully!')
        return super().form_valid(form)


# ==================== COMPANY VIEWS ====================

class CompanyFilterForm(forms.Form):
    """Form for filtering companies"""
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by name or code...',
        })
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class CompanyForm(forms.ModelForm):
    """Form for Company - Auto-save company from user profile"""
    class Meta:
        model = Company
        fields = [
            'company_code', 'name', 'address_line1', 'address_line2', 
            'city', 'state', 'zip_code', 'country', 'phone_number', 
            'email', 'website', 'tax_id', 'currency', 
            'location_restricted', 'is_active'
        ]
        widgets = {
            'company_code': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Company Code'}),
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Company Name'}),
            'address_line1': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Address Line 1'}),
            'address_line2': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Address Line 2'}),
            'city': forms.TextInput(attrs={'class': 'input', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'input', 'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'class': 'input', 'placeholder': 'ZIP Code'}),
            'country': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Country'}),
            'phone_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email'}),
            'website': forms.URLInput(attrs={'class': 'input', 'placeholder': 'Website'}),
            'tax_id': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Tax ID'}),
            'currency': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Currency (USD, EUR)'}),
            'location_restricted': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }


class CompanyListView(LoginRequiredMixin, ListView):
    model = Company
    template_name = 'core/company_list.html'
    context_object_name = 'companies'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Company.objects.all()
        self.filter_form = CompanyFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search']) |
                    Q(company_code__icontains=data['search'])
                )
            if data.get('status') == 'active':
                queryset = queryset.filter(is_active=True)
            elif data.get('status') == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_companies'] = self.get_queryset().count()
        return context


class CompanyCreateView(LoginRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = 'core/company_form.html'
    success_url = reverse_lazy('core:company_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Auto-assign company to user's profile if they don't have one
        if hasattr(self.request.user, 'profile'):
            profile = self.request.user.profile
            if not profile.company:
                profile.company = self.object
                profile.save()
                messages.info(self.request, 'Company assigned to your profile.')
        
        messages.success(self.request, 'Company created successfully!')
        return response


class CompanyUpdateView(LoginRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = 'core/company_form.html'
    success_url = reverse_lazy('core:company_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Company updated successfully!')
        return super().form_valid(form)


class CompanyDeleteView(LoginRequiredMixin, DeleteView):
    model = Company
    template_name = 'core/company_confirm_delete.html'
    success_url = reverse_lazy('core:company_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Company deleted successfully!')
        return super().delete(request, *args, **kwargs)


class CompanyDetailView(LoginRequiredMixin, DetailView):
    model = Company
    template_name = 'core/company_detail.html'
    context_object_name = 'company'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.get_object()
        context['project_count'] = Project.objects.filter(company=company).count()
        context['recent_projects'] = Project.objects.filter(company=company).order_by('-created_at')[:5]
        context['user_profiles_count'] = UserProfile.objects.filter(company=company).count()
        return context


# ==================== PROJECT ROLE VIEWS ====================

class ProjectRoleFilterForm(forms.Form):
    """Filter form for Project Roles"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by role...',
        })
    )


class ProjectRoleForm(forms.ModelForm):
    """Form for ProjectRole"""
    class Meta:
        model = ProjectRole
        fields = ['role', 'hierarchy_level', 'description']
        widgets = {
            'role': forms.Select(attrs={'class': 'input'}),
            'hierarchy_level': forms.NumberInput(attrs={'class': 'input', 'placeholder': 'Hierarchy Level'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Description'}),
        }


class ProjectRoleListView(LoginRequiredMixin, ListView):
    model = ProjectRole
    template_name = 'core/projectrole_list.html'
    context_object_name = 'roles'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = ProjectRole.objects.all()
        self.filter_form = ProjectRoleFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            search = self.filter_form.cleaned_data.get('search')
            if search:
                queryset = queryset.filter(Q(role__icontains=search) | Q(description__icontains=search))
        
        return queryset.order_by('hierarchy_level')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        return context


class ProjectRoleCreateView(LoginRequiredMixin, CreateView):
    model = ProjectRole
    form_class = ProjectRoleForm
    template_name = 'core/projectrole_form.html'
    success_url = reverse_lazy('core:projectrole_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Role created successfully!')
        return super().form_valid(form)


class ProjectRoleUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectRole
    form_class = ProjectRoleForm
    template_name = 'core/projectrole_form.html'
    success_url = reverse_lazy('core:projectrole_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Role updated successfully!')
        return super().form_valid(form)


class ProjectRoleDeleteView(LoginRequiredMixin, DeleteView):
    model = ProjectRole
    template_name = 'core/projectrole_confirm_delete.html'
    success_url = reverse_lazy('core:projectrole_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Project Role deleted successfully!')
        return super().delete(request, *args, **kwargs)


class ProjectRoleDetailView(LoginRequiredMixin, DetailView):
    model = ProjectRole
    template_name = 'core/projectrole_detail.html'
    context_object_name = 'role'


# ==================== PROJECT VIEWS ====================

class ProjectFilterForm(forms.Form):
    """Filter form for Projects"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Search projects...'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + Project.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    priority = forms.ChoiceField(
        choices=[('', 'All Priority')] + Project.PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class ProjectForm(forms.ModelForm):
    """Form for Project - Auto-save company from user profile"""
    
    # ✅ Override fields to use User model
    technical_lead = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    project_manager = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'status', 'priority',
            'start_date', 'end_date', 'total_budget', 'spent_budget',
            'technical_lead', 'project_manager', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Project Name'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'input'}),
            'priority': forms.Select(attrs={'class': 'input'}),
            'start_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'total_budget': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
            'spent_budget': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }


class ProjectListView(LoginRequiredMixin, CompanyFilterMixin, ListView):
    model = Project
    template_name = 'core/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Project.objects.select_related('company', 'technical_lead', 'project_manager')
        queryset = self.filter_queryset_by_company(queryset)
        
        self.filter_form = ProjectFilterForm(self.request.GET)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get('search'):
                queryset = queryset.filter(Q(name__icontains=data['search']) | Q(description__icontains=data['search']))
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
        
        return queryset.order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_projects'] = self.get_queryset().count()
        return context


class ProjectCreateView(LoginRequiredMixin, CompanyFilterMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    
    def form_valid(self, form):
        # Auto-assign company from user's profile
        user_company = self.get_user_company()
        if user_company:
            form.instance.company = user_company
        
        messages.success(self.request, 'Project created successfully!')
        return super().form_valid(form)


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project updated successfully!')
        return super().form_valid(form)


class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('core:project_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Project deleted successfully!')
        return super().delete(request, *args, **kwargs)


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = 'core/project_detail.html'
    context_object_name = 'project'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        context['task_distribution'] = project.get_task_distribution()
        context['budget_status'] = project.get_budget_status()
        context['recent_tasks'] = project.tasks.order_by('-created_at')[:10]
        context['team_members'] = project.members.filter(left_date__isnull=True)
        return context


# ==================== TASK VIEWS ====================

class TaskFilterForm(forms.Form):
    """Filter form for Tasks"""
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Search tasks...'}))
    status = forms.ChoiceField(choices=[('', 'All Status')] + Task.STATUS_CHOICES, required=False, widget=forms.Select(attrs={'class': 'input'}))
    priority = forms.ChoiceField(choices=[('', 'All Priority')] + Task.PRIORITY_CHOICES, required=False, widget=forms.Select(attrs={'class': 'input'}))
    project = forms.ModelChoiceField(queryset=Project.objects.all(), required=False, widget=forms.Select(attrs={'class': 'input'}))


class TaskForm(forms.ModelForm):
    """Form for Task"""
    
    # ✅ Override assigned_by to use User model
    assigned_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    
    class Meta:
        model = Task
        fields = [
            'project', 'title', 'description', 'status', 'priority',
            'assigned_by', 'assigned_to', 'due_date', 'estimated_hours',
            'actual_hours', 'is_blocked', 'blocking_reason'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'title': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Task Title'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'input'}),
            'priority': forms.Select(attrs={'class': 'input'}),
            'assigned_to': forms.Select(attrs={'class': 'input'}),
            'due_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'estimated_hours': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
            'actual_hours': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'blocking_reason': forms.Textarea(attrs={'class': 'textarea', 'rows': 2}),
        }


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'assigned_to', 'assigned_by')
        self.filter_form = TaskFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get('search'):
                queryset = queryset.filter(Q(title__icontains=data['search']) | Q(description__icontains=data['search']))
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
        
        return queryset.order_by('due_date', '-priority')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_tasks'] = self.get_queryset().count()
        return context


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    
    def form_valid(self, form):
        # Auto-assign assigned_by to current user
        if not form.instance.assigned_by:
            form.instance.assigned_by = self.request.user
        
        messages.success(self.request, 'Task created successfully!')
        return super().form_valid(form)


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Task updated successfully!')
        return super().form_valid(form)


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Task deleted successfully!')
        return super().delete(request, *args, **kwargs)


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = 'core/task_detail.html'
    context_object_name = 'task'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        context['comments'] = task.comments.all().order_by('-created_at')
        context['time_logs'] = task.time_logs.all().order_by('-log_date')
        context['checklists'] = task.checklists.all()
        return context


# ==================== TASK COMMENT VIEWS ====================

class TaskCommentFilterForm(forms.Form):
    """Filter form for Task Comments"""
    task = forms.ModelChoiceField(
        queryset=Task.objects.all(), 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class TaskCommentForm(forms.ModelForm):
    """Form for TaskComment"""
    
    # ✅ Override commented_by to use User model
    commented_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    
    class Meta:
        model = TaskComment
        fields = ['task', 'commented_by', 'comment']
        widgets = {
            'task': forms.Select(attrs={'class': 'input'}),
            'comment': forms.Textarea(attrs={'class': 'textarea', 'rows': 4, 'placeholder': 'Add your comment...'}),
        }


class TaskCommentListView(LoginRequiredMixin, ListView):
    model = TaskComment
    template_name = 'core/taskcomment_list.html'
    context_object_name = 'comments'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = TaskComment.objects.select_related('task', 'commented_by')
        self.filter_form = TaskCommentFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            task = self.filter_form.cleaned_data.get('task')
            user = self.filter_form.cleaned_data.get('user')
            
            if task:
                queryset = queryset.filter(task=task)
            if user:
                queryset = queryset.filter(commented_by=user)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        return context


class TaskCommentCreateView(LoginRequiredMixin, CreateView):
    model = TaskComment
    form_class = TaskCommentForm
    template_name = 'core/taskcomment_form.html'
    success_url = reverse_lazy('core:taskcomment_list')
    
    def form_valid(self, form):
        # Auto-assign commented_by to current user
        if not form.instance.commented_by:
            form.instance.commented_by = self.request.user
        
        messages.success(self.request, 'Comment added successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill task if provided in URL
        task_id = self.request.GET.get('task')
        if task_id:
            initial['task'] = task_id
        return initial


class TaskCommentUpdateView(LoginRequiredMixin, UpdateView):
    model = TaskComment
    form_class = TaskCommentForm
    template_name = 'core/taskcomment_form.html'
    success_url = reverse_lazy('core:taskcomment_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Comment updated successfully!')
        return super().form_valid(form)


class TaskCommentDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskComment
    template_name = 'core/taskcomment_confirm_delete.html'
    success_url = reverse_lazy('core:taskcomment_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Comment deleted successfully!')
        return super().delete(request, *args, **kwargs)


class TaskCommentDetailView(LoginRequiredMixin, DetailView):
    model = TaskComment
    template_name = 'core/taskcomment_detail.html'
    context_object_name = 'comment'


# ==================== TASK CHECKLIST VIEWS ====================

class TaskChecklistFilterForm(forms.Form):
    """Filter form for Task Checklists"""
    status = forms.ChoiceField(
        choices=[('', 'All'), ('completed', 'Completed'), ('pending', 'Pending')],
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class TaskChecklistForm(forms.ModelForm):
    """Form for TaskChecklist"""
    class Meta:
        model = TaskChecklist
        fields = ['title', 'is_completed']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Checklist item...'}),
            'is_completed': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }


class TaskChecklistListView(LoginRequiredMixin, ListView):
    model = TaskChecklist
    template_name = 'core/taskchecklist_list.html'
    context_object_name = 'checklists'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = TaskChecklist.objects.all()
        self.filter_form = TaskChecklistFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            status = self.filter_form.cleaned_data.get('status')
            if status == 'completed':
                queryset = queryset.filter(is_completed=True)
            elif status == 'pending':
                queryset = queryset.filter(is_completed=False)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        return context


class TaskChecklistCreateView(LoginRequiredMixin, CreateView):
    model = TaskChecklist
    form_class = TaskChecklistForm
    template_name = 'core/taskchecklist_form.html'
    success_url = reverse_lazy('core:taskchecklist_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Checklist created successfully!')
        return super().form_valid(form)


class TaskChecklistUpdateView(LoginRequiredMixin, UpdateView):
    model = TaskChecklist
    form_class = TaskChecklistForm
    template_name = 'core/taskchecklist_form.html'
    success_url = reverse_lazy('core:taskchecklist_list')
    
    def form_valid(self, form):
        if form.instance.is_completed and not form.initial.get('is_completed'):
            form.instance.completed_at = timezone.now()
        messages.success(self.request, 'Checklist updated successfully!')
        return super().form_valid(form)


class TaskChecklistDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskChecklist
    template_name = 'core/taskchecklist_confirm_delete.html'
    success_url = reverse_lazy('core:taskchecklist_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Checklist deleted successfully!')
        return super().delete(request, *args, **kwargs)


class TaskChecklistDetailView(LoginRequiredMixin, DetailView):
    model = TaskChecklist
    template_name = 'core/taskchecklist_detail.html'
    context_object_name = 'checklist'


# ==================== PROJECT MEMBER VIEWS ====================

class ProjectMemberFilterForm(forms.Form):
    """Filter form for Project Members"""
    project = forms.ModelChoiceField(
        queryset=Project.objects.all(), 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    role = forms.ChoiceField(
        choices=[('', 'All Roles')] + ProjectMember.ROLE_CHOICES, 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    is_active = forms.ChoiceField(
        choices=[('', 'All'), ('active', 'Active'), ('left', 'Left')],
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class ProjectMemberForm(forms.ModelForm):
    """Form for ProjectMember"""
    class Meta:
        model = ProjectMember
        fields = ['project', 'employee', 'role', 'reporting_to', 'left_date']
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'employee': forms.Select(attrs={'class': 'input'}),
            'role': forms.Select(attrs={'class': 'input'}),
            'reporting_to': forms.Select(attrs={'class': 'input'}),
            'left_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        }


class ProjectMemberListView(LoginRequiredMixin, ListView):
    model = ProjectMember
    template_name = 'core/projectmember_list.html'
    context_object_name = 'members'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = ProjectMember.objects.select_related('project', 'employee', 'reporting_to')
        self.filter_form = ProjectMemberFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('role'):
                queryset = queryset.filter(role=data['role'])
            
            if data.get('is_active') == 'active':
                queryset = queryset.filter(left_date__isnull=True)
            elif data.get('is_active') == 'left':
                queryset = queryset.filter(left_date__isnull=False)
        
        return queryset.order_by('project', 'role')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_members'] = self.get_queryset().count()
        context['active_members'] = self.get_queryset().filter(left_date__isnull=True).count()
        return context


class ProjectMemberCreateView(LoginRequiredMixin, CreateView):
    model = ProjectMember
    form_class = ProjectMemberForm
    template_name = 'core/projectmember_form.html'
    success_url = reverse_lazy('core:projectmember_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Member added successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill project if provided in URL
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
        return initial


class ProjectMemberUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectMember
    form_class = ProjectMemberForm
    template_name = 'core/projectmember_form.html'
    success_url = reverse_lazy('core:projectmember_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Member updated successfully!')
        return super().form_valid(form)


class ProjectMemberDeleteView(LoginRequiredMixin, DeleteView):
    model = ProjectMember
    template_name = 'core/projectmember_confirm_delete.html'
    success_url = reverse_lazy('core:projectmember_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Project Member removed successfully!')
        return super().delete(request, *args, **kwargs)


class ProjectMemberDetailView(LoginRequiredMixin, DetailView):
    model = ProjectMember
    template_name = 'core/projectmember_detail.html'
    context_object_name = 'member'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.get_object()
        
        # Get member's team (subordinates)
        context['team'] = member.get_team()
        
        # Get tasks assigned to this member in the project
        context['assigned_tasks'] = Task.objects.filter(
            project=member.project,
            assigned_to=member.employee
        ).order_by('-created_at')[:10]
        
        return context


# ==================== PROJECT REPORT VIEWS ====================

class ProjectReportFilterForm(forms.Form):
    """Filter form for Project Reports"""
    project = forms.ModelChoiceField(
        queryset=Project.objects.all(), 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    reported_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    date_from = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )


class ProjectReportForm(forms.ModelForm):
    """Form for ProjectReport"""
    
    # ✅ Override reported_by to use User model
    reported_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    
    class Meta:
        model = ProjectReport
        fields = [
            'project', 'reported_by', 'report_date', 'completed_tasks',
            'pending_tasks', 'blocked_tasks', 'total_hours_logged',
            'issues_summary', 'planned_activities', 'notes', 'budget_spent_this_period'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'report_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'completed_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'pending_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'blocked_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'total_hours_logged': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
            'issues_summary': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'planned_activities': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'budget_spent_this_period': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
        }


class ProjectReportListView(LoginRequiredMixin, ListView):
    model = ProjectReport
    template_name = 'core/projectreport_list.html'
    context_object_name = 'reports'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = ProjectReport.objects.select_related('project', 'reported_by')
        self.filter_form = ProjectReportFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('reported_by'):
                queryset = queryset.filter(reported_by=data['reported_by'])
            
            if data.get('date_from'):
                queryset = queryset.filter(report_date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(report_date__lte=data['date_to'])
        
        return queryset.order_by('-report_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_reports'] = self.get_queryset().count()
        return context


class ProjectReportCreateView(LoginRequiredMixin, CreateView):
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'core/projectreport_form.html'
    success_url = reverse_lazy('core:projectreport_list')
    
    def form_valid(self, form):
        # Auto-assign reported_by to current user
        if not form.instance.reported_by:
            form.instance.reported_by = self.request.user
        
        messages.success(self.request, 'Project Report created successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill project if provided in URL
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
            initial['report_date'] = timezone.now().date()
        return initial


class ProjectReportUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'core/projectreport_form.html'
    success_url = reverse_lazy('core:projectreport_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Report updated successfully!')
        return super().form_valid(form)


class ProjectReportDeleteView(LoginRequiredMixin, DeleteView):
    model = ProjectReport
    template_name = 'core/projectreport_confirm_delete.html'
    success_url = reverse_lazy('core:projectreport_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Project Report deleted successfully!')
        return super().delete(request, *args, **kwargs)


class ProjectReportDetailView(LoginRequiredMixin, DetailView):
    model = ProjectReport
    template_name = 'core/projectreport_detail.html'
    context_object_name = 'report'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.get_object()
        
        # Calculate completion rate
        total_tasks = report.completed_tasks + report.pending_tasks + report.blocked_tasks
        if total_tasks > 0:
            context['completion_rate'] = round((report.completed_tasks / total_tasks) * 100, 2)
        else:
            context['completion_rate'] = 0
        
        return context


# ==================== DAILY TIME LOG VIEWS ====================

class DailyTimeLogFilterForm(forms.Form):
    """Filter form for Daily Time Logs"""
    task = forms.ModelChoiceField(
        queryset=Task.objects.all(), 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(), 
        required=False, 
        widget=forms.Select(attrs={'class': 'input'})
    )
    date_from = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )


class DailyTimeLogForm(forms.ModelForm):
    """Form for DailyTimeLog"""
    class Meta:
        model = DailyTimeLog
        fields = ['task', 'logged_by', 'log_date', 'hours_worked', 'description']
        widgets = {
            'task': forms.Select(attrs={'class': 'input'}),
            'logged_by': forms.Select(attrs={'class': 'input'}),
            'log_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'hours_worked': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'placeholder': 'Hours'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'What did you work on?'}),
        }


class DailyTimeLogListView(LoginRequiredMixin, ListView):
    model = DailyTimeLog
    template_name = 'core/dailytimelog_list.html'
    context_object_name = 'time_logs'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = DailyTimeLog.objects.select_related('task', 'logged_by')
        self.filter_form = DailyTimeLogFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('task'):
                queryset = queryset.filter(task=data['task'])
            
            if data.get('employee'):
                queryset = queryset.filter(logged_by=data['employee'])
            
            if data.get('date_from'):
                queryset = queryset.filter(log_date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(log_date__lte=data['date_to'])
        
        return queryset.order_by('-log_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        queryset = self.get_queryset()
        context['total_hours'] = queryset.aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0
        context['total_logs'] = queryset.count()
        return context


class DailyTimeLogCreateView(LoginRequiredMixin, CreateView):
    model = DailyTimeLog
    form_class = DailyTimeLogForm
    template_name = 'core/dailytimelog_form.html'
    success_url = reverse_lazy('core:dailytimelog_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Time log created successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill task if provided in URL
        task_id = self.request.GET.get('task')
        if task_id:
            initial['task'] = task_id
        initial['log_date'] = timezone.now().date()
        return initial


class DailyTimeLogUpdateView(LoginRequiredMixin, UpdateView):
    model = DailyTimeLog
    form_class = DailyTimeLogForm
    template_name = 'core/dailytimelog_form.html'
    success_url = reverse_lazy('core:dailytimelog_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Time log updated successfully!')
        return super().form_valid(form)


class DailyTimeLogDeleteView(LoginRequiredMixin, DeleteView):
    model = DailyTimeLog
    template_name = 'core/dailytimelog_confirm_delete.html'
    success_url = reverse_lazy('core:dailytimelog_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Time log deleted successfully!')
        return super().delete(request, *args, **kwargs)


class DailyTimeLogDetailView(LoginRequiredMixin, DetailView):
    model = DailyTimeLog
    template_name = 'core/dailytimelog_detail.html'
    context_object_name = 'time_log'


# ==================== DASHBOARD VIEWS ====================

class ProjectDashboardView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Main Project Management Dashboard"""
    template_name = 'core/project_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        projects = Project.objects.filter(company=user_company, is_active=True)
        today = timezone.now().date()
        week_end = today + timedelta(days=7)
        
        project_summaries = []
        for project in projects.select_related('technical_lead', 'project_manager'):
            project_summaries.append({
                'id': project.id,
                'name': project.name,
                'status': project.get_status_display(),
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
                'hours': float(project.get_total_hours()),
                'days_left': (project.end_date - today).days,
                'tech_lead': project.technical_lead,
                'pm': project.project_manager,
            })
        
        upcoming_tasks = Task.objects.filter(
            project__company=user_company,
            due_date__range=[today, week_end],
            status__in=['todo', 'in_progress']
        ).select_related('project', 'assigned_to').order_by('due_date')[:10]
        
        overdue_tasks = Task.objects.filter(
            project__company=user_company,
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        ).select_related('project', 'assigned_to')
        
        blocked_tasks = Task.objects.filter(
            project__company=user_company,
            is_blocked=True
        ).select_related('project', 'assigned_to')
        
        total_tasks = Task.objects.filter(project__company=user_company).count()
        completed_tasks = Task.objects.filter(project__company=user_company, status='completed').count()
        
        # User-specific statistics
        user_managed_projects = projects.filter(project_manager=self.request.user)
        user_led_projects = projects.filter(technical_lead=self.request.user)
        user_assigned_tasks = Task.objects.filter(assigned_by=self.request.user)
        
        context.update({
            'projects': projects,
            'project_summaries': project_summaries,
            'upcoming_tasks': upcoming_tasks,
            'overdue_tasks': overdue_tasks,
            'blocked_tasks': blocked_tasks,
            'stats': {
                'total_projects': projects.count(),
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'completion_rate': round((completed_tasks / total_tasks * 100), 2) if total_tasks > 0 else 0,
                'total_hours': float(Task.objects.filter(project__company=user_company).aggregate(Sum('actual_hours'))['actual_hours__sum'] or 0),
                'upcoming_count': upcoming_tasks.count(),
                'overdue_count': overdue_tasks.count(),
                'blocked_count': blocked_tasks.count(),
            },
            'user_stats': {
                'managed_projects': user_managed_projects.count(),
                'led_projects': user_led_projects.count(),
                'assigned_tasks': user_assigned_tasks.count(),
            }
        })
        
        return context


class ProjectDetailDashboardView(LoginRequiredMixin, DetailView):
    """Detailed Dashboard for Single Project"""
    model = Project
    template_name = 'core/project_detail_dashboard.html'
    context_object_name = 'project'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        today = timezone.now().date()
        
        tasks = Task.objects.filter(project=project)
        
        team_performance = []
        for member in project.members.filter(left_date__isnull=True).select_related('employee'):
            member_tasks = tasks.filter(assigned_to=member.employee)
            completed = member_tasks.filter(status='completed').count()
            total = member_tasks.count()
            
            hours = DailyTimeLog.objects.filter(
                logged_by=member.employee,
                task__project=project
            ).aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0
            
            team_performance.append({
                'member': member,
                'total_tasks': total,
                'completed_tasks': completed,
                'completion_rate': round((completed / total * 100), 2) if total > 0 else 0,
                'hours_logged': float(hours),
                'pending_tasks': member_tasks.filter(status__in=['todo', 'in_progress']).count(),
            })
        
        weekly_trend = []
        for i in range(7):
            day = today - timedelta(days=6-i)
            day_tasks_created = tasks.filter(created_at__date=day).count()
            day_tasks_completed = tasks.filter(completed_at__date=day).count()
            day_hours = DailyTimeLog.objects.filter(
                log_date=day,
                task__project=project
            ).aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0
            
            weekly_trend.append({
                'date': day,
                'created': day_tasks_created,
                'completed': day_tasks_completed,
                'hours': float(day_hours),
            })
        
        reports = ProjectReport.objects.filter(project=project).order_by('-report_date')[:5]
        
        context.update({
            'team_performance': team_performance,
            'weekly_trend': weekly_trend,
            'recent_reports': reports,
            'task_distribution': project.get_task_distribution(),
            'budget_status': project.get_budget_status(),
            'upcoming_tasks': project.get_upcoming_tasks(days=7),
            'overdue_tasks': project.get_overdue_tasks(),
            'blocked_tasks': project.get_blocked_tasks(),
        })
        
        return context


class WeeklyProgressReportView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Weekly Progress Report"""
    template_name = 'core/weekly_progress_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        projects = Project.objects.filter(company=user_company, is_active=True)
        
        daily_data = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            daily_data.append({
                'date': day,
                'day_name': day.strftime('%A'),
                'tasks_created': Task.objects.filter(created_at__date=day, project__company=user_company).count(),
                'tasks_completed': Task.objects.filter(completed_at__date=day, project__company=user_company).count(),
                'total_hours': float(DailyTimeLog.objects.filter(log_date=day, task__project__company=user_company).aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0),
            })
        
        project_week_data = []
        for project in projects:
            tasks = Task.objects.filter(project=project)
            completed_this_week = tasks.filter(completed_at__date__range=[week_start, week_end]).count()
            hours_this_week = float(DailyTimeLog.objects.filter(
                log_date__range=[week_start, week_end],
                task__project=project
            ).aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0)
            
            project_week_data.append({
                'project': project,
                'completed': completed_this_week,
                'hours': hours_this_week,
                'progress': project.get_progress_percentage(),
            })
        
        context.update({
            'week_start': week_start,
            'week_end': week_end,
            'daily_data': daily_data,
            'project_week_data': project_week_data,
            'total_week_hours': sum([d['total_hours'] for d in daily_data]),
            'total_week_completed': sum([d['tasks_completed'] for d in daily_data]),
        })
        
        return context


class TeamPerformanceView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Team Performance Analysis"""
    template_name = 'core/team_performance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        team_stats = []
        employees = Employee.objects.filter(company=user_company, is_active=True)
        
        for employee in employees:
            tasks = Task.objects.filter(assigned_to=employee)
            completed = tasks.filter(status='completed').count()
            total = tasks.count()
            hours = float(DailyTimeLog.objects.filter(logged_by=employee).aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0)
            
            # Calculate efficiency
            efficiency = 0
            if completed > 0:
                completed_tasks = tasks.filter(status='completed')
                total_efficiency = sum([task.get_efficiency_ratio() for task in completed_tasks])
                efficiency = total_efficiency / completed
            
            if total > 0:
                team_stats.append({
                    'employee': employee,
                    'total_tasks': total,
                    'completed': completed,
                    'pending': total - completed,
                    'completion_rate': round((completed / total * 100), 2),
                    'hours_logged': hours,
                    'avg_hours_per_task': round(hours / total, 2) if total > 0 else 0,
                    'efficiency': round(efficiency, 2),
                })
        
        team_stats.sort(key=lambda x: x['completion_rate'], reverse=True)
        
        context.update({
            'team_stats': team_stats,
            'total_team_members': len(team_stats),
            'avg_completion_rate': round(sum([s['completion_rate'] for s in team_stats]) / len(team_stats), 2) if team_stats else 0,
            'total_hours': sum([s['hours_logged'] for s in team_stats]),
        })
        
        return context


class BudgetAnalysisView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Budget Analysis and Expense Tracking"""
    template_name = 'core/budget_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        projects = Project.objects.filter(company=user_company, total_budget__isnull=False)
        
        budget_data = []
        total_budget = 0
        total_spent = 0
        
        for project in projects:
            status = project.get_budget_status()
            budget_data.append({
                'project': project,
                'total_budget': project.total_budget,
                'spent': project.spent_budget,
                'remaining': status['remaining'],
                'usage_percent': status['percentage_used'],
                'is_over_budget': status['is_over_budget'],
            })
            
            total_budget += float(project.total_budget or 0)
            total_spent += float(project.spent_budget or 0)
        
        context.update({
            'budget_data': budget_data,
            'total_budget': total_budget,
            'total_spent': total_spent,
            'total_remaining': total_budget - total_spent,
            'overall_usage': round((total_spent / total_budget * 100), 2) if total_budget > 0 else 0,
            'over_budget_projects': sum(1 for d in budget_data if d['is_over_budget']),
        })
        
        return context


class MyTasksView(LoginRequiredMixin, TemplateView):
    """My Tasks Dashboard - User's assigned tasks"""
    template_name = 'core/my_tasks.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Try to get employee associated with user
        try:
            employee = Employee.objects.get(user=self.request.user)
            my_tasks = Task.objects.filter(assigned_to=employee)
        except Employee.DoesNotExist:
            my_tasks = Task.objects.none()
        
        today = timezone.now().date()
        
        # Tasks I've assigned to others
        assigned_by_me = Task.objects.filter(assigned_by=self.request.user)
        
        context.update({
            'todo_tasks': my_tasks.filter(status='todo').order_by('due_date'),
            'in_progress_tasks': my_tasks.filter(status='in_progress').order_by('due_date'),
            'completed_tasks': my_tasks.filter(status='completed').order_by('-completed_at')[:10],
            'overdue_tasks': my_tasks.filter(due_date__lt=today, status__in=['todo', 'in_progress']),
            'blocked_tasks': my_tasks.filter(is_blocked=True),
            'assigned_by_me': assigned_by_me.order_by('-created_at')[:10],
            'stats': {
                'total': my_tasks.count(),
                'todo': my_tasks.filter(status='todo').count(),
                'in_progress': my_tasks.filter(status='in_progress').count(),
                'completed': my_tasks.filter(status='completed').count(),
                'overdue': my_tasks.filter(due_date__lt=today, status__in=['todo', 'in_progress']).count(),
                'blocked': my_tasks.filter(is_blocked=True).count(),
            }
        })
        
        return context


class MyProjectsView(LoginRequiredMixin, TemplateView):
    """My Projects Dashboard - Projects I manage or lead"""
    template_name = 'core/my_projects.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Projects where I'm project manager
        managed_projects = Project.objects.filter(
            project_manager=self.request.user,
            is_active=True
        ).select_related('company', 'technical_lead')
        
        # Projects where I'm technical lead
        led_projects = Project.objects.filter(
            technical_lead=self.request.user,
            is_active=True
        ).select_related('company', 'project_manager')
        
        # Get statistics for managed projects
        managed_summaries = []
        for project in managed_projects:
            managed_summaries.append({
                'project': project,
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
            })
        
        # Get statistics for led projects
        led_summaries = []
        for project in led_projects:
            led_summaries.append({
                'project': project,
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
            })
        
        context.update({
            'managed_projects': managed_projects,
            'led_projects': led_projects,
            'managed_summaries': managed_summaries,
            'led_summaries': led_summaries,
            'stats': {
                'total_managed': managed_projects.count(),
                'total_led': led_projects.count(),
                'total_projects': managed_projects.count() + led_projects.count(),
            }
        })
        
        return context


class TimeLogReportView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Time Log Report - Detailed time tracking analysis"""
    template_name = 'core/timelog_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        # Date range from request or default to last 30 days
        date_to = self.request.GET.get('date_to')
        date_from = self.request.GET.get('date_from')
        
        if date_to:
            date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
        else:
            date_to = timezone.now().date()
        
        if date_from:
            date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
        else:
            date_from = date_to - timedelta(days=30)
        
        # Get all time logs in date range
        time_logs = DailyTimeLog.objects.filter(
            task__project__company=user_company,
            log_date__range=[date_from, date_to]
        ).select_related('task', 'logged_by')
        
        # Group by employee
        employee_hours = {}
        for log in time_logs:
            if log.logged_by not in employee_hours:
                employee_hours[log.logged_by] = {
                    'employee': log.logged_by,
                    'total_hours': 0,
                    'days_logged': set(),
                    'tasks': set(),
                }
            employee_hours[log.logged_by]['total_hours'] += float(log.hours_worked)
            employee_hours[log.logged_by]['days_logged'].add(log.log_date)
            employee_hours[log.logged_by]['tasks'].add(log.task)
        
        # Convert to list and calculate averages
        employee_stats = []
        for emp_data in employee_hours.values():
            days_count = len(emp_data['days_logged'])
            employee_stats.append({
                'employee': emp_data['employee'],
                'total_hours': round(emp_data['total_hours'], 2),
                'days_logged': days_count,
                'avg_hours_per_day': round(emp_data['total_hours'] / days_count, 2) if days_count > 0 else 0,
                'tasks_count': len(emp_data['tasks']),
            })
        
        employee_stats.sort(key=lambda x: x['total_hours'], reverse=True)
        
        # Group by project
        project_hours = {}
        for log in time_logs:
            project = log.task.project
            if project not in project_hours:
                project_hours[project] = 0
            project_hours[project] += float(log.hours_worked)
        
        project_stats = [
            {'project': project, 'hours': round(hours, 2)}
            for project, hours in sorted(project_hours.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Daily breakdown
        daily_breakdown = []
        current_date = date_from
        while current_date <= date_to:
            day_logs = time_logs.filter(log_date=current_date)
            daily_hours = day_logs.aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0
            daily_breakdown.append({
                'date': current_date,
                'hours': float(daily_hours),
                'logs_count': day_logs.count(),
            })
            current_date += timedelta(days=1)
        
        total_hours = time_logs.aggregate(Sum('hours_worked'))['hours_worked__sum'] or 0
        
        context.update({
            'date_from': date_from,
            'date_to': date_to,
            'employee_stats': employee_stats,
            'project_stats': project_stats,
            'daily_breakdown': daily_breakdown,
            'total_hours': float(total_hours),
            'total_logs': time_logs.count(),
            'avg_hours_per_day': round(float(total_hours) / len(daily_breakdown), 2) if daily_breakdown else 0,
        })
        
        return context


class TaskStatusReportView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Task Status Report - Overview of all tasks"""
    template_name = 'core/task_status_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        all_tasks = Task.objects.filter(project__company=user_company)
        today = timezone.now().date()
        
        # Status breakdown
        status_breakdown = {
            'todo': all_tasks.filter(status='todo').count(),
            'in_progress': all_tasks.filter(status='in_progress').count(),
            'on_hold': all_tasks.filter(status='on_hold').count(),
            'completed': all_tasks.filter(status='completed').count(),
            'cancelled': all_tasks.filter(status='cancelled').count(),
        }
        
        # Priority breakdown
        priority_breakdown = {
            'low': all_tasks.filter(priority='low').count(),
            'medium': all_tasks.filter(priority='medium').count(),
            'high': all_tasks.filter(priority='high').count(),
            'critical': all_tasks.filter(priority='critical').count(),
        }
        
        # Overdue tasks by priority
        overdue_tasks = all_tasks.filter(
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        )
        
        overdue_by_priority = {
            'low': overdue_tasks.filter(priority='low').count(),
            'medium': overdue_tasks.filter(priority='medium').count(),
            'high': overdue_tasks.filter(priority='high').count(),
            'critical': overdue_tasks.filter(priority='critical').count(),
        }
        
        # Tasks by project
        project_task_stats = []
        projects = Project.objects.filter(company=user_company, is_active=True)
        
        for project in projects:
            project_tasks = all_tasks.filter(project=project)
            total = project_tasks.count()
            completed = project_tasks.filter(status='completed').count()
            
            project_task_stats.append({
                'project': project,
                'total': total,
                'completed': completed,
                'pending': total - completed,
                'overdue': project_tasks.filter(due_date__lt=today, status__in=['todo', 'in_progress']).count(),
                'blocked': project_tasks.filter(is_blocked=True).count(),
                'completion_rate': round((completed / total * 100), 2) if total > 0 else 0,
            })
        
        project_task_stats.sort(key=lambda x: x['completion_rate'], reverse=True)
        
        # Upcoming deadlines (next 7 days)
        upcoming_deadline = today + timedelta(days=7)
        upcoming_tasks = all_tasks.filter(
            due_date__range=[today, upcoming_deadline],
            status__in=['todo', 'in_progress']
        ).order_by('due_date')
        
        context.update({
            'total_tasks': all_tasks.count(),
            'status_breakdown': status_breakdown,
            'priority_breakdown': priority_breakdown,
            'overdue_by_priority': overdue_by_priority,
            'project_task_stats': project_task_stats,
            'upcoming_tasks': upcoming_tasks[:20],
            'blocked_tasks': all_tasks.filter(is_blocked=True),
        })
        
        return context


class EmployeeWorkloadView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Employee Workload Analysis"""
    template_name = 'core/employee_workload.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        employees = Employee.objects.filter(company=user_company, is_active=True)
        
        workload_data = []
        for employee in employees:
            tasks = Task.objects.filter(assigned_to=employee)
            active_tasks = tasks.filter(status__in=['todo', 'in_progress'])
            
            # Calculate estimated remaining hours
            estimated_remaining = active_tasks.aggregate(
                total=Sum('estimated_hours')
            )['total'] or 0
            
            # Get upcoming tasks (next 7 days)
            today = timezone.now().date()
            upcoming = active_tasks.filter(
                due_date__range=[today, today + timedelta(days=7)]
            ).count()
            
            # Get overdue tasks
            overdue = active_tasks.filter(due_date__lt=today).count()
            
            # Calculate workload score (simple metric)
            workload_score = (
                active_tasks.count() * 1 +
                upcoming * 2 +
                overdue * 3 +
                float(estimated_remaining) * 0.1
            )
            
            workload_data.append({
                'employee': employee,
                'active_tasks': active_tasks.count(),
                'completed_tasks': tasks.filter(status='completed').count(),
                'upcoming_tasks': upcoming,
                'overdue_tasks': overdue,
                'blocked_tasks': tasks.filter(is_blocked=True).count(),
                'estimated_remaining': float(estimated_remaining),
                'workload_score': round(workload_score, 2),
            })
        
        # Sort by workload score
        workload_data.sort(key=lambda x: x['workload_score'], reverse=True)
        
        context.update({
            'workload_data': workload_data,
            'total_employees': len(workload_data),
            'avg_workload': round(sum(w['workload_score'] for w in workload_data) / len(workload_data), 2) if workload_data else 0,
        })
        
        return context


class ProjectComparisonView(LoginRequiredMixin, CompanyFilterMixin, TemplateView):
    """Compare multiple projects side by side"""
    template_name = 'core/project_comparison.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_company = self.get_user_company()
        
        # Get projects to compare (from URL params or all active projects)
        project_ids = self.request.GET.getlist('projects')
        
        if project_ids:
            projects = Project.objects.filter(
                id__in=project_ids,
                company=user_company
            )
        else:
            projects = Project.objects.filter(
                company=user_company,
                is_active=True
            )[:5]  # Limit to 5 projects for comparison
        
        comparison_data = []
        for project in projects:
            tasks = Task.objects.filter(project=project)
            total_tasks = tasks.count()
            completed_tasks = tasks.filter(status='completed').count()
            
            comparison_data.append({
                'project': project,
                'progress': project.get_progress_percentage(),
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'pending_tasks': total_tasks - completed_tasks,
                'overdue_tasks': project.get_overdue_tasks(),
                'blocked_tasks': project.get_blocked_tasks().count(),
                'total_hours': float(project.get_total_hours()),
                'budget_status': project.get_budget_status(),
                'team_size': project.members.filter(left_date__isnull=True).count(),
                'days_remaining': (project.end_date - timezone.now().date()).days,
            })
        
        # Available projects for selection
        all_projects = Project.objects.filter(company=user_company, is_active=True)
        
        context.update({
            'comparison_data': comparison_data,
            'all_projects': all_projects,
            'selected_projects': [p.id for p in projects],
        })
        
        return context


# ==================== EXPORT VIEWS ====================

class ExportProjectReportView(LoginRequiredMixin, DetailView):
    """Export project report as JSON or CSV"""
    model = Project
    
    def get(self, request, *args, **kwargs):
        from django.http import JsonResponse, HttpResponse
        import csv
        
        project = self.get_object()
        export_format = request.GET.get('format', 'json')
        
        # Gather project data
        data = {
            'project_name': project.name,
            'status': project.get_status_display(),
            'progress': project.get_progress_percentage(),
            'task_distribution': project.get_task_distribution(),
            'budget_status': project.get_budget_status(),
            'total_hours': float(project.get_total_hours()),
            'overdue_tasks': project.get_overdue_tasks(),
            'blocked_tasks': project.get_blocked_tasks().count(),
        }
        
        if export_format == 'json':
            return JsonResponse(data)
        
        elif export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="project_{project.id}_report.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Metric', 'Value'])
            
            for key, value in data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        writer.writerow([f"{key}_{sub_key}", sub_value])
                else:
                    writer.writerow([key, value])
            
            return response
        
        return JsonResponse({'error': 'Invalid format'}, status=400)


# ==================== AJAX/API VIEWS ====================

class TaskQuickUpdateView(LoginRequiredMixin, UpdateView):
    """Quick update for task status (AJAX)"""
    model = Task
    fields = ['status']
    
    def form_valid(self, form):
        from django.http import JsonResponse
        
        task = form.save()
        
        if task.status == 'completed' and not task.completed_at:
            task.mark_completed()
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'status': task.get_status_display(),
        })
    
    def form_invalid(self, form):
        from django.http import JsonResponse
        return JsonResponse({
            'success': False,
            'errors': form.errors
        }, status=400)


class ChecklistToggleView(LoginRequiredMixin, UpdateView):
    """Toggle checklist item completion (AJAX)"""
    model = TaskChecklist
    fields = ['is_completed']
    
    def form_valid(self, form):
        from django.http import JsonResponse
        
        checklist = form.save(commit=False)
        if checklist.is_completed:
            checklist.completed_at = timezone.now()
        else:
            checklist.completed_at = None
        checklist.save()
        
        return JsonResponse({
            'success': True,
            'checklist_id': checklist.id,
            'is_completed': checklist.is_completed,
        })
    
    def form_invalid(self, form):
        from django.http import JsonResponse
        return JsonResponse({
            'success': False,
            'errors': form.errors
        }, status=400)


# ==================== UTILITY VIEWS ====================

class MainDashboardView(LoginRequiredMixin, TemplateView):
    """Main landing dashboard"""
    template_name = 'core/main_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get user's profile
        if hasattr(self.request.user, 'profile'):
            context['user_profile'] = self.request.user.profile
            user_company = self.request.user.profile.company
        else:
            user_company = Company.get_active_company()
        
        # Quick stats
        if user_company:
            context['quick_stats'] = {
                'total_projects': Project.objects.filter(company=user_company).count(),
                'active_projects': Project.objects.filter(company=user_company, is_active=True).count(),
                'total_tasks': Task.objects.filter(project__company=user_company).count(),
                'my_tasks': 0,  # Will be calculated based on employee
            }
            
            # Try to get employee tasks
            try:
                employee = Employee.objects.get(user=self.request.user)
                context['quick_stats']['my_tasks'] = Task.objects.filter(
                    assigned_to=employee,
                    status__in=['todo', 'in_progress']
                ).count()
            except Employee.DoesNotExist:
                pass
        
        return context        