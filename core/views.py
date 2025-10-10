from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count,Sum
from django.contrib import messages
from django import forms
from .models import Task, Project, Company
from django.utils.translation import gettext_lazy as _

# ==================== Helper Mixin ====================

class CompanyFilterMixin:
    """Mixin to handle company filtering logic"""
    
    def get_user_company(self):
        """Get the user's company based on employee record or default company"""
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.filter(user=self.request.user).first()
            if employee and employee.company:
                return employee.company
        except Exception:
            pass
        
        # Return default active company if no employee record found
        return Company.get_active_company()
    
    def filter_queryset_by_company(self, queryset):
        """Filter queryset by user's company"""
        user_company = self.get_user_company()
        if user_company:
            queryset = queryset.filter(company=user_company)
        return queryset
    
    def filter_queryset_by_ownership(self, queryset):
        """Filter queryset based on user permissions (superuser/staff see all, others see only their own)"""
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            queryset = queryset.filter(owner=self.request.user)
        return queryset


# ==================== Company Management ====================

class CompanyFilterForm(forms.Form):
    """Form for filtering companies in the list view"""
    
    STATUS_CHOICES = [
        ('', _('All Statuses')),
        ('active', _('Active')),
        ('inactive', (_('Inactive'))),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by company name or code...',
        }),
        label=_('Search')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Status')
    )


class CompanyForm(forms.ModelForm):
    """ModelForm for Company with proper validation"""
    
    class Meta:
        model = Company
        fields = [
            'company_code', 'name', 'address_line1', 'address_line2', 
            'city', 'state', 'zip_code', 'country', 'phone_number', 
            'email', 'website', 'tax_id', 'currency', 
            'location_restricted', 'is_active'
        ]
        widgets = {
            'company_code': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter company code'
            }),
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter company name'
            }),
            'address_line1': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 1'
            }),
            'address_line2': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 2'
            }),
            'city': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'City'
            }),
            'state': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'State/Province'
            }),
            'zip_code': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'ZIP/Postal Code'
            }),
            'country': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Country'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Phone number'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'input',
                'placeholder': 'Email address'
            }),
            'website': forms.URLInput(attrs={
                'class': 'input',
                'placeholder': 'Website URL'
            }),
            'tax_id': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Tax ID (VAT, EIN, GST)'
            }),
            'currency': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Currency code (USD, EUR, GBP)'
            }),
            'location_restricted': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
        }
    
    def clean_company_code(self):
        company_code = self.cleaned_data.get('company_code')
        if self.instance and self.instance.pk:
            # For updates, exclude current instance from uniqueness check
            if Company.objects.filter(company_code=company_code).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(_('Company code must be unique.'))
        else:
            # For creates, check if company code exists
            if Company.objects.filter(company_code=company_code).exists():
                raise forms.ValidationError(_('Company code must be unique.'))
        return company_code


class CompanyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Company
    template_name = 'core/company_list.html'
    context_object_name = 'companies'
    paginate_by = 10
    permission_required = 'core.view_company'
    
    def get_queryset(self):
        queryset = Company.objects.all().order_by('name')
        
        # Apply filters
        self.filter_form = CompanyFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search']) |
                    Q(company_code__icontains=data['search']) |
                    Q(city__icontains=data['search']) |
                    Q(country__icontains=data['search'])
                )
            
            if data.get('status') == 'active':
                queryset = queryset.filter(is_active=True)
            elif data.get('status') == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_companies'] = queryset.count()
        context['active_count'] = queryset.filter(is_active=True).count()
        context['inactive_count'] = queryset.filter(is_active=False).count()
        context['filter_form'] = self.filter_form
        
        # Get project and employee counts for statistics
        context['total_projects'] = Project.objects.count()
        
        return context


class CompanyCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = 'core/company_form.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.add_company'
    
    def form_valid(self, form):
        messages.success(self.request, _('Company created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class CompanyUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = 'core/company_form.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.change_company'
    
    def form_valid(self, form):
        messages.success(self.request, _('Company updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class CompanyDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Company
    template_name = 'core/company_confirm_delete.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.delete_company'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.get_object()
        
        # Count related projects and tasks for warning
        project_count = Project.objects.filter(company=company).count()
        task_count = Task.objects.filter(company=company).count()
        
        context['project_count'] = project_count
        context['task_count'] = task_count
        
        return context
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Company deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class CompanyDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Company
    template_name = 'core/company_detail.html'
    context_object_name = 'company'
    permission_required = 'core.view_company'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.get_object()
        
        # Get company statistics
        projects = Project.objects.filter(company=company)
        tasks = Task.objects.filter(company=company)
        
        context['project_count'] = projects.count()
        context['task_count'] = tasks.count()
        context['active_projects'] = projects.filter(is_active=True).count()
        context['total_hours'] = tasks.aggregate(total_hours=Sum('hours_spent'))['total_hours'] or 0
        
        # Recent projects
        context['recent_projects'] = projects.select_related('owner').order_by('-created_at')[:5]
        
        # Recent tasks
        context['recent_tasks'] = tasks.select_related('project', 'employee').order_by('-created_at')[:5]
        
        return context

# ==================== Project Management ====================

class ProjectFilterForm(forms.Form):
    """Form for filtering projects in the list view"""
    
    STATUS_CHOICES = [
        ('', _('All Statuses')),
        ('active', _('Active')),
        ('inactive', _('Inactive')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by project name or description...',
        }),
        label=_('Search')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Status')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        label=_('Start Date From')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        label=_('Start Date To')
    )


class ProjectForm(forms.ModelForm):
    """ModelForm for Project with proper validation"""
    
    class Meta:
        model = Project
        fields = ['name', 'description', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter project name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'placeholder': 'Describe the project...',
                'rows': 4
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if not self.instance.pk:
            self.fields['is_active'].initial = True

    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(_('End date cannot be before start date.'))
        
        return end_date


class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, ListView):
    model = Project
    template_name = 'core/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10
    permission_required = 'core.view_project'
    
    def get_queryset(self):
        queryset = Project.objects.select_related('company', 'owner')
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser see only their projects)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        # Apply filters
        self.filter_form = ProjectFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('status') == 'active':
                queryset = queryset.filter(is_active=True)
            elif data.get('status') == 'inactive':
                queryset = queryset.filter(is_active=False)
            
            if data.get('date_from'):
                queryset = queryset.filter(start_date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(start_date__lte=data['date_to'])
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_projects'] = queryset.count()
        context['active_count'] = queryset.filter(is_active=True).count()
        context['inactive_count'] = queryset.filter(is_active=False).count()
        context['filter_form'] = self.filter_form
        
        return context


class ProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.add_project'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set the owner automatically
        form.instance.owner = self.request.user
        
        # Set the company automatically
        user_company = self.get_user_company()
        if user_company:
            form.instance.company = user_company
        else:
            messages.error(self.request, _('No company found. Please contact administrator.'))
            return self.form_invalid(form)
        
        messages.success(self.request, _('Project created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.change_project'
    
    def get_queryset(self):
        queryset = Project.objects.all()
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser can only edit their projects)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Project updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ProjectDeleteView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, DeleteView):
    model = Project
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.delete_project'
    
    def get_queryset(self):
        queryset = Project.objects.all()
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser can only delete their projects)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        
        # Count related tasks for warning
        task_count = Task.objects.filter(project=project).count()
        context['task_count'] = task_count
        
        return context
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Project deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class ProjectDetailView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, DetailView):
    model = Project
    template_name = 'core/project_detail.html'
    context_object_name = 'project'
    permission_required = 'core.view_project'
    
    def get_queryset(self):
        queryset = Project.objects.select_related('company', 'owner')
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser see only their projects)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        
        # Get project statistics
        tasks = Task.objects.filter(project=project)
        
        # If not staff/superuser, show only user's tasks
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            tasks = tasks.filter(owner=self.request.user)
        
        context['task_count'] = tasks.count()
        context['completed_tasks'] = tasks.filter(status='done').count()
        context['total_hours'] = tasks.aggregate(total_hours=Sum('hours_spent'))['total_hours'] or 0
        
        # Recent tasks
        context['recent_tasks'] = tasks.select_related('employee').order_by('-created_at')[:5]
        
        return context


# ==================== Task Management ====================

class TaskFilterForm(forms.Form):
    """Form for filtering tasks in the list view"""
    
    STATUS_CHOICES = [
        ('', _('All Statuses')),
        ('todo', _('To Do')),
        ('in_progress', _('In Progress')),
        ('done', _('Done')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by title or description...',
        }),
        label=_('Search')
    )
    
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        empty_label=_('All Projects'),
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Project')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Status')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        label=_('From Date')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        label=_('To Date')
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            user_company = self._get_user_company(user)
            if user_company:
                projects = Project.objects.filter(company=user_company, is_active=True)
                
                # If not staff/superuser, show only user's projects
                if not user.is_superuser and not user.is_staff:
                    projects = projects.filter(owner=user)
                
                self.fields['project'].queryset = projects.order_by('name')
    
    def _get_user_company(self, user):
        """Get the user's company based on employee record or default company"""
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.filter(user=user).first()
            if employee and employee.company:
                return employee.company
        except Exception:
            pass
        
        return Company.get_active_company()


