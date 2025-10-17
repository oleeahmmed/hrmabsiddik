from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from .base_views import CompanyFilterMixin, CompanyRequiredMixin, CompanyOwnershipMixin, CommonContextMixin
from ..models import Project, Task
from django.contrib.auth import get_user_model

User = get_user_model()

class ProjectFilterForm(forms.Form):
    """Filter form for Projects"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search projects...'
        })
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
    """Form for Project with auto-assignment - MODIFIED VERSION"""
    
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'status', 'priority',
            'start_date', 'end_date', 'total_budget', 'spent_budget',
            'technical_lead', 'project_manager', 'supervisor', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Project Name'
            }),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'input'}),
            'priority': forms.Select(attrs={'class': 'input'}),
            'start_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'total_budget': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'spent_budget': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'technical_lead': forms.Select(attrs={'class': 'input'}),
            'project_manager': forms.Select(attrs={'class': 'input'}),
            'supervisor': forms.Select(attrs={'class': 'input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter users by company
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
            
            company_users = User.objects.filter(
                profile__company__id__in=company_ids,
                is_active=True
            )
            
            # Set queryset for all leadership fields
            self.fields['technical_lead'].queryset = company_users
            self.fields['project_manager'].queryset = company_users
            self.fields['supervisor'].queryset = company_users

    def clean(self):
        """FIXED: Remove company validation for leadership fields"""
        cleaned_data = super().clean()
        
        # Remove company validation for leadership fields
        # The company will be set from the user's profile in form_valid
        
        # Keep date validation
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError({
                'end_date': 'End date cannot be before start date.'
            })
        
        # Keep budget validation
        total_budget = cleaned_data.get('total_budget')
        spent_budget = cleaned_data.get('spent_budget')
        
        if total_budget and spent_budget and spent_budget > total_budget:
            raise forms.ValidationError({
                'spent_budget': 'Spent budget cannot exceed total budget.'
            })
        
        return cleaned_data


class ProjectCreateView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a new project - MODIFIED VERSION
    Permission: core.add_project
    """
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.add_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create projects.')
        return redirect('core:project_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # CRITICAL FIX: Set owner and company BEFORE saving
        form.instance.owner = self.request.user  # This sets the Admin
        
        # Set company from user's profile
        if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
            form.instance.company = self.request.user.profile.company
        
        # Save the instance first to get an ID
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            f'Project "{form.instance.name}" created successfully!'
        )
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'project',
            'back_url': reverse_lazy('core:project_list'),
            'back_text': 'Projects',
        })
        return context


class ProjectUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a project - MODIFIED VERSION
    Permission: core.change_project
    """
    model = Project
    form_class = ProjectForm
    template_name = 'core/project_form.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.change_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update projects.')
        return redirect('core:project_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'project',
            'back_url': reverse_lazy('core:project_list'),
            'back_text': 'Projects',
        })
        return context
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f'Project "{form.instance.name}" updated successfully!'
        )
        return super().form_valid(form)


class ProjectDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View project details using the form template (read-only) - MODIFIED VERSION
    Permission: core.view_project
    """
    model = Project
    template_name = 'core/project_form.html'  # Use form template for details
    permission_required = 'core.view_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project details.')
        return redirect('core:project_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        
        # Add project statistics for detail view
        context['task_distribution'] = project.get_task_distribution()
        context['budget_status'] = project.get_budget_status()
        context['progress'] = project.get_progress_percentage()
        context['total_hours'] = project.get_total_hours()
        context['total_tasks'] = project.tasks.count()
        context['completed_tasks'] = project.tasks.filter(status='completed').count()
        context['pending_tasks'] = project.tasks.filter(status__in=['todo', 'in_progress']).count()
        context['blocked_tasks'] = project.tasks.filter(is_blocked=True).count()
        context['overdue_tasks'] = project.get_overdue_tasks()
        
        # Project team information
        context['project_team'] = project.get_project_team()
        
        # Recent tasks
        context['recent_tasks'] = project.tasks.select_related(
            'assigned_to', 'assigned_by'
        ).order_by('-created_at')[:5]
        
        # Task breakdown by status
        context['todo_tasks'] = project.tasks.filter(status='todo').count()
        context['in_progress_tasks'] = project.tasks.filter(status='in_progress').count()
        context['on_hold_tasks'] = project.tasks.filter(status='on_hold').count()
        context['cancelled_tasks'] = project.tasks.filter(status='cancelled').count()
        
        # Mark this as detail view (read-only)
        context['is_detail_view'] = True
        context['read_only'] = True
        
        return context

class ProjectListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List latest 10 projects
    Permission: core.view_project
    """
    model = Project
    template_name = 'core/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10
    permission_required = 'core.view_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view projects.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'company',
            'owner',
            'technical_lead',
            'project_manager'
        ).prefetch_related('tasks')
        
        self.filter_form = ProjectFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
        
        # Apply ordering and slicing AFTER all filters
        return queryset.order_by('-created_at')[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get base queryset without slicing for counts
        base_queryset = super().get_queryset()
        
        # Project counts
        context['total_projects'] = base_queryset.count()
        context['active_projects'] = base_queryset.filter(is_active=True).count()
        context['planning_count'] = base_queryset.filter(status='planning').count()
        context['completed_count'] = base_queryset.filter(status='completed').count()
        
        # Task statistics
        from django.db.models import Count, Q
        from django.utils import timezone
        
        # Get all tasks across projects
        all_tasks = Task.objects.filter(project__in=base_queryset)
        context['total_tasks'] = all_tasks.count()
        
        # Count overdue tasks
        context['overdue_tasks'] = all_tasks.filter(
            due_date__lt=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).count()
        
        context['filter_form'] = self.filter_form
        
        return context


class ProjectListAllView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List all projects without pagination
    Permission: core.view_project
    """
    model = Project
    template_name = 'core/project_list_all.html'
    context_object_name = 'projects'
    paginate_by = None  # No pagination
    permission_required = 'core.view_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view projects.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'company',
            'owner',
            'technical_lead',
            'project_manager'
        )
        
        self.filter_form = ProjectFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get base queryset without slicing for counts
        base_queryset = super().get_queryset()
        context['filter_form'] = self.filter_form
        context['total_projects'] = base_queryset.count()
        context['active_projects'] = base_queryset.filter(is_active=True).count()
        context['planning_count'] = base_queryset.filter(status='planning').count()
        context['completed_count'] = base_queryset.filter(status='completed').count()
        
        return context


class ProjectPrintView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    Print project details using Print.js
    Permission: core.view_project
    """
    model = Project
    template_name = 'core/project_print.html'
    permission_required = 'core.view_project'
    context_object_name = 'project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project details.')
        return redirect('core:project_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        
        # Add project-specific data to context
        context.update({
            'task_distribution': project.get_task_distribution(),
            'budget_status': project.get_budget_status(),
            'progress': project.get_progress_percentage(),
            'total_hours': project.get_total_hours(),
            'recent_tasks': project.tasks.select_related('assigned_to').order_by('-created_at')[:10],
            'overdue_tasks': project.tasks.filter(
                due_date__lt=timezone.now().date(),
                status__in=['todo', 'in_progress']
            ).count(),
            'print_date': timezone.now().date(),
            'total_tasks': project.tasks.count(),
            'completed_tasks': project.tasks.filter(status='completed').count(),
            'pending_tasks': project.tasks.filter(status__in=['todo', 'in_progress']).count(),
            'blocked_tasks': project.tasks.filter(is_blocked=True).count(),
        })
        
        return context


class ProjectDeleteView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DeleteView):
    """
    Delete a project
    Permission: core.delete_project
    """
    model = Project
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.delete_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete projects.')
        return redirect('core:project_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        context.update({
            'task_count': project.tasks.count(),
            'back_url': reverse_lazy('core:project_list'),
            'back_text': 'Back to Projects',
            'title': f'Delete Project: {project.name}',
        })
        return context
    
    def delete(self, request, *args, **kwargs):
        project = self.get_object()
        project_name = project.name
        messages.success(
            request,
            f'Project "{project_name}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)
    """
    Delete a project
    Permission: core.delete_project
    """
    model = Project
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('core:project_list')
    permission_required = 'core.delete_project'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete projects.')
        return redirect('core:project_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        context['task_count'] = project.tasks.count()
        context['back_url'] = reverse_lazy('core:project_list')
        context['back_text'] = 'Back to Projects'
        return context
    
    def delete(self, request, *args, **kwargs):
        project = self.get_object()
        project_name = project.name
        messages.success(
            request,
            f'Project "{project_name}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)