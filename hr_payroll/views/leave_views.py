from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q,F
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.utils import timezone
from datetime import timedelta
from ..models import LeaveApplication, LeaveBalance, LeaveType

# ==================== LEAVE MANAGEMENT ====================

class LeaveFilterForm(forms.Form):
    """Form for filtering leave applications in the list view"""
    
    STATUS_CHOICES = [
        ('', _('All Statuses')),
        ('P', _('Pending')),
        ('A', _('Approved')),
        ('R', _('Rejected')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by employee name or reason...',
        }),
        label=_('Search')
    )
    
    leave_type = forms.ModelChoiceField(
        queryset=LeaveType.objects.none(),  # Start with empty queryset
        required=False,
        empty_label=_('All Leave Types'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Leave Type')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Status')
    )
    
    start_date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('Start Date From')
    )
    
    start_date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('Start Date To')
    )

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)
        
        # Set leave_type queryset based on employee or use all active leave types
        if employee:
            self.fields['leave_type'].queryset = LeaveType.objects.filter(
                company=employee.company
            ).order_by('name')
        else:
            # Fallback for cases where no employee is provided
            self.fields['leave_type'].queryset = LeaveType.objects.all().order_by('name')

class LeaveApplicationForm(forms.ModelForm):
    """ModelForm for LeaveApplication with proper validation"""
    
    class Meta:
        model = LeaveApplication
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': 'input'}),
            'leave_type': forms.Select(attrs={'class': 'input'}),
            'start_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'input',
                'placeholder': 'Enter reason for leave...',
                'rows': 4
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets based on user's employee record
        if user:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=user)
                
                # Filter leave types by company
                self.fields['leave_type'].queryset = LeaveType.objects.filter(
                    company=employee.company
                ).order_by('name')
                
                # Filter employees by company and user permissions
                if user.is_staff or user.is_superuser:
                    # Staff can apply for any employee in their company
                    self.fields['employee'].queryset = Employee.objects.filter(
                        company=employee.company,
                        is_active=True
                    ).order_by('name')
                else:
                    # Non-staff users can only apply for themselves
                    self.fields['employee'].queryset = Employee.objects.filter(pk=employee.pk)
                    self.fields['employee'].initial = employee
                    self.fields['employee'].widget.attrs['readonly'] = True
                    self.fields['employee'].widget.attrs['disabled'] = True
                    
                # Hide status field for non-staff users
                if not user.is_staff and not user.is_superuser:
                    if 'status' in self.fields:
                        del self.fields['status']
                    
            except Employee.DoesNotExist:
                # If user doesn't have an employee record, show all leave types
                # This allows the form to be displayed, but validation will catch the issue
                self.fields['leave_type'].queryset = LeaveType.objects.all().order_by('name')
                self.fields['employee'].queryset = Employee.objects.none()
                
                # Add a form error to inform the user
                if hasattr(self, 'add_error'):
                    self.add_error(None, _('No employee profile found for your account. Please contact administrator.'))
        else:
            # No user provided, show all leave types but no employees
            self.fields['leave_type'].queryset = LeaveType.objects.all().order_by('name')
            self.fields['employee'].queryset = Employee.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        employee = cleaned_data.get('employee')
        leave_type = cleaned_data.get('leave_type')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(_('End date cannot be before start date.'))
        
        # Check if employee has enough leave balance
        if employee and leave_type and start_date and end_date:
            # Calculate number of days (excluding weekends)
            delta = end_date - start_date
            business_days = 0
            for i in range(delta.days + 1):
                day = start_date + timedelta(days=i)
                if day.weekday() < 5:  # Monday to Friday
                    business_days += 1
            
            # Get or create leave balance
            leave_balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=leave_type,
                defaults={'entitled_days': leave_type.max_days, 'used_days': 0}
            )
            
            # Check if this is an update of existing application
            if self.instance and self.instance.pk:
                # If updating an approved application, subtract the old days first
                if self.instance.status == 'A':
                    old_delta = self.instance.end_date - self.instance.start_date
                    old_business_days = 0
                    for i in range(old_delta.days + 1):
                        day = self.instance.start_date + timedelta(days=i)
                        if day.weekday() < 5:
                            old_business_days += 1
                    
                    # Temporarily add back the old days for validation
                    available_days = leave_balance.remaining_days + old_business_days
                else:
                    available_days = leave_balance.remaining_days
            else:
                available_days = leave_balance.remaining_days
            
            if business_days > available_days:
                raise forms.ValidationError(
                    _('Not enough leave balance. Available: %(available)s days, Requested: %(requested)s days') % {
                        'available': available_days,
                        'requested': business_days
                    }
                )
        
        return cleaned_data