class TaskForm(forms.ModelForm):
    """ModelForm for Task with proper validation"""
    
    date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
        label=_('Task Date')
    )
    
    class Meta:
        model = Task
        fields = ['project', 'employee', 'title', 'description', 'date', 'hours_spent', 'status']
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'employee': forms.Select(attrs={'class': 'input'}),
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter task title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'placeholder': 'Describe your task in detail...',
                'rows': 4
            }),
            'hours_spent': forms.NumberInput(attrs={
                'class': 'input',
                'placeholder': '0.00',
                'step': '0.25',
                'min': '0',
                'max': '24'
            }),
            'status': forms.Select(attrs={'class': 'input'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Make employee field optional
        self.fields['employee'].required = False
        self.fields['employee'].empty_label = "Unassigned"
        
        # Filter querysets based on user's company
        if user:
            user_company = self._get_user_company(user)
            if user_company:
                # Filter projects by company
                projects = Project.objects.filter(company=user_company, is_active=True)
                
                # If not staff/superuser, show only user's projects
                if not user.is_superuser and not user.is_staff:
                    projects = projects.filter(owner=user)
                
                self.fields['project'].queryset = projects.order_by('name')
                
                # Filter employees by company
                try:
                    from hr_payroll.models import Employee
                    self.fields['employee'].queryset = Employee.objects.filter(
                        company=user_company,
                        is_active=True
                    ).order_by('name')
                    
                    # Set current user's employee as default if exists
                    if not self.instance.pk:
                        current_employee = Employee.objects.filter(user=user).first()
                        if current_employee:
                            self.fields['employee'].initial = current_employee
                        
                except Exception:
                    self.fields['employee'].queryset = Employee.objects.none()
            else:
                self.fields['project'].queryset = Project.objects.none()
                self.fields['employee'].queryset = Employee.objects.none()
    
    def _get_user_company(self, user):
        """Get the user's company based on employee record or default company"""
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.filter(user=user).first()
            if employee and employee.company:
                return employee.company
        except Exception:
            pass
        
        return Company.get_active_company()


class TaskListView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 10
    permission_required = 'core.view_task'
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'employee', 'company', 'owner')
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser see only their tasks)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        # Apply filters
        self.filter_form = TaskFilterForm(self.request.GET, user=self.request.user)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(title__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('date_from'):
                queryset = queryset.filter(date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(date__lte=data['date_to'])
        
        return queryset.order_by('-date', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_tasks'] = queryset.count()
        context['todo_count'] = queryset.filter(status='todo').count()
        context['in_progress_count'] = queryset.filter(status='in_progress').count()
        context['done_count'] = queryset.filter(status='done').count()
        context['unassigned_count'] = queryset.filter(employee__isnull=True).count()
        context['filter_form'] = self.filter_form
        
        return context


class TaskCreateView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.add_task'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set the owner automatically
        form.instance.owner = self.request.user
        
        # Set the company automatically
        user_company = self.get_user_company()
        if user_company:
            form.instance.company = user_company
        else:
            messages.error(self.request, _('No company found. Please contact administrator.'))
            return self.form_invalid(form)
        
        # If no employee selected, try to assign to current user's employee record
        if not form.instance.employee:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.filter(user=self.request.user).first()
                if employee:
                    form.instance.employee = employee
            except Exception:
                pass  # Leave employee as null if no employee record found
        
        messages.success(self.request, _('Task created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class TaskUpdateView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.change_task'
    
    def get_queryset(self):
        queryset = Task.objects.all()
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser can only edit their tasks)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Task updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class TaskDeleteView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, DeleteView):
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.delete_task'
    
    def get_queryset(self):
        queryset = Task.objects.all()
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser can only delete their tasks)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Task deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class TaskDetailView(LoginRequiredMixin, PermissionRequiredMixin, CompanyFilterMixin, DetailView):
    model = Task
    template_name = 'core/task_detail.html'
    context_object_name = 'task'
    permission_required = 'core.view_task'
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'employee', 'company', 'owner')
        
        # Filter by company
        queryset = self.filter_queryset_by_company(queryset)
        
        # Filter by ownership (non-staff/superuser see only their tasks)
        queryset = self.filter_queryset_by_ownership(queryset)
        
        return queryset