from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from .base_views import CompanyFilterMixin, CompanyRequiredMixin, CompanyOwnershipMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import Task, Project
from django.contrib.auth import get_user_model

User = get_user_model()


class TaskFilterForm(forms.Form):
    """Filter form for Tasks"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search tasks...'
        })
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + Task.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    priority = forms.ChoiceField(
        choices=[('', 'All Priority')] + Task.PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class TaskForm(forms.ModelForm):
    """Form for Task with auto-assignment"""
    
    class Meta:
        model = Task
        fields = [
            'project', 'title', 'description', 'status', 'priority',
            'assigned_to', 'due_date', 'estimated_hours', 'actual_hours',
            'is_blocked', 'blocking_reason'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Task Title'
            }),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'input'}),
            'priority': forms.Select(attrs={'class': 'input'}),
            'assigned_to': forms.Select(attrs={'class': 'input'}),
            'due_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'actual_hours': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'blocking_reason': forms.Textarea(attrs={'class': 'textarea', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter by company
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
            
            # Filter projects
            self.fields['project'].queryset = Project.objects.filter(
                company__id__in=company_ids,
                is_active=True
            )
            
            # Filter users
            self.fields['assigned_to'].queryset = User.objects.filter(
                profile__company__id__in=company_ids,
                is_active=True
            )


class TaskListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List latest 10 tasks
    Permission: core.view_task
    """
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 10
    permission_required = 'core.view_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view tasks.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'project',
            'company',
            'owner',
            'assigned_to',
            'assigned_by'
        )
        
        self.filter_form = TaskFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(title__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('assigned_to'):
                queryset = queryset.filter(assigned_to=data['assigned_to'])
        
        return queryset.order_by('-created_at')[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        
        queryset = self.get_queryset()
        context['total_tasks'] = queryset.count()
        context['overdue_tasks'] = queryset.filter(
            due_date__lt=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).count()
        context['blocked_tasks'] = queryset.filter(is_blocked=True).count()
        
        return context


class TaskListAllView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List all tasks
    Permission: core.view_task
    """
    model = Task
    template_name = 'core/task_list_all.html'
    context_object_name = 'tasks'
    paginate_by = 50
    permission_required = 'core.view_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view tasks.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'project',
            'company',
            'owner',
            'assigned_to',
            'assigned_by'
        )
        
        self.filter_form = TaskFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(title__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('assigned_to'):
                queryset = queryset.filter(assigned_to=data['assigned_to'])
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        
        queryset = self.get_queryset()
        context['total_tasks'] = queryset.count()
        context['overdue_tasks'] = queryset.filter(
            due_date__lt=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).count()
        context['blocked_tasks'] = queryset.filter(is_blocked=True).count()
        
        return context


class TaskCreateView(PermissionRequiredMixin, AutoAssignOwnerMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a new task
    Permission: core.add_task
    """
    model = Task
    form_class = TaskForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.add_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create tasks.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Auto-assign assigned_by
        if not form.instance.assigned_by:
            form.instance.assigned_by = self.request.user
        
        messages.success(
            self.request,
            f'Task "{form.instance.title}" created successfully!'
        )
        return super().form_valid(form)


class TaskUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a task
    Permission: core.change_task
    """
    model = Task
    form_class = TaskForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.change_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update tasks.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f'Task "{form.instance.title}" updated successfully!'
        )
        return super().form_valid(form)


class TaskDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View task details
    Permission: core.view_task
    """
    model = Task
    template_name = 'form.html'
    permission_required = 'core.view_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view task details.')
        return redirect('core:task_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        
        context['comments'] = task.comments.select_related(
            'commented_by'
        ).order_by('-created_at')
        
        context['is_overdue'] = task.is_overdue()
        context['days_until_due'] = task.get_days_until_due()
        
        return context


class TaskPrintView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    Print task details
    Permission: core.view_task
    """
    model = Task
    template_name = 'core/task_print.html'
    permission_required = 'core.view_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view task details.')
        return redirect('core:task_list')


class TaskDeleteView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DeleteView):
    """
    Delete a task
    Permission: core.delete_task
    """
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.delete_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete tasks.')
        return redirect('core:task_list')
    
    def delete(self, request, *args, **kwargs):
        task = self.get_object()
        task_title = task.title
        messages.success(
            request,
            f'Task "{task_title}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)