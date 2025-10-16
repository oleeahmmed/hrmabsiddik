from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from .base_views import CompanyFilterMixin, CompanyRequiredMixin, CompanyOwnershipMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import ProjectReport, Project


class ProjectReportFilterForm(forms.Form):
    """Filter form for Project Reports"""
    project = forms.ModelChoiceField(
        queryset=Project.objects.all(),
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
    
    class Meta:
        model = ProjectReport
        fields = [
            'project', 'report_date', 'completed_tasks', 'pending_tasks',
            'blocked_tasks', 'total_hours_logged', 'issues_summary',
            'planned_activities', 'notes', 'budget_spent_this_period'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'input'}),
            'report_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'completed_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'pending_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'blocked_tasks': forms.NumberInput(attrs={'class': 'input'}),
            'total_hours_logged': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01'
            }),
            'issues_summary': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'planned_activities': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'budget_spent_this_period': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.01'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter projects by company
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
            
            self.fields['project'].queryset = Project.objects.filter(
                company__id__in=company_ids,
                is_active=True
            )


class ProjectReportListView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List latest 10 project reports
    Permission: core.view_projectreport
    """
    model = ProjectReport
    template_name = 'core/projectreport_list.html'
    context_object_name = 'reports'
    paginate_by = 10
    permission_required = 'core.view_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project reports.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'project',
            'company',
            'owner',
            'reported_by'
        )
        
        self.filter_form = ProjectReportFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
            if data.get('date_from'):
                queryset = queryset.filter(report_date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(report_date__lte=data['date_to'])
        
        return queryset.order_by('-report_date')[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_reports'] = self.get_queryset().count()
        return context


class ProjectReportListAllView(PermissionRequiredMixin, CompanyFilterMixin, CommonContextMixin, ListView):
    """
    List all project reports
    Permission: core.view_projectreport
    """
    model = ProjectReport
    template_name = 'core/projectreport_list_all.html'
    context_object_name = 'reports'
    paginate_by = 50
    permission_required = 'core.view_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project reports.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'project',
            'company',
            'owner',
            'reported_by'
        )
        
        self.filter_form = ProjectReportFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('project'):
                queryset = queryset.filter(project=data['project'])
            
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


class ProjectReportCreateView(PermissionRequiredMixin, AutoAssignOwnerMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a project report
    Permission: core.add_projectreport
    """
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:projectreport_list')
    permission_required = 'core.add_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create project reports.')
        return redirect('core:projectreport_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Auto-assign reported_by
        if not form.instance.reported_by:
            form.instance.reported_by = self.request.user
        
        messages.success(self.request, 'Project Report created successfully!')
        return super().form_valid(form)
    
    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
        initial['report_date'] = timezone.now().date()
        return initial


class ProjectReportUpdateView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, UpdateView):
    """
    Update a project report
    Permission: core.change_projectreport
    """
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:projectreport_list')
    permission_required = 'core.change_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update project reports.')
        return redirect('core:projectreport_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, 'Project Report updated successfully!')
        return super().form_valid(form)


class ProjectReportDetailView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    View project report details
    Permission: core.view_projectreport
    """
    model = ProjectReport
    template_name = 'form.html'
    permission_required = 'core.view_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project report details.')
        return redirect('core:projectreport_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.get_object()
        
        # Calculate completion rate
        total_tasks = report.completed_tasks + report.pending_tasks + report.blocked_tasks
        if total_tasks > 0:
            context['completion_rate'] = round(
                (report.completed_tasks / total_tasks) * 100,
                2
            )
        else:
            context['completion_rate'] = 0
        
        return context


class ProjectReportPrintView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DetailView):
    """
    Print project report details
    Permission: core.view_projectreport
    """
    model = ProjectReport
    template_name = 'core/projectreport_print.html'
    permission_required = 'core.view_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view project report details.')
        return redirect('core:projectreport_list')


class ProjectReportDeleteView(PermissionRequiredMixin, CompanyOwnershipMixin, CommonContextMixin, DeleteView):
    """
    Delete a project report
    Permission: core.delete_projectreport
    """
    model = ProjectReport
    template_name = 'core/projectreport_confirm_delete.html'
    success_url = reverse_lazy('core:projectreport_list')
    permission_required = 'core.delete_projectreport'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete project reports.')
        return redirect('core:projectreport_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Project Report deleted successfully!')
        return super().delete(request, *args, **kwargs)