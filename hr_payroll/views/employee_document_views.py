# employee_document_views.py

from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from ..models import EmployeeDocument, Employee
from django.utils.translation import gettext_lazy as _
import os
# ==================== Employee Document Management ====================

class EmployeeDocumentFilterForm(forms.Form):
    """Form for filtering employee documents in the list view"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('', _('All Types')),
        ('resume', _('Resume/CV')),
        ('certificate', _('Certificate')),
        ('contract', _('Contract')),
        ('nid', _('National ID')),
        ('passport', _('Passport')),
        ('other', _('Other')),
    ]
    
    VERIFICATION_CHOICES = [
        ('', _('All Documents')),
        ('verified', _('Verified Only')),
        ('unverified', _('Unverified Only')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by title, employee name or ID...',
        }),
        label=_('Search')
    )
    
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        required=False,
        empty_label=_('All Employees'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Employee')
    )
    
    document_type = forms.ChoiceField(
        choices=DOCUMENT_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Document Type')
    )
    
    verification_status = forms.ChoiceField(
        choices=VERIFICATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Verification Status')
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            try:
                employee = Employee.objects.get(user=user)
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()



class EmployeeDocumentForm(forms.ModelForm):
    """ModelForm for EmployeeDocument with proper validation"""
    
    class Meta:
        model = EmployeeDocument
        fields = ['employee', 'document_type', 'title', 'description', 'file', 'is_verified']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'input',
            }),
            'document_type': forms.Select(attrs={
                'class': 'input',
            }),
            'title': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter document title',
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'placeholder': 'Enter document description',
                'rows': 4,
            }),
            'file': forms.FileInput(attrs={
                'class': 'input',
            }),
            'is_verified': forms.CheckboxInput(attrs={
                'class': 'switch-input',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter employees based on user's company
        if user:
            try:
                employee = Employee.objects.get(user=user)
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Validate file size (10MB limit)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError(_("File size must be less than 10MB"))
            
            # Validate file extensions
            valid_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(_("Unsupported file format. Please upload PDF, DOC, DOCX, JPG, or PNG files."))
        
        return file

class EmployeeDocumentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = EmployeeDocument
    template_name = 'employee/employee_document_list.html'
    context_object_name = 'documents'
    paginate_by = 20
    permission_required = 'hr_payroll.view_employeedocument'
    
    def get_queryset(self):
        queryset = EmployeeDocument.objects.select_related('employee', 'uploaded_by')
        
        # Filter by user's company
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        # Apply filters
        self.filter_form = EmployeeDocumentFilterForm(self.request.GET, user=self.request.user)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(title__icontains=data['search']) |
                    Q(employee__name__icontains=data['search']) |
                    Q(employee__employee_id__icontains=data['search']) |
                    Q(description__icontains=data['search'])
                )
            
            if data.get('employee'):
                queryset = queryset.filter(employee=data['employee'])
            
            if data.get('document_type'):
                queryset = queryset.filter(document_type=data['document_type'])
            
            if data.get('verification_status') == 'verified':
                queryset = queryset.filter(is_verified=True)
            elif data.get('verification_status') == 'unverified':
                queryset = queryset.filter(is_verified=False)
        
        return queryset.order_by('-uploaded_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_documents'] = queryset.count()
        context['verified_count'] = queryset.filter(is_verified=True).count()
        context['unverified_count'] = queryset.filter(is_verified=False).count()
        context['filter_form'] = self.filter_form
        
        return context


class EmployeeDocumentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = EmployeeDocument
    form_class = EmployeeDocumentForm
    template_name = 'employee/employee_document_form.html'
    success_url = reverse_lazy('zkteco:employee_document_list')
    permission_required = 'hr_payroll.add_employeedocument'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set uploaded_by to current user
        form.instance.uploaded_by = self.request.user
        
        messages.success(self.request, _('Document uploaded successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class EmployeeDocumentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = EmployeeDocument
    form_class = EmployeeDocumentForm
    template_name = 'employee/employee_document_form.html'
    success_url = reverse_lazy('zkteco:employee_document_list')
    permission_required = 'hr_payroll.change_employeedocument'
    
    def get_queryset(self):
        queryset = EmployeeDocument.objects.all()
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Document updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class EmployeeDocumentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = EmployeeDocument
    template_name = 'employee/employee_document_confirm_delete.html'
    success_url = reverse_lazy('zkteco:employee_document_list')
    permission_required = 'hr_payroll.delete_employeedocument'
    
    def get_queryset(self):
        queryset = EmployeeDocument.objects.all()
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Document deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class EmployeeDocumentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EmployeeDocument
    template_name = 'employee/employee_document_detail.html'
    context_object_name = 'document'
    permission_required = 'hr_payroll.view_employeedocument'
    
    def get_queryset(self):
        queryset = EmployeeDocument.objects.select_related('employee', 'uploaded_by')
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset