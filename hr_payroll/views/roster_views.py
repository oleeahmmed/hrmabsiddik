# roster_views.py - ENHANCED WITH BETTER ERROR HANDLING
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count
from django.contrib import messages
from django import forms
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from django.db import transaction
from ..models import Roster, RosterAssignment, RosterDay, Employee, Shift, Company
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# ==================== FORMS ====================

class RosterForm(forms.ModelForm):
    """Form for Roster with enhanced validation"""
    
    class Meta:
        model = Roster
        fields = ['name', 'start_date', 'end_date', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter roster name (e.g., Weekly Schedule - Jan 2025)',
                'required': True,
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date',
                'required': True,
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'input',
                'type': 'date',
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'input',
                'rows': 3,
                'placeholder': 'Optional description (e.g., Monthly roster for production team)',
            }),
        }
        labels = {
            'name': _('Roster Name'),
            'start_date': _('Start Date'),
            'end_date': _('End Date'),
            'description': _('Description'),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['name'].help_text = 'Unique name for this roster'
        self.fields['start_date'].help_text = 'First day of the roster period'
        self.fields['end_date'].help_text = 'Last day of the roster period'
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        
        if not name or len(name.strip()) < 3:
            raise forms.ValidationError(
                _('Roster name must be at least 3 characters long.')
            )
        
        # Check for duplicate names in the same company
        if self.user and hasattr(self.user, 'employee'):
            company = self.user.employee.company
            existing = Roster.objects.filter(
                company=company,
                name__iexact=name
            )
            
            # Exclude current instance in update mode
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError(
                    _('A roster with this name already exists in your company.')
                )
        
        return name.strip()
    
    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        
        if not start_date:
            raise forms.ValidationError(_('Start date is required.'))
        
        return start_date
    
    def clean_end_date(self):
        end_date = self.cleaned_data.get('end_date')
        
        if not end_date:
            raise forms.ValidationError(_('End date is required.'))
        
        return end_date
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError(
                    _('End date must be after or equal to start date.')
                )
            
            # Check if duration is too long (more than 365 days)
            duration = (end_date - start_date).days + 1
            if duration > 365:
                raise forms.ValidationError(
                    _('Roster duration cannot exceed 365 days. Current duration: %(days)s days.') % {'days': duration}
                )
            
            logger.info(f"Roster duration: {duration} days")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set company from user - with fallback
        if self.user and hasattr(self.user, 'employee'):
            instance.company = self.user.employee.company
            logger.info(f"Setting company: {instance.company}")
        else:
            # Fallback: get first company or handle differently
            first_company = Company.objects.first()
            if first_company:
                instance.company = first_company
                logger.warning(f"User has no employee profile, using first company: {first_company}")
            else:
                logger.error("No companies found in database!")
                raise forms.ValidationError(_('No company found. Please contact administrator.'))
        
        if commit:
            instance.save()
            logger.info(f"Roster saved: {instance.pk} - {instance.name}")
        
        return instance


class RosterAssignmentInlineForm(forms.ModelForm):
    """Form for RosterAssignment in the formset"""
    
    class Meta:
        model = RosterAssignment
        fields = ['employee', 'shift']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'input',
                'required': True,
            }),
            'shift': forms.Select(attrs={
                'class': 'input',
                'required': True,
            }),
        }
        labels = {
            'employee': _('Employee'),
            'shift': _('Default Shift'),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter by company
        if self.user:
            # Get company from user's employee profile or use first company
            company = None
            if hasattr(self.user, 'employee'):
                company = self.user.employee.company
            else:
                company = Company.objects.first()
            
            if company:
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=company,
                    is_active=True
                ).order_by('first_name', 'last_name')
                
                self.fields['shift'].queryset = Shift.objects.filter(
                    company=company
                ).order_by('name')
                
                logger.info(f"Available employees: {self.fields['employee'].queryset.count()}")
                logger.info(f"Available shifts: {self.fields['shift'].queryset.count()}")
        
        # Make fields required
        self.fields['employee'].required = True
        self.fields['shift'].required = True
    
    def clean_employee(self):
        employee = self.cleaned_data.get('employee')
        
        # Skip validation if form is marked for deletion
        if self.cleaned_data.get('DELETE'):
            return employee
        
        if not employee:
            raise forms.ValidationError(_('Employee is required.'))
        
        return employee
    
    def clean_shift(self):
        shift = self.cleaned_data.get('shift')
        
        # Skip validation if form is marked for deletion
        if self.cleaned_data.get('DELETE'):
            return shift
        
        if not shift:
            raise forms.ValidationError(_('Shift is required.'))
        
        return shift
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Skip validation if form is marked for deletion
        if cleaned_data.get('DELETE'):
            return cleaned_data
        
        employee = cleaned_data.get('employee')
        shift = cleaned_data.get('shift')
        
        # Both fields must be filled
        if not employee and not shift:
            # Empty form is okay, will be filtered out
            return cleaned_data
        
        if not employee:
            self.add_error('employee', _('Employee is required when shift is selected.'))
        
        if not shift:
            self.add_error('shift', _('Shift is required when employee is selected.'))
        
        return cleaned_data


# Create inline formset for RosterAssignment
RosterAssignmentFormSet = inlineformset_factory(
    Roster,
    RosterAssignment,
    form=RosterAssignmentInlineForm,
    extra=1,  # One extra form by default
    can_delete=True,
    min_num=0,  # Set to 0 to handle custom validation
    validate_min=False,
)


# ==================== ROSTER VIEWS ====================

class RosterListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Roster
    template_name = 'roster/roster_list.html'
    context_object_name = 'rosters'
    paginate_by = 10
    permission_required = 'hr_payroll.view_roster'
    
    def get_queryset(self):
        queryset = Roster.objects.annotate(
            assignment_count=Count('roster_assignments')
        )
        
        if not self.request.user.is_superuser:
            # Get company from user's employee profile or use first company
            company = None
            if hasattr(self.request.user, 'employee'):
                company = self.request.user.employee.company
            else:
                company = Company.objects.first()
            
            if company:
                queryset = queryset.filter(company=company)
        
        # Apply search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset.order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_rosters'] = self.get_queryset().count()
        return context


class RosterCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Roster
    form_class = RosterForm
    template_name = 'roster/roster_form.html'
    success_url = reverse_lazy('zkteco:roster_list')
    permission_required = 'hr_payroll.add_roster'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        logger.info("=== GET FORM KWARGS ===")
        logger.info(f"User: {self.request.user}")
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = False
        
        logger.info("=== GET CONTEXT DATA ===")
        
        if self.request.POST:
            logger.info("Processing POST data for formset")
            context['assignment_formset'] = RosterAssignmentFormSet(
                self.request.POST,
                instance=self.object,
                form_kwargs={'user': self.request.user}
            )
        else:
            logger.info("Creating empty formset")
            context['assignment_formset'] = RosterAssignmentFormSet(
                instance=self.object,
                form_kwargs={'user': self.request.user}
            )
        
        logger.info(f"Formset has {len(context['assignment_formset'].forms)} forms")
        
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        assignment_formset = context['assignment_formset']
        
        logger.info("=" * 60)
        logger.info("=== ROSTER CREATE - FORM VALIDATION START ===")
        logger.info("=" * 60)
        logger.info(f"Main form valid: {form.is_valid()}")
        logger.info(f"Main form data: {form.cleaned_data}")
        logger.info(f"Formset valid: {assignment_formset.is_valid()}")
        logger.info(f"Total formset forms: {len(assignment_formset.forms)}")
        
        # Log each form in formset
        for i, formset_form in enumerate(assignment_formset.forms):
            logger.info(f"--- Form {i} ---")
            logger.info(f"Is valid: {formset_form.is_valid()}")
            logger.info(f"Data: {formset_form.cleaned_data if formset_form.is_valid() else 'INVALID'}")
            logger.info(f"Errors: {formset_form.errors}")
        
        # Validate main form
        if not form.is_valid():
            logger.error("Main form is invalid!")
            logger.error(f"Form errors: {form.errors}")
            messages.error(
                self.request,
                _('Please correct the errors in the roster information.')
            )
            return self.form_invalid(form)
        
        # Validate formset
        if not assignment_formset.is_valid():
            logger.error("Formset is invalid!")
            logger.error(f"Formset errors: {assignment_formset.errors}")
            logger.error(f"Non-form errors: {assignment_formset.non_form_errors()}")
            
            # Show specific errors
            for i, formset_form in enumerate(assignment_formset.forms):
                if formset_form.errors:
                    logger.error(f"Form {i} errors: {formset_form.errors}")
            
            messages.error(
                self.request,
                _('Please correct the errors in employee assignments.')
            )
            return self.form_invalid(form)
        
        # Check if at least one valid assignment exists
        valid_forms = [
            f for f in assignment_formset.forms
            if f.cleaned_data and not f.cleaned_data.get('DELETE', False) and f.cleaned_data.get('employee')
        ]
        
        logger.info(f"Valid assignment forms count: {len(valid_forms)}")
        
        if not valid_forms:
            logger.error("No valid employee assignments found!")
            messages.error(
                self.request,
                _('Please add at least one employee assignment with both employee and shift selected.')
            )
            return self.form_invalid(form)
        
        # Check for duplicate employees
        employee_ids = [f.cleaned_data['employee'].id for f in valid_forms]
        if len(employee_ids) != len(set(employee_ids)):
            logger.error("Duplicate employees found!")
            messages.error(
                self.request,
                _('Each employee can only be assigned once. Please remove duplicate employees.')
            )
            return self.form_invalid(form)
        
        try:
            with transaction.atomic():
                # Save roster
                self.object = form.save()
                logger.info(f"✓ Roster saved: ID={self.object.pk}, Name={self.object.name}")
                
                # Save assignments
                assignment_formset.instance = self.object
                assignments = assignment_formset.save()
                logger.info(f"✓ Saved {len(assignments)} assignments")
                
                # Create roster days for each assignment
                total_days = 0
                for assignment in assignments:
                    days = self.create_roster_days(assignment)
                    total_days += days
                    logger.info(f"✓ Created {days} days for {assignment.employee.get_full_name()}")
                
                logger.info("=" * 60)
                logger.info(f"✓✓✓ SUCCESS: Roster created with {len(assignments)} employees and {total_days} total days")
                logger.info("=" * 60)
                
                messages.success(
                    self.request,
                    _(f'Roster "{self.object.name}" created successfully with {len(assignments)} employee(s) and {total_days} scheduled days!')
                )
                return redirect(self.success_url)
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"✗✗✗ ERROR SAVING ROSTER: {str(e)}")
            logger.error("=" * 60)
            logger.exception(e)
            
            messages.error(
                self.request,
                _(f'Error saving roster: {str(e)}. Please try again or contact support.')
            )
            return self.form_invalid(form)
    
    def create_roster_days(self, assignment):
        """Create roster days for the entire period"""
        roster = assignment.roster
        current_date = roster.start_date
        
        days_created = 0
        while current_date <= roster.end_date:
            RosterDay.objects.create(
                roster_assignment=assignment,
                date=current_date,
                shift=assignment.shift
            )
            days_created += 1
            current_date += timedelta(days=1)
        
        return days_created
    
    def form_invalid(self, form):
        logger.error("=" * 60)
        logger.error("=== FORM INVALID ===")
        logger.error(f"Form errors: {form.errors}")
        
        context = self.get_context_data()
        if 'assignment_formset' in context:
            formset = context['assignment_formset']
            logger.error(f"Formset errors: {formset.errors}")
            logger.error(f"Non-form errors: {formset.non_form_errors()}")
        
        logger.error("=" * 60)
        
        messages.error(
            self.request,
            _('Please correct the errors below. Check the error messages in red.')
        )
        return super().form_invalid(form)


class RosterUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Roster
    form_class = RosterForm
    template_name = 'roster/roster_form.html'
    success_url = reverse_lazy('zkteco:roster_list')
    permission_required = 'hr_payroll.change_roster'
    
    def get_queryset(self):
        queryset = Roster.objects.all()
        if not self.request.user.is_superuser:
            # Get company from user's employee profile or use first company
            company = None
            if hasattr(self.request.user, 'employee'):
                company = self.request.user.employee.company
            else:
                company = Company.objects.first()
            
            if company:
                queryset = queryset.filter(company=company)
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = True
        
        if self.request.POST:
            context['assignment_formset'] = RosterAssignmentFormSet(
                self.request.POST,
                instance=self.object,
                form_kwargs={'user': self.request.user}
            )
        else:
            context['assignment_formset'] = RosterAssignmentFormSet(
                instance=self.object,
                form_kwargs={'user': self.request.user}
            )
        
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        assignment_formset = context['assignment_formset']
        
        logger.info("=== ROSTER UPDATE - VALIDATION ===")
        logger.info(f"Main form valid: {form.is_valid()}")
        logger.info(f"Formset valid: {assignment_formset.is_valid()}")
        
        if not assignment_formset.is_valid():
            logger.error(f"Formset errors: {assignment_formset.errors}")
            messages.error(
                self.request,
                _('Please correct the errors in employee assignments.')
            )
            return self.form_invalid(form)
        
        # Check valid forms
        valid_forms = [
            f for f in assignment_formset.forms
            if f.cleaned_data and not f.cleaned_data.get('DELETE', False) and f.cleaned_data.get('employee')
        ]
        
        if not valid_forms:
            messages.error(
                self.request,
                _('Please add at least one employee assignment.')
            )
            return self.form_invalid(form)
        
        # Check for duplicates
        employee_ids = [f.cleaned_data['employee'].id for f in valid_forms]
        if len(employee_ids) != len(set(employee_ids)):
            messages.error(
                self.request,
                _('Each employee can only be assigned once.')
            )
            return self.form_invalid(form)
        
        try:
            with transaction.atomic():
                # Check if dates changed
                old_start = self.object.start_date
                old_end = self.object.end_date
                
                self.object = form.save()
                
                new_start = self.object.start_date
                new_end = self.object.end_date
                
                # Save assignments
                assignment_formset.instance = self.object
                assignments = assignment_formset.save()
                
                # Handle date changes or new assignments
                for assignment in assignments:
                    # Check if this is a new assignment
                    if not assignment.roster_days.exists():
                        self.create_roster_days(assignment)
                    elif old_start != new_start or old_end != new_end:
                        # Dates changed, recreate roster days
                        assignment.roster_days.all().delete()
                        self.create_roster_days(assignment)
                
                logger.info(f"Updated roster with {len(assignments)} assignments")
                
                messages.success(
                    self.request,
                    _(f'Roster "{self.object.name}" updated successfully!')
                )
                return redirect(self.success_url)
                
        except Exception as e:
            logger.error(f"Error updating: {str(e)}", exc_info=True)
            messages.error(
                self.request,
                _(f'Error updating roster: {str(e)}')
            )
            return self.form_invalid(form)
    
    def create_roster_days(self, assignment):
        """Create roster days for the entire period"""
        roster = assignment.roster
        current_date = roster.start_date
        
        days_created = 0
        while current_date <= roster.end_date:
            RosterDay.objects.create(
                roster_assignment=assignment,
                date=current_date,
                shift=assignment.shift
            )
            days_created += 1
            current_date += timedelta(days=1)
        
        return days_created
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            _('Please correct the errors below.')
        )
        return super().form_invalid(form)


class RosterDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Roster
    template_name = 'roster/roster_confirm_delete.html'
    success_url = reverse_lazy('zkteco:roster_list')
    permission_required = 'hr_payroll.delete_roster'
    
    def get_queryset(self):
        queryset = Roster.objects.all()
        if not self.request.user.is_superuser:
            # Get company from user's employee profile or use first company
            company = None
            if hasattr(self.request.user, 'employee'):
                company = self.request.user.employee.company
            else:
                company = Company.objects.first()
            
            if company:
                queryset = queryset.filter(company=company)
        return queryset
    
    def delete(self, request, *args, **kwargs):
        roster = self.get_object()
        messages.success(
            request,
            _(f'Roster "{roster.name}" deleted successfully!')
        )
        return super().delete(request, *args, **kwargs)


class RosterDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Roster
    template_name = 'roster/roster_detail.html'
    context_object_name = 'roster'
    permission_required = 'hr_payroll.view_roster'
    
    def get_queryset(self):
        queryset = Roster.objects.prefetch_related(
            'roster_assignments__employee',
            'roster_assignments__shift',
            'roster_assignments__roster_days'
        )
        
        if not self.request.user.is_superuser:
            # Get company from user's employee profile or use first company
            company = None
            if hasattr(self.request.user, 'employee'):
                company = self.request.user.employee.company
            else:
                company = Company.objects.first()
            
            if company:
                queryset = queryset.filter(company=company)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        roster = self.get_object()
        context['assignments'] = roster.roster_assignments.all().order_by(
            'employee__first_name'
        )
        context['total_days'] = (roster.end_date - roster.start_date).days + 1
        
        return context