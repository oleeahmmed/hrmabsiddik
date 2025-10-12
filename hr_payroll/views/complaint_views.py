# complaint_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import Complaint, Employee
from core.models import Company


# ==================== COMPLAINT MANAGEMENT ====================

class ComplaintFilterForm(forms.Form):
    """Form for filtering complaints in the list view"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by complaint title...',
        }),
        label=_('Search')
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + Complaint.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Status')
    )
    
    priority = forms.ChoiceField(
        required=False,
        choices=[('', 'All Priorities')] + Complaint.PRIORITY_CHOICES,
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Priority')
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)


class ComplaintForm(forms.ModelForm):
    """ModelForm for Complaint with proper validation"""
    
    class Meta:
        model = Complaint
        fields = ['employee', 'title', 'description', 'priority', 'status', 'assigned_to', 'resolution', 'remarks']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'input',
            }),
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter complaint title...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'rows': 4,
                'placeholder': 'Enter complaint description...'
            }),
            'priority': forms.Select(attrs={
                'class': 'input',
            }),
            'status': forms.Select(attrs={
                'class': 'input',
            }),
            'assigned_to': forms.Select(attrs={
                'class': 'input',
            }),
            'resolution': forms.Textarea(attrs={
                'class': 'input',
                'rows': 3,
                'placeholder': 'Enter resolution details...'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'input',
                'rows': 2,
                'placeholder': 'Enter any remarks...'
            }),
        }
        labels = {
            'employee': _('Employee'),
            'title': _('Complaint Title'),
            'description': _('Description'),
            'priority': _('Priority'),
            'status': _('Status'),
            'assigned_to': _('Assigned To'),
            'resolution': _('Resolution'),
            'remarks': _('Remarks'),
        }
        help_texts = {
            'description': _('Detailed description of the complaint'),
            'resolution': _('How the complaint was resolved'),
            'remarks': _('Additional notes or comments'),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter employees by active company
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=active_company, 
                is_active=True
            )
        
        # Filter assigned_to to staff users only
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['assigned_to'].queryset = User.objects.filter(is_staff=True)
        
        # Set initial submitted date for new complaints
        if not self.instance.pk:
            self.initial['submitted_date'] = timezone.now().date()
    
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        resolution = cleaned_data.get('resolution')
        resolved_date = cleaned_data.get('resolved_date')
        
        # If status is resolved, require resolution
        if status == 'resolved' and not resolution:
            raise forms.ValidationError(_('Resolution is required when status is set to resolved.'))
        
        # If status is resolved and no resolved_date, set it to today
        if status == 'resolved' and not resolved_date:
            cleaned_data['resolved_date'] = timezone.now().date()
        
        return cleaned_data


class ComplaintListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Complaint
    template_name = 'complaint/complaint_list.html'
    context_object_name = 'complaints'
    paginate_by = 10
    permission_required = 'hr_payroll.view_complaint'
    
    def get_queryset(self):
        queryset = Complaint.objects.all().select_related('employee', 'assigned_to')
        
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(employee__company=active_company)
        
        # Apply filters
        self.filter_form = ComplaintFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(title__icontains=data['search']) |
                    Q(description__icontains=data['search']) |
                    Q(employee__name__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('priority'):
                queryset = queryset.filter(priority=data['priority'])
        
        return queryset.order_by('-submitted_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_complaints'] = queryset.count()
        context['filter_form'] = self.filter_form
        
        # Statistics
        context['submitted_count'] = queryset.filter(status='submitted').count()
        context['under_review_count'] = queryset.filter(status='under_review').count()
        context['resolved_count'] = queryset.filter(status='resolved').count()
        context['closed_count'] = queryset.filter(status='closed').count()
        
        # High priority complaints
        context['high_priority_count'] = queryset.filter(priority='high').count()
        
        return context


class ComplaintCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Complaint
    form_class = ComplaintForm
    template_name = 'complaint/complaint_form.html'
    success_url = reverse_lazy('zkteco:complaint_list')
    permission_required = 'hr_payroll.add_complaint'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Complaint created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ComplaintUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Complaint
    form_class = ComplaintForm
    template_name = 'complaint/complaint_form.html'
    success_url = reverse_lazy('zkteco:complaint_list')
    permission_required = 'hr_payroll.change_complaint'
    
    def get_queryset(self):
        queryset = Complaint.objects.all().select_related('employee')
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(employee__company=active_company)
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set resolved_date if status is changed to resolved
        if form.instance.status == 'resolved' and not form.instance.resolved_date:
            form.instance.resolved_date = timezone.now().date()
        
        messages.success(self.request, _('Complaint updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ComplaintDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Complaint
    template_name = 'complaint/complaint_confirm_delete.html'
    success_url = reverse_lazy('zkteco:complaint_list')
    permission_required = 'hr_payroll.delete_complaint'
    
    def get_queryset(self):
        queryset = Complaint.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(employee__company=active_company)
        return queryset
    
    def delete(self, request, *args, **kwargs):
        complaint = self.get_object()
        
        # Check if complaint is resolved or closed
        if complaint.status in ['resolved', 'closed']:
            messages.warning(request, _('This complaint has already been resolved or closed.'))
        
        messages.success(request, _('Complaint deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class ComplaintDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Complaint
    template_name = 'complaint/complaint_detail.html'
    context_object_name = 'complaint'
    permission_required = 'hr_payroll.view_complaint'
    
    def get_queryset(self):
        queryset = Complaint.objects.all().select_related('employee', 'assigned_to')
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(employee__company=active_company)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        complaint = self.get_object()
        
        # Get similar complaints from the same employee
        similar_complaints = Complaint.objects.filter(
            employee=complaint.employee
        ).exclude(pk=complaint.pk).order_by('-submitted_date')[:5]
        context['similar_complaints'] = similar_complaints
        
        return context