
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django import forms
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.core.exceptions import ValidationError

from .base_views import CompanyRequiredMixin, AutoAssignOwnerMixin, CommonContextMixin
from ..models import Company, Project, UserProfile, Task


class CompanyFilterForm(forms.Form):
    """Form for filtering companies"""
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by name or code...',
        })
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input'})
    )
    parent = forms.ModelChoiceField(
        queryset=Company.objects.filter(is_active=True),
        required=False,
        empty_label='All Companies',
        widget=forms.Select(attrs={'class': 'input'})
    )


class CompanyForm(forms.ModelForm):
    """Form for Company with fieldset configuration"""
    
    # Fieldset configuration stored in form class
    form_fieldsets = [
        {
            'name': 'Basic Information',
            'icon': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
            'fields': ['company_code', 'name', 'parent', 'is_active'],
            'columns': 'md:grid-cols-2 lg:grid-cols-4'
        },
        {
            'name': 'Address Information',
            'icon': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/>',
            'fields': ['address_line1', 'address_line2', 'city', 'state', 'zip_code', 'country'],
            'columns': 'md:grid-cols-2 lg:grid-cols-3'
        },
        {
            'name': 'Contact Information',
            'icon': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/>',
            'fields': ['phone_number', 'email', 'website'],
            'columns': 'md:grid-cols-1 lg:grid-cols-3'
        },
        {
            'name': 'Legal & Financial Information',
            'icon': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
            'fields': ['tax_id', 'registration_number', 'currency'],
            'columns': 'md:grid-cols-1 lg:grid-cols-3'
        },
        {
            'name': 'Additional Settings',
            'icon': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
            'fields': ['logo', 'location_restricted'],
            'columns': 'md:grid-cols-1 lg:grid-cols-2'
        }
    ]
    
    class Meta:
        model = Company
        fields = [
            'company_code', 'name', 'parent', 'address_line1', 'address_line2',
            'city', 'state', 'zip_code', 'country', 'phone_number',
            'email', 'website', 'tax_id', 'registration_number', 'currency',
            'logo', 'location_restricted', 'is_active'
        ]
        widgets = {
            'company_code': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'e.g., COMP001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Company Name'
            }),
            'parent': forms.Select(attrs={'class': 'input'}),
            'address_line1': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 1'
            }),
            'address_line2': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Address Line 2'
            }),
            'city': forms.TextInput(attrs={'class': 'input', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'input', 'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'class': 'input', 'placeholder': 'ZIP'}),
            'country': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Country'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Phone'
            }),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email'}),
            'website': forms.URLInput(attrs={'class': 'input', 'placeholder': 'Website'}),
            'tax_id': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Tax ID'}),
            'registration_number': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Registration Number'
            }),
            'currency': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'e.g., BDT, USD'
            }),
            'logo': forms.FileInput(attrs={'class': 'input'}),
            'location_restricted': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter parent companies based on user's access
        if self.user and hasattr(self.user, 'profile') and self.user.profile.company:
            user_company = self.user.profile.company
            # Can only select own company or its parents as parent
            allowed_parents = user_company.get_hierarchy_path()
            self.fields['parent'].queryset = Company.objects.filter(
                id__in=[c.id for c in allowed_parents]
            )


class CompanyListView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, ListView):
    """
    List latest 10 companies
    Permission: core.view_company
    """
    model = Company
    template_name = 'core/company_list.html'
    context_object_name = 'companies'
    paginate_by = 10
    permission_required = 'core.view_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view companies.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = Company.objects.select_related('parent')
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
            
            if data.get('parent'):
                queryset = queryset.filter(parent=data['parent'])
        
        return queryset.order_by('-created_at')[:10]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_companies'] = Company.objects.count()
        context['active_count'] = Company.objects.filter(is_active=True).count()
        context['inactive_count'] = Company.objects.filter(is_active=False).count()
        context['total_projects'] = Project.objects.count()
        return context


class CompanyListAllView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, ListView):
    """
    List all companies
    Permission: core.view_company
    """
    model = Company
    template_name = 'core/company_list_all.html'
    context_object_name = 'companies'
    paginate_by = 50
    permission_required = 'core.view_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view companies.')
        return redirect('core:main_dashboard')
    
    def get_queryset(self):
        queryset = Company.objects.select_related('parent')
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
            
            if data.get('parent'):
                queryset = queryset.filter(parent=data['parent'])
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['total_companies'] = Company.objects.count()
        context['active_count'] = Company.objects.filter(is_active=True).count()
        context['inactive_count'] = Company.objects.filter(is_active=False).count()
        context['total_projects'] = Project.objects.count()
        return context


