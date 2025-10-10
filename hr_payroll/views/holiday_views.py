# holiday_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import Holiday
from core.models import Company


# ==================== HOLIDAY MANAGEMENT ====================

class HolidayFilterForm(forms.Form):
    """Form for filtering holidays in the list view"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by holiday name...',
        }),
        label=_('Search')
    )
    
    year = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(attrs={'class': 'input'}),
        label=_('Year')
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Get available years from existing holidays
        years = Holiday.objects.dates('date', 'year').order_by('-date')
        year_choices = [('', 'All Years')] + [(year.year, str(year.year)) for year in years]
        self.fields['year'].choices = year_choices


class HolidayForm(forms.ModelForm):
    """ModelForm for Holiday with proper validation"""
    
    class Meta:
        model = Holiday
        fields = ['name', 'date', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter holiday name...'
            }),
            'date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date'
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'rows': 3,
                'placeholder': 'Enter holiday description...'
            }),
        }
        labels = {
            'name': _('Holiday Name'),
            'date': _('Holiday Date'),
            'description': _('Description'),
        }
        help_texts = {
            'date': _('Select the date of the holiday'),
            'description': _('Optional description about the holiday'),
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
        date = cleaned_data.get('date')
        company = self.instance.company
        
        if date and company:
            # Check for duplicate holiday date for the same company
            existing_holiday = Holiday.objects.filter(
                company=company,
                date=date
            ).exclude(pk=self.instance.pk).first()
            
            if existing_holiday:
                raise forms.ValidationError(
                    _('A holiday already exists for this date: %(holiday_name)s') % {
                        'holiday_name': existing_holiday.name
                    }
                )
        
        return cleaned_data


class HolidayListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Holiday
    template_name = 'holiday/holiday_list.html'
    context_object_name = 'holidays'
    paginate_by = 10
    permission_required = 'hr_payroll.view_holiday'
    
    def get_queryset(self):
        queryset = Holiday.objects.all()
        
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        
        # Apply filters
        self.filter_form = HolidayFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(name__icontains=data['search'])
                )
            
            if data.get('year'):
                queryset = queryset.filter(date__year=data['year'])
        
        return queryset.order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_holidays'] = queryset.count()
        context['filter_form'] = self.filter_form
        
        # Statistics
        current_year = timezone.now().year
        current_year_holidays = queryset.filter(date__year=current_year)
        context['current_year_count'] = current_year_holidays.count()
        
        # Upcoming holidays (next 30 days)
        today = timezone.now().date()
        next_30_days = today + timezone.timedelta(days=30)
        context['upcoming_holidays'] = queryset.filter(
            date__gte=today,
            date__lte=next_30_days
        ).order_by('date')[:5]
        
        return context


class HolidayCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Holiday
    form_class = HolidayForm
    template_name = 'holiday/holiday_form.html'
    success_url = reverse_lazy('zkteco:holiday_list')
    permission_required = 'hr_payroll.add_holiday'
    
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
        
        messages.success(self.request, _('Holiday created successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class HolidayUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Holiday
    form_class = HolidayForm
    template_name = 'holiday/holiday_form.html'
    success_url = reverse_lazy('zkteco:holiday_list')
    permission_required = 'hr_payroll.change_holiday'
    
    def get_queryset(self):
        queryset = Holiday.objects.all()
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
        messages.success(self.request, _('Holiday updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class HolidayDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Holiday
    template_name = 'holiday/holiday_confirm_delete.html'
    success_url = reverse_lazy('zkteco:holiday_list')
    permission_required = 'hr_payroll.delete_holiday'
    
    def get_queryset(self):
        queryset = Holiday.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get today's date for comparison
        context['today'] = timezone.now().date()
        
        # Get attendance records for this holiday
        from ..models import Attendance
        attendance_on_holiday = Attendance.objects.filter(
            date=self.object.date,
            status='H'
        )
        context['attendance_on_holiday_count'] = attendance_on_holiday.count()
        
        return context
    
    def delete(self, request, *args, **kwargs):
        holiday = self.get_object()
        
        # Check if holiday is in the past
        if holiday.date < timezone.now().date():
            messages.warning(request, _('This holiday is in the past. It may have been used in attendance calculations.'))
        
        messages.success(request, _('Holiday deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class HolidayDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Holiday
    template_name = 'holiday/holiday_detail.html'
    context_object_name = 'holiday'
    permission_required = 'hr_payroll.view_holiday'
    
    def get_queryset(self):
        queryset = Holiday.objects.all()
        # Filter by company from core app
        active_company = Company.objects.filter(is_active=True).first()
        if active_company:
            queryset = queryset.filter(company=active_company)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        holiday = self.get_object()
        
        # Get related attendance records for this holiday
        from ..models import Attendance
        attendance_on_holiday = Attendance.objects.filter(
            date=holiday.date,
            status='H'
        ).select_related('employee')
        context['attendance_on_holiday'] = attendance_on_holiday
        
        # Check if it's a recurring holiday (same date in previous years)
        same_date_holidays = Holiday.objects.filter(
            company=holiday.company,
            date__month=holiday.date.month,
            date__day=holiday.date.day
        ).exclude(pk=holiday.pk).order_by('-date')
        context['recurring_holidays'] = same_date_holidays
        
        return context