class LeaveListView(LoginRequiredMixin, ListView):
    model = LeaveApplication
    template_name = 'leave/leave_list.html'
    context_object_name = 'leaves'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = LeaveApplication.objects.select_related('employee', 'leave_type', 'approved_by')
        
        # Non-staff and non-superuser users see only their own leaves
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        # Apply filters
        try:
            from hr_payroll.models import Employee
            if self.request.user.is_staff or self.request.user.is_superuser:
                # Staff can see all employees in their company
                user_employee = Employee.objects.get(user=self.request.user)
                self.filter_form = LeaveFilterForm(self.request.GET, employee=user_employee)
            else:
                # Regular users only see their own data
                employee = Employee.objects.get(user=self.request.user)
                self.filter_form = LeaveFilterForm(self.request.GET, employee=employee)
        except Employee.DoesNotExist:
            self.filter_form = LeaveFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(employee__name__icontains=data['search']) |
                    Q(reason__icontains=data['search'])
                )
            
            if data.get('leave_type'):
                queryset = queryset.filter(leave_type=data['leave_type'])
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('start_date_from'):
                queryset = queryset.filter(start_date__gte=data['start_date_from'])
            
            if data.get('start_date_to'):
                queryset = queryset.filter(start_date__lte=data['start_date_to'])
        
        return queryset.order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_leaves'] = queryset.count()
        context['pending_count'] = queryset.filter(status='P').count()
        context['approved_count'] = queryset.filter(status='A').count()
        context['rejected_count'] = queryset.filter(status='R').count()
        context['filter_form'] = self.filter_form
        
        # Add leave balances for current user
        try:
            from hr_payroll.models import Employee
            if self.request.user.is_staff or self.request.user.is_superuser:
                # Staff can see all leave balances in their company
                employee = Employee.objects.get(user=self.request.user)
                leave_balances = LeaveBalance.objects.filter(
                    employee__company=employee.company
                ).select_related('leave_type', 'employee')
            else:
                # Regular users see only their own leave balances
                employee = Employee.objects.get(user=self.request.user)
                leave_balances = LeaveBalance.objects.filter(employee=employee).select_related('leave_type')
            context['leave_balances'] = leave_balances
        except Employee.DoesNotExist:
            context['leave_balances'] = []
            # Add a message for users without employee profiles
            if not self.request.user.is_staff and not self.request.user.is_superuser:
                messages.warning(self.request, _('No employee profile found for your account. Please contact administrator to create your employee profile before applying for leaves.'))
        
        # Add user permissions context
        context['is_staff_or_superuser'] = self.request.user.is_staff or self.request.user.is_superuser
        
        # Add debug info for employee profile
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            context['has_employee_profile'] = True
            context['user_employee'] = employee
        except Employee.DoesNotExist:
            context['has_employee_profile'] = False
            context['user_employee'] = None
        
        return context