class CompanyCreateView(PermissionRequiredMixin, AutoAssignOwnerMixin, CompanyRequiredMixin, CommonContextMixin, CreateView):
    """
    Create a new company
    Permission: core.add_company
    """
    model = Company
    form_class = CompanyForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.add_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to create companies.')
        return redirect('core:company_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'company',
            'back_url': reverse_lazy('core:company_list'),
            'back_text': 'Companies',
            'form_fieldsets': self.form_class.form_fieldsets,
            'is_create': True
        })
        return context
    
    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(
                self.request,
                f'Company "{self.object.name}" created successfully!'
            )
            return response
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    form.add_error(field, error)
            return self.form_invalid(form)


class CompanyUpdateView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, UpdateView):
    """
    Update a company
    Permission: core.change_company
    """
    model = Company
    form_class = CompanyForm
    template_name = 'form.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.change_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to update companies.')
        return redirect('core:company_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'model_name': 'company',
            'back_url': reverse_lazy('core:company_list'),
            'back_text': 'Companies',
            'form_fieldsets': self.form_class.form_fieldsets,
            'is_update': True
        })
        return context
    
    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(
                self.request,
                f'Company "{self.object.name}" updated successfully!'
            )
            return response
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    form.add_error(field, error)
            return self.form_invalid(form)


class CompanyDetailView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, DetailView):
    """
    View company details
    Permission: core.view_company
    """
    model = Company
    template_name = 'form.html'
    permission_required = 'core.view_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view company details.')
        return redirect('core:company_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.get_object()
        
        # Create a mock form instance for display purposes
        class ReadOnlyForm(forms.ModelForm):
            class Meta:
                model = Company
                fields = '__all__'
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for field in self.fields:
                    self.fields[field].widget.attrs['disabled'] = True
                    self.fields[field].widget.attrs['readonly'] = True
        
        # Initialize form with object data for display
        form = ReadOnlyForm(instance=company)
        
        context.update({
            'model_name': 'company',
            'back_url': reverse_lazy('core:company_list'),
            'back_text': 'Companies',
            'form_fieldsets': CompanyForm.form_fieldsets,
            'form': form,  # Pass form for consistent template rendering
            'object': company,
            'is_detail': True
        })
        
        # Get additional context for detail view
        context['subsidiaries'] = company.subsidiaries.filter(is_active=True)
        context['hierarchy_path'] = company.get_hierarchy_path()
        context['stats'] = {
            'projects': Project.objects.filter(company=company).count(),
            'active_projects': Project.objects.filter(company=company, is_active=True).count(),
            'users': UserProfile.objects.filter(company=company, is_active=True).count(),
            'tasks': Task.objects.filter(company=company).count(),
        }
        context['recent_projects'] = Project.objects.filter(company=company).order_by('-created_at')[:5]
        
        return context


class CompanyPrintView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, DetailView):
    """
    Print company details
    Permission: core.view_company
    """
    model = Company
    template_name = 'core/company_print.html'
    permission_required = 'core.view_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to view company details.')
        return redirect('core:company_list')


class CompanyDeleteView(PermissionRequiredMixin, CompanyRequiredMixin, CommonContextMixin, DeleteView):
    """
    Delete a company
    Permission: core.delete_company
    """
    model = Company
    template_name = 'core/company_confirm_delete.html'
    success_url = reverse_lazy('core:company_list')
    permission_required = 'core.delete_company'
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to delete companies.')
        return redirect('core:company_list')
    
    def delete(self, request, *args, **kwargs):
        company = self.get_object()
        
        # Check if company has subsidiaries
        if company.subsidiaries.exists():
            messages.error(
                request,
                'Cannot delete company with subsidiaries. Please delete subsidiaries first.'
            )
            return redirect('core:company_detail', pk=company.pk)
        
        # Check if company has users
        if company.user_profiles.exists():
            messages.error(
                request,
                'Cannot delete company with associated users. Please reassign users first.'
            )
            return redirect('core:company_detail', pk=company.pk)
        
        messages.success(request, f'Company "{company.name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)
