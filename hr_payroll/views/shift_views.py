# shift_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import Roster, RosterAssignment, RosterDay, Shift, Employee
from core.models import Company  # Import from core app


# ==================== SHIFT MANAGEMENT ====================

class ShiftFilterForm(forms.Form):
    """Form for filtering shifts in the list view"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by shift name...',
        }),
        label=_('Search')
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)


class ShiftForm(forms.ModelForm):
    """ModelForm for Shift with proper validation"""
    
    class Meta:
        model = Shift
        fields = ['name', 'start_time', 'end_time', 'break_time', 'grace_time']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter shift name...'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'input',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'input',
                'type': 'time'
            }),
            'break_time': forms.NumberInput(attrs={
                'class': 'input',
                'placeholder': 'Break time in minutes...'
            }),
            'grace_time': forms.NumberInput(attrs={
                'class': 'input',
                'placeholder': 'Grace time in minutes...'
            }),
        }
        labels = {
            'name': _('Shift Name'),
            'start_time': _('Start Time'),
            'end_time': _('End Time'),
            'break_time': _('Break Time (minutes)'),
            'grace_time': _('Grace Time (minutes)'),
        }
        help_texts = {
            'break_time': _('Total break time in minutes'),
            'grace_time': _('Allowed late arrival time in minutes'),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set company based on first active company from core app
        if not self.instance.pk:  # Only for new instances
            active_company = Company.objects.filter(is_active=True).first()
            if active_company:
                self.instance.company = active_company
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if start_time == end_time:
                raise forms.ValidationError(_('Start time and end time cannot be the same.'))
            
            # Calculate duration
            start_datetime = timezone.datetime.combine(timezone.now().date(), start_time)
            end_datetime = timezone.datetime.combine(timezone.now().date(), end_time)
            
            if end_datetime < start_datetime:
                end_datetime += timezone.timedelta(days=1)
            
            duration = end_datetime - start_datetime
            duration_minutes = duration.total_seconds() / 60
            
            if duration_minutes < 60:  # Minimum 1 hour shift
                raise forms.ValidationError(_('Shift duration must be at least 1 hour.'))
        
        return cleaned_data


class ShiftListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Shift
    template_name = 'shift/shift_list.html'
    context_object_name = 'shifts'
    paginate_by = 10
    permission_required = 'hr_payroll.view_shift'
    
    def get_queryset(self):
        queryset = Shift.objects.all()
        
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        
        # Apply filters
        self.filter_form = ShiftFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search'])
                )
        
        return queryset.order_by('start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_shifts'] = queryset.count()
        context['filter_form'] = self.filter_form
        
        return context


class ShiftCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Shift
    form_class = ShiftForm
    template_name = 'shift/shift_form.html'
    success_url = reverse_lazy('zkteco:shift_list')
    permission_required = 'hr_payroll.add_shift'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Set company from core app if not already set
        if not form.instance.company:
            active_company = Company.objects.filter(is_active=True).first()
            if active_company:
                form.instance.company = active_company
        
        messages.success(self.request, _('Shift created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ShiftUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Shift
    form_class = ShiftForm
    template_name = 'shift/shift_form.html'
    success_url = reverse_lazy('zkteco:shift_list')
    permission_required = 'hr_payroll.change_shift'
    
    def get_queryset(self):
        queryset = Shift.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Shift updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class ShiftDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Shift
    template_name = 'shift/shift_confirm_delete.html'
    success_url = reverse_lazy('zkteco:shift_list')
    permission_required = 'hr_payroll.delete_shift'
    
    def get_queryset(self):
        queryset = Shift.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        return queryset
    
    def delete(self, request, *args, **kwargs):
        shift = self.get_object()
        
        # Check if shift is being used by any employee
        from ..models import Employee, RosterAssignment
        employee_count = Employee.objects.filter(default_shift=shift).count()
        roster_count = RosterAssignment.objects.filter(shift=shift).count()
        
        if employee_count > 0 or roster_count > 0:
            messages.error(request, _('Cannot delete shift. It is being used by employees or roster assignments.'))
            return redirect('zkteco:shift_detail', pk=shift.pk)
        
        messages.success(request, _('Shift deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class ShiftDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Shift
    template_name = 'shift/shift_detail.html'
    context_object_name = 'shift'
    permission_required = 'hr_payroll.view_shift'
    
    def get_queryset(self):
        queryset = Shift.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        shift = self.get_object()
        
        # Get employees using this shift as default
        from ..models import Employee
        employees = Employee.objects.filter(default_shift=shift, is_active=True)
        context['employees_using_shift'] = employees
        
        # Get roster assignments using this shift
        from ..models import RosterAssignment
        roster_assignments = RosterAssignment.objects.filter(shift=shift)
        context['roster_assignments'] = roster_assignments
        
        return context


# ==================== ROSTER DAY MANAGEMENT ====================

class RosterDayFilterForm(forms.Form):
    """Form for filtering roster days in the list view"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by employee or roster...',
        }),
        label=_('Search')
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


