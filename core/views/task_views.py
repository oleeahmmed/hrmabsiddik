# task_views.py - MODIFIED VERSION
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
from decimal import Decimal

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
        queryset=Project.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )


class TaskForm(forms.ModelForm):
    """Form for Task with auto-assignment"""
    
    class Meta:
        model = Task
        fields = [
            'project', 'title', 'description', 'status', 'priority',
            'due_date', 'estimated_hours', 'actual_hours',
            'assigned_to', 'is_blocked', 'blocking_reason'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Task Title'
            }),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'input'}),
            'priority': forms.Select(attrs={'class': 'input'}),
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
            'assigned_to': forms.Select(attrs={'class': 'input'}),
            'project': forms.Select(attrs={'class': 'input'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'blocking_reason': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        # Filter projects and users by company
        if self.company:
            company_ids = [c.id for c in self.company.get_all_subsidiaries(include_self=True)]
            
            # Filter projects
            self.fields['project'].queryset = Project.objects.filter(
                company__id__in=company_ids,
                is_active=True
            )
            
            # Filter users
            company_users = User.objects.filter(
                profile__company__id__in=company_ids,
                is_active=True
            )
            self.fields['assigned_to'].queryset = company_users


class TaskCreateView(PermissionRequiredMixin, AutoAssignOwnerMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a new task - FIXED with AutoAssignOwnerMixin
    Permission: core.add_task
    """
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.add_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create tasks.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        if hasattr(self.request.user, 'profile'):
            kwargs['company'] = self.request.user.profile.company
        return kwargs
    
    def get_initial(self):
        initial = super().get_initial()
        # Set default values
        initial['assigned_by'] = self.request.user
        initial['due_date'] = timezone.now().date()
        initial['estimated_hours'] = Decimal('0.00')
        initial['actual_hours'] = Decimal('0.00')
        return initial
    
    def form_valid(self, form):
        # Auto-assign assigned_by to current user
        form.instance.assigned_by = self.request.user
        
        # Auto-assign company from project if selected, otherwise from user profile
        if form.cleaned_data.get('project'):
            form.instance.company = form.cleaned_data['project'].company
        elif hasattr(self.request.user, 'profile') and self.request.user.profile.company:
            form.instance.company = self.request.user.profile.company
        
        messages.success(
            self.request,
            f'Task "{form.instance.title}" created successfully!'
        )
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'task',
            'back_url': reverse_lazy('core:task_list'),
            'back_text': 'Tasks',
        })
        return context


class TaskUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a task
    Permission: core.change_task
    """
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')
    permission_required = 'core.change_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update tasks.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        if hasattr(self.request.user, 'profile'):
            kwargs['company'] = self.request.user.profile.company
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'task',
            'back_url': reverse_lazy('core:task_list'),
            'back_text': 'Tasks',
        })
        return context
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f'Task "{form.instance.title}" updated successfully!'
        )
        return super().form_valid(form)


class TaskListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List tasks where user is owner OR assigned to the task
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
        # Get base queryset filtered by company
        queryset = super().get_queryset().select_related(
            'company',
            'owner',
            'project',
            'assigned_by',
            'assigned_to'
        )
        
        # Filter tasks where user is owner OR assigned to the task
        queryset = queryset.filter(
            Q(owner=self.request.user) | Q(assigned_to=self.request.user)
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
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get base queryset without slicing for counts
        base_queryset = super().get_queryset().filter(
            Q(owner=self.request.user) | Q(assigned_to=self.request.user)
        )
        
        # Task counts for current user's tasks
        context['total_tasks'] = base_queryset.count()
        context['completed_tasks'] = base_queryset.filter(status='completed').count()
        context['overdue_tasks'] = base_queryset.filter(
            due_date__lt=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).count()
        context['blocked_tasks'] = base_queryset.filter(is_blocked=True).count()
        
        # Set project choices for filter form
        if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
            company = self.request.user.profile.company
            company_ids = [c.id for c in company.get_all_subsidiaries(include_self=True)]
            context['filter_form'] = TaskFilterForm(self.request.GET)
            context['filter_form'].fields['project'].queryset = Project.objects.filter(
                company__id__in=company_ids,
                is_active=True
            )
        else:
            context['filter_form'] = TaskFilterForm()
        
        return context


class TaskDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View task details using the form template (read-only)
    Permission: core.view_task
    """
    model = Task
    template_name = 'core/task_form.html'
    permission_required = 'core.view_task'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view task details.')
        return redirect('core:task_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        
        # Add task statistics for detail view
        context['is_overdue'] = task.is_overdue()
        context['days_until_due'] = task.get_days_until_due()
        
        # Mark this as detail view (read-only)
        context['is_detail_view'] = True
        context['read_only'] = True
        
        return context


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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        context['comment_count'] = task.comments.count()
        return context
    
    def delete(self, request, *args, **kwargs):
        task = self.get_object()
        task_title = task.title
        messages.success(
            request,
            f'Task "{task_title}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)