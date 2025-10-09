# zkteco/forms.py
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from .models import ZkDevice, Employee, LeaveApplication

class ZkDeviceForm(forms.ModelForm):
    """Form for adding/editing ZKTeco devices"""
    
    # IP address validator
    ip_validator = RegexValidator(
        regex=r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        message=_('Enter a valid IP address.')
    )
    
    class Meta:
        model = ZkDevice
        fields = ['name', 'ip_address', 'port', 'password', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': 'Enter device name (e.g., Main Entrance)',
                'required': True
            }),
            'ip_address': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': '192.168.1.100',
                'pattern': r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
                'title': 'Enter a valid IP address',
                'required': True
            }),
            'port': forms.NumberInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'min': 1,
                'max': 65535,
                'placeholder': '4370 (default)',
                'value': 4370
            }),
            'password': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': 'Leave empty if no password (default: 0)',
                'autocomplete': 'new-password'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'rows': 3,
                'placeholder': 'Optional description about device location, purpose, etc.'
            })
        }
        labels = {
            'name': _('Device Name'),
            'ip_address': _('IP Address'),
            'port': _('Port'),
            'password': _('Device Password'),
            'description': _('Description')
        }
        help_texts = {
            'name': _('A descriptive name for the device (e.g., "Main Office Entrance")'),
            'ip_address': _('The IP address of the ZKTeco device on your network'),
            'port': _('Communication port (default: 4370)'),
            'password': _('Device password if set (leave empty for no password)'),
            'description': _('Optional notes about device location or purpose')
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add IP address validator
        self.fields['ip_address'].validators.append(self.ip_validator)
        
        # Set default port if not provided
        if not self.instance.pk:
            self.fields['port'].initial = 4370
    
    def clean_ip_address(self):
        """Validate IP address format"""
        ip_address = self.cleaned_data.get('ip_address')
        
        if ip_address:
            # Split IP and validate each octet
            octets = ip_address.split('.')
            if len(octets) != 4:
                raise forms.ValidationError(_('Invalid IP address format.'))
            
            for octet in octets:
                try:
                    num = int(octet)
                    if not 0 <= num <= 255:
                        raise forms.ValidationError(_('Each IP address octet must be between 0 and 255.'))
                except ValueError:
                    raise forms.ValidationError(_('IP address must contain only numbers and dots.'))
        
        return ip_address
    
    def clean_port(self):
        """Validate port number"""
        port = self.cleaned_data.get('port')
        
        if port is not None:
            if not 1 <= port <= 65535:
                raise forms.ValidationError(_('Port number must be between 1 and 65535.'))
        
        return port
    
    def clean_password(self):
        """Clean password field"""
        password = self.cleaned_data.get('password')
        
        # Convert empty string to None for consistency
        if password == '':
            return None
        
        return password
    
    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        ip_address = cleaned_data.get('ip_address')
        
        # Check for duplicate IP address (excluding current instance)
        if ip_address:
            existing_device = ZkDevice.objects.filter(ip_address=ip_address)
            if self.instance.pk:
                existing_device = existing_device.exclude(pk=self.instance.pk)
            
            if existing_device.exists():
                raise forms.ValidationError({
                    'ip_address': _('A device with this IP address already exists.')
                })
        
        return cleaned_data

class LoginForm(forms.Form):
    """Custom login form"""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
            'placeholder': 'Enter your username',
            'autocomplete': 'username',
            'required': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
            'required': True
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary focus:ring-primary focus:ring-offset-0'
        })
    )

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            # Basic Information
            'employee_id', 'zkteco_id', 'name', 'first_name', 'last_name', 'is_active',
            
            # Personal Information
            'gender', 'date_of_birth', 'blood_group', 'marital_status', 
            'nid', 'passport_no',
            
            # Contact Information
            'contact_number', 'email', 
            'emergency_contact', 'emergency_contact_name', 'emergency_contact_relation',
            
            # Address Information
            'present_address', 'permanent_address',
            
            # Employment Details
            'company', 'department', 'designation', 'default_shift', 'user', 
            'joining_date', 'confirmation_date', 'job_type', 'employment_status',
            'resignation_date', 'termination_date',
            
            # Educational Information
            'highest_education', 'university', 'passing_year',
            
            # Salary & Compensation
            'base_salary', 'overtime_rate', 'per_hour_rate', 'expected_working_hours', 'overtime_grace_minutes',
            
            # Allowances
            'house_rent_allowance', 'medical_allowance', 'conveyance_allowance', 'food_allowance',
            'attendance_bonus', 'festival_bonus',
            
            # Deductions
            'provident_fund', 'tax_deduction', 'loan_deduction',
            
            # Banking Information
            'bank_name', 'bank_account_no', 'bank_branch', 'payment_method',
            
            # Additional Information
            'bio', 'skills', 'experience',
        ]
        widgets = {
            # Select fields
            'company': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'department': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'designation': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'default_shift': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'user': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'gender': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'marital_status': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'blood_group': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'job_type': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'employment_status': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'payment_method': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Text input fields
            'employee_id': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'zkteco_id': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'name': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'first_name': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'contact_number': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'emergency_contact': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'emergency_contact_relation': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'email': forms.EmailInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'nid': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'passport_no': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'highest_education': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'university': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'bank_name': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'bank_account_no': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'bank_branch': forms.TextInput(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Date fields
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'joining_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'confirmation_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'resignation_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'termination_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Number fields
            'passing_year': forms.NumberInput(attrs={'min': '1900', 'max': '2100', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'base_salary': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'overtime_rate': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'per_hour_rate': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'expected_working_hours': forms.NumberInput(attrs={'step': '0.1', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'overtime_grace_minutes': forms.NumberInput(attrs={'step': '1', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Allowances
            'house_rent_allowance': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'medical_allowance': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'conveyance_allowance': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'food_allowance': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'attendance_bonus': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'festival_bonus': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Deductions
            'provident_fund': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'tax_deduction': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'loan_deduction': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Textarea fields
            'present_address': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'permanent_address': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'bio': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'skills': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'experience': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            
            # Checkbox
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-gray-300 text-primary focus:ring-primary focus:ring-offset-0'}),
        }
class LeaveApplicationForm(forms.ModelForm):
    class Meta:
        model = LeaveApplication
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'leave_type': forms.Select(attrs={'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'start_date': forms.DateInput(attrs={'type': 'date','class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'end_date': forms.DateInput(attrs={'type': 'date','class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
            'reason': forms.Textarea(attrs={'rows': 4,'class': 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary'}),
        }

from django import forms
from .models import AttendanceProcessorConfiguration, Shift, Company


class AttendanceProcessorConfigurationForm(forms.ModelForm):
    """Form for creating and updating attendance processor configurations"""
    
    class Meta:
        model = AttendanceProcessorConfiguration
        fields = [
            'company', 'name', 'is_active',
            # Basic settings
            'grace_minutes', 'early_out_threshold_minutes', 
            'overtime_start_after_minutes', 'minimum_overtime_minutes',
            # Weekend configuration
            'weekend_friday', 'weekend_saturday', 'weekend_sunday',
            'weekend_monday', 'weekend_tuesday', 'weekend_wednesday', 'weekend_thursday',
            # Break time
            'default_break_minutes', 'use_shift_break_time', 'break_deduction_method',
            # Enhanced rules
            'enable_minimum_working_hours_rule', 'minimum_working_hours_for_present',
            'enable_working_hours_half_day_rule', 'half_day_minimum_hours', 'half_day_maximum_hours',
            'require_both_in_and_out',
            'enable_maximum_working_hours_rule', 'maximum_allowable_working_hours',
            # Dynamic shift detection
            'enable_dynamic_shift_detection', 'dynamic_shift_tolerance_minutes',
            'multiple_shift_priority', 'dynamic_shift_fallback_to_default',
            'dynamic_shift_fallback_shift',
            # Shift grace time
            'use_shift_grace_time',
            # Consecutive absence
            'enable_consecutive_absence_flagging', 'consecutive_absence_termination_risk_days',
            # Early out flagging
            'enable_max_early_out_flagging', 'max_early_out_threshold_minutes',
            'max_early_out_occurrences',
            # Overtime configuration
            'overtime_calculation_method', 'holiday_overtime_full_day',
            'weekend_overtime_full_day', 'late_affects_overtime', 'separate_ot_break_time',
            # Employee-specific settings
            'use_employee_specific_grace', 'use_employee_specific_overtime',
            'use_employee_expected_hours',
            # Advanced rules
            'late_to_absent_days', 'holiday_before_after_absent',
            'weekend_before_after_absent', 'require_holiday_presence',
            'include_holiday_analysis', 'holiday_buffer_days',
            # Display options
            'show_absent_employees', 'show_leave_employees',
            'show_holiday_status', 'include_roster_info',
        ]
        widgets = {
            'company': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring'
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'placeholder': 'Enter configuration name'
            }),
            'grace_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'early_out_threshold_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'overtime_start_after_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'minimum_overtime_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'default_break_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'break_deduction_method': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring'
            }),
            'minimum_working_hours_for_present': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0',
                'step': '0.1'
            }),
            'half_day_minimum_hours': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0',
                'step': '0.1'
            }),
            'half_day_maximum_hours': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0',
                'step': '0.1'
            }),
            'maximum_allowable_working_hours': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0',
                'step': '0.1'
            }),
            'dynamic_shift_tolerance_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'multiple_shift_priority': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring'
            }),
            'dynamic_shift_fallback_shift': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring'
            }),
            'consecutive_absence_termination_risk_days': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'max_early_out_threshold_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'max_early_out_occurrences': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'overtime_calculation_method': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring'
            }),
            'separate_ot_break_time': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'late_to_absent_days': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
            'holiday_buffer_days': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring',
                'min': '0'
            }),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        # Filter shifts by company if available
        if company:
            self.fields['dynamic_shift_fallback_shift'].queryset = Shift.objects.filter(company=company)
        
        # Add help text to complex fields
        self.fields['grace_minutes'].help_text = "Late arrival grace period in minutes"
        self.fields['early_out_threshold_minutes'].help_text = "Minutes before end time to consider as early departure"
        self.fields['break_deduction_method'].help_text = "Method to calculate break time deduction"
        
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate half day hours
        half_day_min = cleaned_data.get('half_day_minimum_hours')
        half_day_max = cleaned_data.get('half_day_maximum_hours')
        
        if half_day_min and half_day_max and half_day_min >= half_day_max:
            raise forms.ValidationError("Half day minimum hours must be less than maximum hours")
        
        return cleaned_data        