class RosterDayForm(forms.ModelForm):
    """ModelForm for RosterDay with proper validation"""
    
    class Meta:
        model = RosterDay
        fields = ['roster_assignment', 'date', 'shift']
        widgets = {
            'roster_assignment': forms.Select(attrs={
                'class': 'input',
            }),
            'date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'shift': forms.Select(attrs={
                'class': 'input',
            }),
        }
        labels = {
            'roster_assignment': _('Roster Assignment'),
            'date': _('Date'),
            'shift': _('Shift'),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter roster assignments and shifts by active company
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            self.fields['roster_assignment'].queryset = RosterAssignment.objects.filter(
                roster__company=active_company
            )
            self.fields['shift'].queryset = Shift.objects.filter(company=active_company)
    
    def clean(self):
        cleaned_data = super().clean()
        roster_assignment = cleaned_data.get('roster_assignment')
        date = cleaned_data.get('date')
        
        if roster_assignment and date:
            # Check if date is within roster period
            roster = roster_assignment.roster
            if date < roster.start_date or date > roster.end_date:
                raise forms.ValidationError(
                    _('Date must be within the roster period: %(start)s to %(end)s') % {
                        'start': roster.start_date,
                        'end': roster.end_date
                    }
                )
            
            # Check for duplicate roster day
            existing = RosterDay.objects.filter(
                roster_assignment=roster_assignment,
                date=date
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise forms.ValidationError(
                    _('A roster day already exists for this assignment and date.')
                )
        
        return cleaned_data


class RosterDayListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = RosterDay
    template_name = 'shift/roster_day_list.html'
    context_object_name = 'roster_days'
    paginate_by = 20
    permission_required = 'hr_payroll.view_rosterday'
    
    def get_queryset(self):
        queryset = RosterDay.objects.select_related(
            'roster_assignment__roster',
            'roster_assignment__employee',
            'shift'
        ).all()
        
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(
                roster_assignment__roster__company=active_company
            )
        
        # Apply filters
        self.filter_form = RosterDayFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(roster_assignment__employee__name__icontains=data['search']) |
                    Q(roster_assignment__roster__name__icontains=data['search']) |
                    Q(shift__name__icontains=data['search'])
                )
            
            if data.get('date_from'):
                queryset = queryset.filter(date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(date__lte=data['date_to'])
        
        return queryset.order_by('-date', 'roster_assignment__employee__name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_roster_days'] = queryset.count()
        context['filter_form'] = self.filter_form
        
        # Date range statistics
        if queryset.exists():
            context['date_range_start'] = queryset.last().date
            context['date_range_end'] = queryset.first().date
        
        return context


class RosterDayCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = RosterDay
    form_class = RosterDayForm
    template_name = 'shift/roster_day_form.html'
    success_url = reverse_lazy('zkteco:roster_day_list')
    permission_required = 'hr_payroll.add_rosterday'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Roster day created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class RosterDayUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = RosterDay
    form_class = RosterDayForm
    template_name = 'shift/roster_day_form.html'
    success_url = reverse_lazy('zkteco:roster_day_list')
    permission_required = 'hr_payroll.change_rosterday'
    
    def get_queryset(self):
        queryset = RosterDay.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(
                roster_assignment__roster__company=active_company
            )
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Roster day updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class RosterDayDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = RosterDay
    template_name = 'shift/roster_day_confirm_delete.html'
    success_url = reverse_lazy('zkteco:roster_day_list')
    permission_required = 'hr_payroll.delete_rosterday'
    
    def get_queryset(self):
        queryset = RosterDay.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(
                roster_assignment__roster__company=active_company
            )
        return queryset
    
    def delete(self, request, *args, **kwargs):
        roster_day = self.get_object()
        messages.success(request, _('Roster day deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class RosterDayDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = RosterDay
    template_name = 'shift/roster_day_detail.html'
    context_object_name = 'roster_day'
    permission_required = 'hr_payroll.view_rosterday'
    
    def get_queryset(self):
        queryset = RosterDay.objects.select_related(
            'roster_assignment__roster',
            'roster_assignment__employee',
            'shift'
        ).all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(
                roster_assignment__roster__company=active_company
            )
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        roster_day = self.get_object()
        
        # Get related attendance records if any
        from ..models import Attendance
        attendance_records = Attendance.objects.filter(
            employee=roster_day.roster_assignment.employee,
            date=roster_day.date
        )
        context['attendance_records'] = attendance_records
        
        return context