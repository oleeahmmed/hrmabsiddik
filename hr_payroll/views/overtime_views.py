# overtime_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime, timedelta
from ..models import Overtime, Employee

class OvertimeFilterForm(forms.Form):
    """Form for filtering overtime requests in the list view"""
    
    STATUS_CHOICES = [
        ('', _('All Statuses')),
        ('pending', _('Pending')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('cancelled', _('Cancelled')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by employee name or reason...',
        }),
        label=_('Search')
    )
    
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        empty_label=_('All Employees'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Employee')
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
        label=_('Date From')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('Date To')
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set employee queryset based on user's company
        if user:
            try:
                employee = Employee.objects.get(user=user)
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()

class OvertimeForm(forms.ModelForm):
    """ModelForm for Overtime with proper validation"""
    
    class Meta:
        model = Overtime
        fields = ['employee', 'date', 'start_time', 'end_time', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': 'input'}),
            'date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'input',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'input',
                'type': 'time'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'input',
                'placeholder': 'Enter reason for overtime...',
                'rows': 4
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets based on user's employee record
        if user:
            try:
                employee = Employee.objects.get(user=user)
                
                # Filter employees by company
                if user.is_staff:
                    self.fields['employee'].queryset = Employee.objects.filter(
                        company=employee.company,
                        is_active=True
                    ).order_by('name')
                else:
                    # Non-staff users can only apply for themselves
                    self.fields['employee'].queryset = Employee.objects.filter(pk=employee.pk)
                    self.fields['employee'].initial = employee
                    self.fields['employee'].widget.attrs['readonly'] = True
                    
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if date and start_time and end_time:
            if end_time <= start_time:
                raise forms.ValidationError(_('End time must be after start time.'))
            
            # Calculate overtime hours
            start_datetime = datetime.combine(date, start_time)
            end_datetime = datetime.combine(date, end_time)
            
            if end_datetime <= start_datetime:
                end_datetime += timedelta(days=1)
            
            duration = end_datetime - start_datetime
            hours = duration.total_seconds() / 3600
            
            # Update the hours field
            cleaned_data['hours'] = round(hours, 2)
            
            # Check if overtime date is in the future
            today = timezone.now().date()
            if date > today:
                raise forms.ValidationError(_('Overtime cannot be requested for future dates.'))
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Calculate hours if not already set
        if instance.date and instance.start_time and instance.end_time:
            start_datetime = datetime.combine(instance.date, instance.start_time)
            end_datetime = datetime.combine(instance.date, instance.end_time)
            
            if end_datetime <= start_datetime:
                end_datetime += timedelta(days=1)
            
            duration = end_datetime - start_datetime
            instance.hours = round(duration.total_seconds() / 3600, 2)
        
        if commit:
            instance.save()
        return instance

class OvertimeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Overtime
    template_name = 'overtime/overtime_list.html'
    context_object_name = 'overtimes'
    paginate_by = 10
    permission_required = 'hr_payroll.view_overtime'
    
    def get_queryset(self):
        queryset = Overtime.objects.select_related('employee', 'approved_by')
        
        # Regular users see only their overtime, staff see all
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        # Apply filters
        self.filter_form = OvertimeFilterForm(self.request.GET, user=self.request.user)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(employee__name__icontains=data['search']) |
                    Q(reason__icontains=data['search'])
                )
            
            if data.get('employee'):
                queryset = queryset.filter(employee=data['employee'])
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('date_from'):
                queryset = queryset.filter(date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(date__lte=data['date_to'])
        
        return queryset.order_by('-date', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_overtimes'] = queryset.count()
        context['pending_count'] = queryset.filter(status='pending').count()
        context['approved_count'] = queryset.filter(status='approved').count()
        context['rejected_count'] = queryset.filter(status='rejected').count()
        context['cancelled_count'] = queryset.filter(status='cancelled').count()
        context['filter_form'] = self.filter_form
        
        # Calculate total overtime hours
        total_hours = sum(ovt.hours for ovt in queryset if ovt.hours)
        context['total_hours'] = round(total_hours, 2)
        
        return context

class OvertimeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Overtime
    form_class = OvertimeForm
    template_name = 'overtime/overtime_form.html'
    success_url = reverse_lazy('zkteco:overtime_list')
    permission_required = 'hr_payroll.add_overtime'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            employee = Employee.objects.get(user=self.request.user)
            
            # If no employee selected, assign to current user
            if not form.instance.employee:
                form.instance.employee = employee
            
            messages.success(self.request, _('Overtime request submitted successfully!'))
            return super().form_valid(form)
            
        except Employee.DoesNotExist:
            messages.error(self.request, _('No employee profile found for your account.'))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)

class OvertimeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Overtime
    form_class = OvertimeForm
    template_name = 'overtime/overtime_form.html'
    success_url = reverse_lazy('zkteco:overtime_list')
    permission_required = 'hr_payroll.change_overtime'
    
    def get_queryset(self):
        queryset = Overtime.objects.all()
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Overtime request updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)

class OvertimeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Overtime
    template_name = 'overtime/overtime_confirm_delete.html'
    success_url = reverse_lazy('zkteco:overtime_list')
    permission_required = 'hr_payroll.delete_overtime'
    
    def get_queryset(self):
        queryset = Overtime.objects.all()
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Overtime request deleted successfully!'))
        return super().delete(request, *args, **kwargs)

class OvertimeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Overtime
    template_name = 'overtime/overtime_detail.html'
    context_object_name = 'overtime'
    permission_required = 'hr_payroll.view_overtime'
    
    def get_queryset(self):
        queryset = Overtime.objects.select_related('employee', 'approved_by')
        if not self.request.user.is_staff:
            try:
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        return queryset

class OvertimeStatusChangeView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """API view for changing overtime status (approve/reject)"""
    model = Overtime
    fields = ['status', 'approved_by', 'remarks']
    permission_required = 'hr_payroll.change_overtime'
    
    def post(self, request, *args, **kwargs):
        overtime = self.get_object()
        new_status = request.POST.get('status')
        remarks = request.POST.get('remarks', '')
        
        if new_status in ['approved', 'rejected']:
            overtime.status = new_status
            overtime.approved_by = request.user
            overtime.approved_at = timezone.now()
            overtime.remarks = remarks
            overtime.save()
            
            messages.success(request, _('Overtime status updated successfully!'))
        else:
            messages.error(request, _('Invalid status provided.'))
        
        return redirect('zkteco:overtime_detail', pk=overtime.pk)