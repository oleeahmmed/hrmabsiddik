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
from ..models import Roster, RosterAssignment, RosterDay, Shift, Employee, Company


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
        
        # Set company based on user
        if user and hasattr(user, 'employee'):
            self.instance.company = user.employee.company
    
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
        
        # Filter by company for non-superusers
        if not self.request.user.is_superuser and hasattr(self.request.user, 'employee'):
            queryset = queryset.filter(company=self.request.user.employee.company)
        
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
        # Set company for the shift
        if hasattr(self.request.user, 'employee'):
            form.instance.company = self.request.user.employee.company
        
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
        if not self.request.user.is_superuser and hasattr(self.request.user, 'employee'):
            queryset = queryset.filter(company=self.request.user.employee.company)
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
        if not self.request.user.is_superuser and hasattr(self.request.user, 'employee'):
            queryset = queryset.filter(company=self.request.user.employee.company)
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
        if not self.request.user.is_superuser and hasattr(self.request.user, 'employee'):
            queryset = queryset.filter(company=self.request.user.employee.company)
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
    
