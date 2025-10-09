from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from .models import Task, Project, Company
from django.utils.translation import gettext_lazy as _
from django.db import models

# ==================== Project Management ====================

# Add these imports at the top
from django.utils import timezone

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
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Status')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('Start Date From')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('Start Date To')
    )

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)


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
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set initial active status to True for new projects
        if not self.instance.pk:
            self.fields['is_active'].initial = True

    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(_('End date cannot be before start date.'))
        
        return end_date


class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Project
    template_name = 'core/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10
    permission_required = 'core.view_project'
    
    def get_queryset(self):
        queryset = Project.objects.select_related('company', 'owner')
        
        # Regular users see only projects from their company
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(company=employee.company)
            except:
                queryset = queryset.none()
        
        # Apply filters
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            self.filter_form = ProjectFilterForm(self.request.GET, employee=employee)
        except:
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


class ProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            
            # Set the owner and company
            form.instance.owner = self.request.user
            form.instance.company = employee.company
            
            messages.success(self.request, _('Project created successfully!'))
            return super().form_valid(form)
            
        except Employee.DoesNotExist:
            messages.error(self.request, _('No employee profile found for your account.'))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.change_project'
    
    def get_queryset(self):
        queryset = Project.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(company=employee.company)
            except:
                queryset = queryset.none()
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


class ProjectDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Project
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.delete_project'
    
    def get_queryset(self):
        queryset = Project.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(company=employee.company)
            except:
                queryset = queryset.none()
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


class ProjectDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Project
    template_name = 'core/project_detail.html'
    context_object_name = 'project'
    permission_required = 'core.view_project'
    
    def get_queryset(self):
        queryset = Project.objects.select_related('company', 'owner')
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(company=employee.company)
            except:
                queryset = queryset.none()
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        
        # Get project statistics
        context['task_count'] = Task.objects.filter(project=project).count()
        context['completed_tasks'] = Task.objects.filter(project=project, status='done').count()
        context['total_hours'] = Task.objects.filter(project=project).aggregate(
            total_hours=models.Sum('hours_spent')
        )['total_hours'] or 0
        
        # Recent tasks
        context['recent_tasks'] = Task.objects.filter(project=project).select_related(
            'employee'
        ).order_by('-created_at')[:5]
        
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
        queryset=Project.objects.filter(is_active=True),
        required=False,
        empty_label=_('All Projects'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Project')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Status')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('From Date')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('To Date')
    )

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)
        
        if employee:
            self.fields['project'].queryset = Project.objects.filter(
                company=employee.company,
                is_active=True
            ).order_by('name')


class TaskForm(forms.ModelForm):
    """ModelForm for Task with proper validation"""
    
    # Override date field since it has auto_now_add=True in model
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date'
        }),
        label=_('Task Date')
    )
    
    class Meta:
        model = Task
        fields = ['project', 'employee', 'title', 'description', 'hours_spent', 'status']
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
        
        # Filter querysets based on user's employee record
        if user:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=user)
                
                # Filter projects by company
                self.fields['project'].queryset = Project.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
                
                # Filter employees by company
                if user.is_staff:
                    self.fields['employee'].queryset = Employee.objects.filter(
                        company=employee.company,
                        is_active=True
                    ).order_by('name')
                else:
                    # Non-staff users can only assign tasks to themselves
                    self.fields['employee'].queryset = Employee.objects.filter(pk=employee.pk)
                    self.fields['employee'].initial = employee
                    
            except Employee.DoesNotExist:
                self.fields['project'].queryset = Project.objects.none()
                self.fields['employee'].queryset = Employee.objects.none()


class TaskListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 10
    permission_required = 'core.view_task'
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'employee', 'company')
        
        # Regular users see only their tasks, staff see all
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except:
                queryset = queryset.none()
        
        # Apply filters
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            self.filter_form = TaskFilterForm(self.request.GET, employee=employee)
        except:
            self.filter_form = TaskFilterForm(self.request.GET)
        
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
        
        return queryset.order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_tasks'] = queryset.count()
        context['todo_count'] = queryset.filter(status='todo').count()
        context['in_progress_count'] = queryset.filter(status='in_progress').count()
        context['done_count'] = queryset.filter(status='done').count()
        context['filter_form'] = self.filter_form
        
        return context


class TaskCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            
            # Set the owner
            form.instance.owner = self.request.user
            
            # Set the company
            form.instance.company = employee.company
            
            # If no employee selected, assign to current user
            if not form.instance.employee:
                form.instance.employee = employee
            
            messages.success(self.request, _('Task created successfully!'))
            return super().form_valid(form)
            
        except Employee.DoesNotExist:
            messages.error(self.request, _('No employee profile found for your account.'))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class TaskUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.change_task'
    
    def get_queryset(self):
        queryset = Task.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except:
                queryset = queryset.none()
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


class TaskDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.delete_task'
    
    def get_queryset(self):
        queryset = Task.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except:
                queryset = queryset.none()
        return queryset
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Task deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class TaskDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Task
    template_name = 'core/task_detail.html'
    context_object_name = 'task'
    permission_required = 'core.view_task'
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'employee', 'company')
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except:
                queryset = queryset.none()
        return queryset
    


   