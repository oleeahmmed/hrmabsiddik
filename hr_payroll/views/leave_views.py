# leave_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum
from django.contrib import messages
from django import forms
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta
from ..models import LeaveApplication, LeaveType, LeaveBalance, Employee
from core.models import Company


# ==================== LEAVE APPLICATION MANAGEMENT ====================

class LeaveFilterForm(forms.Form):
    """Form for filtering leave applications in the list view"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by employee name or ID...',
        }),
        label=_('Search')
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status')] + list(LeaveApplication.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Status')
    )
    
    leave_type = forms.ModelChoiceField(
        required=False,
        queryset=LeaveType.objects.none(),
        empty_label='All Leave Types',
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Leave Type')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date'
        }),
        label=_('From Date')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date'
        }),
        label=_('To Date')
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter leave types by company
        if user:
            active_company = Company.objects.filter(is_active=True).first()
            if active_company:
                self.fields['leave_type'].queryset = LeaveType.objects.filter(
                    company=active_company
                )


class LeaveApplicationForm(forms.ModelForm):
    """ModelForm for Leave Application with proper validation"""
    
    class Meta:
        model = LeaveApplication
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'input',
            }),
            'leave_type': forms.Select(attrs={
                'class': 'input',
            }),
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
                'rows': 4,
                'placeholder': 'Enter reason for leave...'
            }),
        }
        labels = {
            'employee': _('Employee'),
            'leave_type': _('Leave Type'),
            'start_date': _('Start Date'),
            'end_date': _('End Date'),
            'reason': _('Reason'),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        active_company = Company.objects.filter(is_active=True).first()
        
        # If user is not staff/superuser, filter to show only their employee
        if user and not (user.is_staff or user.is_superuser):
            try:
                employee = Employee.objects.get(user=user, company=active_company)
                self.fields['employee'].queryset = Employee.objects.filter(pk=employee.pk)
                self.fields['employee'].initial = employee
                self.fields['employee'].widget.attrs['readonly'] = True
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()
        else:
            # Staff/superuser can see all employees
            if active_company:
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=active_company
                ).order_by('employee_id')
        
        # Filter leave types by company
        if active_company:
            self.fields['leave_type'].queryset = LeaveType.objects.filter(
                company=active_company
            )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        employee = cleaned_data.get('employee')
        leave_type = cleaned_data.get('leave_type')
        
        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError(
                    _('End date cannot be earlier than start date')
                )
            
            # Check for overlapping leave applications
            if employee:
                overlapping = LeaveApplication.objects.filter(
                    employee=employee,
                    status__in=['P', 'A']  # Pending or Approved
                ).filter(
                    Q(start_date__lte=end_date, end_date__gte=start_date)
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if overlapping.exists():
                    raise forms.ValidationError(
                        _('This employee already has a leave application for overlapping dates')
                    )
            
            # Check leave balance
            if employee and leave_type:
                days_requested = (end_date - start_date).days + 1
                try:
                    balance = LeaveBalance.objects.get(
                        employee=employee,
                        leave_type=leave_type
                    )
                    if balance.remaining_days < days_requested:
                        raise forms.ValidationError(
                            _('Insufficient leave balance. Available: %(days)s days') % {
                                'days': balance.remaining_days
                            }
                        )
                except LeaveBalance.DoesNotExist:
                    pass  # No balance check if not set up
        
        return cleaned_data


class LeaveListView(LoginRequiredMixin, ListView):
    model = LeaveApplication
    template_name = 'leave/leave_list.html'
    context_object_name = 'leaves'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = LeaveApplication.objects.select_related(
            'employee', 'leave_type', 'approved_by'
        )
        
        # Filter by company
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(employee__company=active_company)
        
        # If user is not staff/superuser, show only their leaves
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            try:
                employee = Employee.objects.get(
                    user=self.request.user,
                    company=active_company
                )
                queryset = queryset.filter(employee=employee)
            except Employee.DoesNotExist:
                queryset = queryset.none()
        
        # Apply filters
        self.filter_form = LeaveFilterForm(
            self.request.GET,
            user=self.request.user
        )
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(employee__name__icontains=data['search']) |
                    Q(employee__employee_id__icontains=data['search'])
                )
            
            if data.get('status'):
                queryset = queryset.filter(status=data['status'])
            
            if data.get('leave_type'):
                queryset = queryset.filter(leave_type=data['leave_type'])
            
            if data.get('date_from'):
                queryset = queryset.filter(start_date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(end_date__lte=data['date_to'])
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['filter_form'] = self.filter_form
        
        # Statistics
        context['total_leaves'] = queryset.count()
        context['pending_leaves'] = queryset.filter(status='P').count()
        context['approved_leaves'] = queryset.filter(status='A').count()
        context['rejected_leaves'] = queryset.filter(status='R').count()
        
        # User permissions
        context['is_staff_or_admin'] = (
            self.request.user.is_staff or self.request.user.is_superuser
        )
        
        return context


class LeaveCreateView(LoginRequiredMixin, CreateView):
    model = LeaveApplication
    form_class = LeaveApplicationForm
    template_name = 'leave/leave_form.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set default status to Pending
        form.instance.status = 'P'
        
        messages.success(
            self.request,
            _('Leave application submitted successfully!')
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            _('Please correct the errors below.')
        )
        return super().form_invalid(form)


class LeaveUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = LeaveApplication
    form_class = LeaveApplicationForm
    template_name = 'leave/leave_form.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def test_func(self):
        leave = self.get_object()
        user = self.request.user
        
        # Staff/superuser can edit any leave
        if user.is_staff or user.is_superuser:
            return True
        
        # Regular users can only edit their own PENDING leaves
        try:
            employee = Employee.objects.get(user=user)
            return (
                leave.employee == employee and
                leave.status == 'P'  # Only pending leaves
            )
        except Employee.DoesNotExist:
            return False
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(
            self.request,
            _('Leave application updated successfully!')
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            _('Please correct the errors below.')
        )
        return super().form_invalid(form)


class LeaveDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = LeaveApplication
    template_name = 'leave/leave_confirm_delete.html'
    success_url = reverse_lazy('zkteco:leave_list')
    
    def test_func(self):
        leave = self.get_object()
        user = self.request.user
        
        # Staff/superuser can delete any leave
        if user.is_staff or user.is_superuser:
            return True
        
        # Regular users can only delete their own PENDING leaves
        try:
            employee = Employee.objects.get(user=user)
            return (
                leave.employee == employee and
                leave.status == 'P'  # Only pending leaves
            )
        except Employee.DoesNotExist:
            return False
    
    def delete(self, request, *args, **kwargs):
        messages.success(
            request,
            _('Leave application deleted successfully!')
        )
        return super().delete(request, *args, **kwargs)


class LeaveDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = LeaveApplication
    template_name = 'leave/leave_detail.html'
    context_object_name = 'leave'
    
    def test_func(self):
        leave = self.get_object()
        user = self.request.user
        
        # Staff/superuser can view any leave
        if user.is_staff or user.is_superuser:
            return True
        
        # Regular users can only view their own leaves
        try:
            employee = Employee.objects.get(user=user)
            return leave.employee == employee
        except Employee.DoesNotExist:
            return False
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        leave = self.get_object()
        
        # Calculate leave duration in business days
        delta = leave.end_date - leave.start_date
        business_days = 0
        for i in range(delta.days + 1):
            day = leave.start_date + timedelta(days=i)
            if day.weekday() < 5:  # Monday to Friday
                business_days += 1
        
        context['business_days'] = business_days
        
        # Get leave balance
        try:
            balance = LeaveBalance.objects.get(
                employee=leave.employee,
                leave_type=leave.leave_type
            )
            context['leave_balance'] = balance
        except LeaveBalance.DoesNotExist:
            context['leave_balance'] = None
        
        # User permissions
        context['is_staff_or_admin'] = (
            self.request.user.is_staff or self.request.user.is_superuser
        )
        context['can_edit'] = (
            (self.request.user.is_staff or self.request.user.is_superuser) or
            (leave.status == 'P' and leave.employee.user == self.request.user)
        )
        context['can_delete'] = context['can_edit']
        
        return context


class LeaveStatusChangeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """API view to change leave status (Approve/Reject)"""
    permission_required = 'hr_payroll.change_leaveapplication'
    
    def post(self, request, pk):
        leave = get_object_or_404(LeaveApplication, pk=pk)
        new_status = request.POST.get('status')
        
        if new_status not in ['A', 'R']:
            return JsonResponse({
                'success': False,
                'message': 'Invalid status'
            }, status=400)
        
        # Update status
        leave.status = new_status
        leave.approved_by = request.user
        leave.save()
        
        status_text = 'Approved' if new_status == 'A' else 'Rejected'
        
        return JsonResponse({
            'success': True,
            'message': f'Leave application {status_text.lower()} successfully',
            'status': new_status,
            'status_display': leave.get_status_display()
        })