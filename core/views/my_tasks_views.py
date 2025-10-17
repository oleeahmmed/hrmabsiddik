from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django import forms

from .base_views import CompanyFilterMixin, CompanyRequiredMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import Task, Project
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class MyTaskForm(forms.ModelForm):
    """Form for My Tasks with limited fields"""
    
    class Meta:
        model = Task
        fields = [
            'project', 'title', 'description', 'priority',
            'due_date', 'estimated_hours', 'is_blocked', 'blocking_reason'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Task Title'
            }),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 4}),
            'priority': forms.Select(attrs={'class': 'input'}),
            'due_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'project': forms.Select(attrs={'class': 'input'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'blocking_reason': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        # Filter projects by company
        if self.company:
            company_ids = [c.id for c in self.company.get_all_subsidiaries(include_self=True)]
            self.fields['project'].queryset = Project.objects.filter(
                company__id__in=company_ids,
                is_active=True
            )


class MyTasksView(CompanyRequiredMixin, CommonContextMixin, ListView):
    """View to show tasks assigned to current user with modal support"""
    model = Task
    template_name = 'core/my_tasks.html'
    context_object_name = 'tasks'
    paginate_by = 10
    
    def get_queryset(self):
        """Get tasks assigned to current user"""
        queryset = Task.objects.filter(
            assigned_to=self.request.user
        ).select_related('project', 'assigned_by', 'company').order_by('-created_at')
        
        # Apply company filtering
        company_filter = CompanyFilterMixin()
        company_filter.request = self.request
        return company_filter.filter_queryset_by_company(queryset)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add form for modal
        if hasattr(self.request.user, 'profile'):
            company = self.request.user.profile.company
            context['task_form'] = MyTaskForm(user=self.request.user, company=company)
        
        # Task statistics
        tasks = self.get_queryset()
        context['total_tasks'] = tasks.count()
        context['completed_tasks'] = tasks.filter(status='completed').count()
        context['in_progress_tasks'] = tasks.filter(status='in_progress').count()
        context['todo_tasks'] = tasks.filter(status='todo').count()
        context['overdue_tasks'] = tasks.filter(
            due_date__lt=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).count()
        
        return context


class MyTaskCreateView(CompanyRequiredMixin, AutoAssignOwnerMixin, CommonContextMixin, CreateView):
    """Create a new task for current user"""
    model = Task
    form_class = MyTaskForm
    template_name = 'core/my_task_modal_form.html'
    
    def get_success_url(self):
        return reverse_lazy('core:my_tasks')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        if hasattr(self.request.user, 'profile'):
            kwargs['company'] = self.request.user.profile.company
        return kwargs
    
    def get_initial(self):
        initial = super().get_initial()
        # Set default values
        initial['due_date'] = timezone.now().date()
        initial['estimated_hours'] = Decimal('0.00')
        return initial
    
    def form_valid(self, form):
        # Auto-assign to current user
        form.instance.assigned_to = self.request.user
        form.instance.assigned_by = self.request.user
        
        # Auto-assign company
        if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
            form.instance.company = self.request.user.profile.company
        
        messages.success(
            self.request,
            f'Task "{form.instance.title}" created successfully!'
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            'Please correct the errors below.'
        )
        return super().form_invalid(form)


class MyTaskUpdateView(CompanyRequiredMixin, CommonContextMixin, UpdateView):
    """Update a task assigned to current user"""
    model = Task
    form_class = MyTaskForm
    template_name = 'core/my_task_modal_form.html'
    
    def get_success_url(self):
        return reverse_lazy('core:my_tasks')
    
    def get_queryset(self):
        """Only allow updating tasks assigned to current user"""
        queryset = super().get_queryset()
        return queryset.filter(assigned_to=self.request.user)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        if hasattr(self.request.user, 'profile'):
            kwargs['company'] = self.request.user.profile.company
        return kwargs
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f'Task "{form.instance.title}" updated successfully!'
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            'Please correct the errors below.'
        )
        return super().form_invalid(form)


class MyTaskDetailView(CompanyRequiredMixin, CommonContextMixin, DetailView):
    """View task details in modal"""
    model = Task
    template_name = 'core/my_task_modal_detail.html'
    
    def get_queryset(self):
        """Only allow viewing tasks assigned to current user"""
        queryset = super().get_queryset()
        return queryset.filter(assigned_to=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        
        # Add task statistics for detail view
        context['is_overdue'] = task.is_overdue()
        context['days_until_due'] = task.get_days_until_due()
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
class UpdateTaskStatusView(LoginRequiredMixin, View):
    """Update task status via AJAX"""
    
    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, assigned_to=request.user)
        
        # Get new status from POST data
        new_status = request.POST.get('status')
        
        # Validate status
        valid_statuses = dict(Task.STATUS_CHOICES).keys()
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status'})
        
        # Update task status
        task.status = new_status
        if new_status == 'completed':
            task.completed_at = timezone.now()
        task.save()
        
        return JsonResponse({
            'success': True, 
            'new_status': task.get_status_display(),
            'status_class': self.get_status_class(task.status)
        })
    
    def get_status_class(self, status):
        """Get CSS class for status badge"""
        status_classes = {
            'todo': 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
            'in_progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
            'on_hold': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
            'completed': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
            'cancelled': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
        }
        return status_classes.get(status, 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400')