class LeaveCreateView(LoginRequiredMixin, CreateView):
    model = LeaveApplication
    form_class = LeaveApplicationForm
    template_name = 'leave/leave_form.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has an employee record
        if not request.user.is_staff and not request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                messages.error(request, _('No employee profile found for your account. Please contact administrator to create your employee profile.'))
                return redirect('zkteco:leave_list')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            from hr_payroll.models import Employee
            
            # Non-staff users can only create leaves for themselves
            if not self.request.user.is_staff and not self.request.user.is_superuser:
                employee = Employee.objects.get(user=self.request.user)
                form.instance.employee = employee
            
            # If no employee selected and user is staff, require selection
            if not form.instance.employee:
                if self.request.user.is_staff or self.request.user.is_superuser:
                    messages.error(self.request, _('Please select an employee.'))
                    return self.form_invalid(form)
                else:
                    employee = Employee.objects.get(user=self.request.user)
                    form.instance.employee = employee
            
            messages.success(self.request, _('Leave application submitted successfully!'))
            return super().form_valid(form)
            
        except Employee.DoesNotExist:
            messages.error(self.request, _('No employee profile found for your account. Please contact administrator to create your employee profile.'))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class LeaveUpdateView(LoginRequiredMixin, UpdateView):
    model = LeaveApplication
    form_class = LeaveApplicationForm
    template_name = 'leave/leave_form.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def get_queryset(self):
        queryset = LeaveApplication.objects.all()
        
        # Non-staff users can only update their own leaves
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        return queryset
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has an employee record
        if not request.user.is_staff and not request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                messages.error(request, _('No employee profile found for your account. Please contact administrator to create your employee profile.'))
                return redirect('zkteco:leave_list')
        
        # Check permissions before processing
        obj = self.get_object()
        
        # Check if non-staff user can edit this leave
        if not request.user.is_staff and not request.user.is_superuser:
            # Non-staff users cannot edit approved leaves
            if obj.status == 'A':
                messages.error(request, _('You cannot edit an approved leave application.'))
                return redirect('zkteco:leave_list')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        old_status = self.get_object().status
        new_status = form.instance.status
        
        # Non-staff users cannot change status
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            if old_status != new_status:
                messages.error(self.request, _('You cannot change the leave status.'))
                return self.form_invalid(form)
        
        # Update leave balance if status changed to/from approved (only for staff)
        if (self.request.user.is_staff or self.request.user.is_superuser) and old_status != new_status and (old_status == 'A' or new_status == 'A'):
            self.update_leave_balance(form.instance, old_status, new_status)
        
        messages.success(self.request, _('Leave application updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)
    
    def update_leave_balance(self, leave_application, old_status, new_status):
        """Update leave balance when leave status changes"""
        # Calculate business days
        delta = leave_application.end_date - leave_application.start_date
        business_days = 0
        for i in range(delta.days + 1):
            day = leave_application.start_date + timedelta(days=i)
            if day.weekday() < 5:  # Monday to Friday
                business_days += 1
        
        # Get or create leave balance
        leave_balance, created = LeaveBalance.objects.get_or_create(
            employee=leave_application.employee,
            leave_type=leave_application.leave_type,
            defaults={
                'entitled_days': leave_application.leave_type.max_days,
                'used_days': 0
            }
        )
        
        # Update used days based on status change
        if old_status == 'A' and new_status != 'A':
            # Removing approved status, subtract used days
            leave_balance.used_days = max(0, leave_balance.used_days - business_days)
        elif new_status == 'A' and old_status != 'A':
            # Adding approved status, add used days
            leave_balance.used_days += business_days
        
        leave_balance.save()


class LeaveDeleteView(LoginRequiredMixin, DeleteView):
    model = LeaveApplication
    template_name = 'leave/leave_confirm_delete.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def get_queryset(self):
        queryset = LeaveApplication.objects.all()
        
        # Non-staff users can only delete their own leaves
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        return queryset
    
    def dispatch(self, request, *args, **kwargs):
        # Check permissions before processing
        obj = self.get_object()
        
        # Check if non-staff user can delete this leave
        if not request.user.is_staff and not request.user.is_superuser:
            # Non-staff users cannot delete approved leaves
            if obj.status == 'A':
                messages.error(request, _('You cannot delete an approved leave application.'))
                return redirect('zkteco:leave_list')
        
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        leave_application = self.get_object()
        
        # If deleting an approved application, update leave balance (only staff can do this)
        if leave_application.status == 'A' and (request.user.is_staff or request.user.is_superuser):
            self.update_leave_balance_on_delete(leave_application)
        
        messages.success(request, _('Leave application deleted successfully!'))
        return super().delete(request, *args, **kwargs)
    
    def update_leave_balance_on_delete(self, leave_application):
        """Update leave balance when approved leave is deleted"""
        # Calculate business days
        delta = leave_application.end_date - leave_application.start_date
        business_days = 0
        for i in range(delta.days + 1):
            day = leave_application.start_date + timedelta(days=i)
            if day.weekday() < 5:  # Monday to Friday
                business_days += 1
        
        try:
            leave_balance = LeaveBalance.objects.get(
                employee=leave_application.employee,
                leave_type=leave_application.leave_type
            )
            leave_balance.used_days = max(0, leave_balance.used_days - business_days)
            leave_balance.save()
        except LeaveBalance.DoesNotExist:
            pass


class LeaveDetailView(LoginRequiredMixin, DetailView):
    model = LeaveApplication
    template_name = 'leave/leave_detail.html'
    context_object_name = 'leave'
    
    def get_queryset(self):
        queryset = LeaveApplication.objects.select_related('employee', 'leave_type', 'approved_by')
        
        # Non-staff users can only view their own leaves
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate business days for this leave
        leave = self.get_object()
        delta = leave.end_date - leave.start_date
        business_days = 0
        for i in range(delta.days + 1):
            day = leave.start_date + timedelta(days=i)
            if day.weekday() < 5:  # Monday to Friday
                business_days += 1
        context['business_days'] = business_days
        
        # Get leave balance for this employee and leave type
        try:
            leave_balance = LeaveBalance.objects.get(
                employee=leave.employee,
                leave_type=leave.leave_type
            )
            context['leave_balance'] = leave_balance
        except LeaveBalance.DoesNotExist:
            context['leave_balance'] = None
        
        # Get all leave balances for this employee
        leave_balances = LeaveBalance.objects.filter(employee=leave.employee).select_related('leave_type')
        context['all_leave_balances'] = leave_balances
        
        return context


class LeaveStatusChangeView(LoginRequiredMixin, UpdateView):
    """API view for changing leave status (approve/reject) - Only for staff"""
    model = LeaveApplication
    fields = ['status', 'approved_by']
    
    def dispatch(self, request, *args, **kwargs):
        # Only staff and superusers can change leave status
        if not request.user.is_staff and not request.user.is_superuser:
            messages.error(request, _('You do not have permission to change leave status.'))
            return redirect('zkteco:leave_list')
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        leave = self.get_object()
        old_status = leave.status
        new_status = request.POST.get('status')
        
        if new_status in ['A', 'R']:
            leave.status = new_status
            leave.approved_by = request.user
            leave.save()
            
            # Update leave balance if status changed to/from approved
            if old_status != new_status and (old_status == 'A' or new_status == 'A'):
                self.update_leave_balance(leave, old_status, new_status)
            
            status_text = 'approved' if new_status == 'A' else 'rejected'
            messages.success(request, _(f'Leave application {status_text} successfully!'))
        else:
            messages.error(request, _('Invalid status provided.'))
        
        return redirect('zkteco:leave_detail', pk=leave.pk)
    
    def update_leave_balance(self, leave_application, old_status, new_status):
        """Update leave balance when leave status changes"""
        # Calculate business days
        delta = leave_application.end_date - leave_application.start_date
        business_days = 0
        for i in range(delta.days + 1):
            day = leave_application.start_date + timedelta(days=i)
            if day.weekday() < 5:  # Monday to Friday
                business_days += 1
        
        # Get or create leave balance
        leave_balance, created = LeaveBalance.objects.get_or_create(
            employee=leave_application.employee,
            leave_type=leave_application.leave_type,
            defaults={
                'entitled_days': leave_application.leave_type.max_days,
                'used_days': 0
            }
        )
        
        # Update used days based on status change
        if old_status == 'A' and new_status != 'A':
            # Removing approved status, subtract used days
            leave_balance.used_days = max(0, leave_balance.used_days - business_days)
        elif new_status == 'A' and old_status != 'A':
            # Adding approved status, add used days
            leave_balance.used_days += business_days
        
        leave_balance.save()