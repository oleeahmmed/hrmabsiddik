from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.contrib import messages
from django.shortcuts import redirect

from .base_views import CompanyFilterMixin, CompanyRequiredMixin, CompanyOwnershipMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import TaskComment, Task


class TaskCommentForm(forms.ModelForm):
    """Form for TaskComment"""
    
    class Meta:
        model = TaskComment
        fields = ['task', 'comment']
        widgets = {
            'task': forms.Select(attrs={'class': 'input'}),
            'comment': forms.Textarea(attrs={
                'class': 'textarea',
                'rows': 4,
                'placeholder': 'Add your comment...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter tasks by company
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
            
            self.fields['task'].queryset = Task.objects.filter(
                company__id__in=company_ids
            )


class TaskCommentListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List latest 10 task comments
    Permission: core.view_taskcomment
    """
    model = TaskComment
    template_name = 'core/taskcomment_list.html'
    context_object_name = 'comments'
    paginate_by = 10
    permission_required = 'core.view_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view task comments.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        return super().get_queryset().select_related(
            'task', 'commented_by', 'company'
        ).order_by('-created_at')[:10]


class TaskCommentListAllView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List all task comments
    Permission: core.view_taskcomment
    """
    model = TaskComment
    template_name = 'core/taskcomment_list_all.html'
    context_object_name = 'comments'
    paginate_by = 50
    permission_required = 'core.view_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view task comments.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        return super().get_queryset().select_related(
            'task', 'commented_by', 'company'
        ).order_by('-created_at')


class TaskCommentCreateView(PermissionRequiredMixin, AutoAssignOwnerMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a task comment
    Permission: core.add_taskcomment
    """
    model = TaskComment
    form_class = TaskCommentForm
    template_name = 'form.html'
    permission_required = 'core.add_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to add comments.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_success_url(self):
        return reverse_lazy('core:task_detail', kwargs={'pk': self.object.task.pk})
    
    def form_valid(self, form):
        # Auto-assign commented_by
        if not form.instance.commented_by:
            form.instance.commented_by = self.request.user
        
        messages.success(self.request, 'Comment added successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        task_id = self.request.GET.get('task')
        if task_id:
            initial['task'] = task_id
        return initial


class TaskCommentUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a task comment
    Permission: core.change_taskcomment
    """
    model = TaskComment
    form_class = TaskCommentForm
    template_name = 'form.html'
    permission_required = 'core.change_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update comments.')
        return redirect('core:task_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_success_url(self):
        return reverse_lazy('core:task_detail', kwargs={'pk': self.object.task.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'Comment updated successfully!')
        return super().form_valid(form)


class TaskCommentDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View task comment details
    Permission: core.view_taskcomment
    """
    model = TaskComment
    template_name = 'form.html'
    permission_required = 'core.view_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view comments.')
        return redirect('core:task_list')


class TaskCommentDeleteView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DeleteView):
    """
    Delete a task comment
    Permission: core.delete_taskcomment
    """
    model = TaskComment
    template_name = 'core/taskcomment_confirm_delete.html'
    permission_required = 'core.delete_taskcomment'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete comments.')
        return redirect('core:task_list')
    
    def get_success_url(self):
        return reverse_lazy('core:task_detail', kwargs={'pk': self.object.task.pk})
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Comment deleted successfully!')
        return super().delete(request, *args, **kwargs)