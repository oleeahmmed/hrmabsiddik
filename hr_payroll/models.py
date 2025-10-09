from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import os
import logging
from django.utils.dateparse import parse_datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

# Import Company model from custom_auth app
from core.models import Company

try:
    from zk import ZK
    from zk.exception import ZKNetworkError, ZKErrorResponse
    ZK_AVAILABLE = True
except ImportError:
    ZK_AVAILABLE = False
    logging.warning("ZK library not available. Please install it with 'pip install pyzk'")

logger = logging.getLogger(__name__)


# models.py এ যোগ করুন

class AttendanceProcessorConfiguration(models.Model):
    """
    Attendance Processor এর জন্য সকল কনফিগারেশন সংরক্ষণ ও পরিচালনার মডেল
    """
    # Company relationship
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Configuration Name"), max_length=100, default="Default Configuration")
    is_active = models.BooleanField(_("Active"), default=True)
    
    # Basic Attendance Settings
    grace_minutes = models.PositiveIntegerField(
        _("Grace Minutes"), 
        default=15,
        help_text=_("Late arrival grace period in minutes")
    )
    early_out_threshold_minutes = models.PositiveIntegerField(
        _("Early Out Threshold (minutes)"), 
        default=30,
        help_text=_("Minutes before end time to consider as early departure")
    )
    overtime_start_after_minutes = models.PositiveIntegerField(
        _("Overtime Start After (minutes)"), 
        default=15,
        help_text=_("Minutes after scheduled end time to start overtime calculation")
    )
    minimum_overtime_minutes = models.PositiveIntegerField(
        _("Minimum Overtime Minutes"), 
        default=60,
        help_text=_("Minimum overtime duration to be eligible for overtime pay")
    )
    
    # Weekend Configuration
    weekend_friday = models.BooleanField(_("Friday Weekend"), default=True)
    weekend_saturday = models.BooleanField(_("Saturday Weekend"), default=False)
    weekend_sunday = models.BooleanField(_("Sunday Weekend"), default=False)
    weekend_monday = models.BooleanField(_("Monday Weekend"), default=False)
    weekend_tuesday = models.BooleanField(_("Tuesday Weekend"), default=False)
    weekend_wednesday = models.BooleanField(_("Wednesday Weekend"), default=False)
    weekend_thursday = models.BooleanField(_("Thursday Weekend"), default=False)
    
    # Break Time Configuration
    default_break_minutes = models.PositiveIntegerField(
        _("Default Break Time (minutes)"), 
        default=60,
        help_text=_("Default break time if shift doesn't specify")
    )
    use_shift_break_time = models.BooleanField(
        _("Use Shift Break Time"), 
        default=True,
        help_text=_("Use shift-specific break time instead of default")
    )
    break_deduction_method = models.CharField(
        _("Break Deduction Method"),
        max_length=20,
        choices=[
            ('fixed', _('Fixed')),
            ('proportional', _('Proportional')),
        ],
        default='fixed',
        help_text=_("Method to calculate break time deduction")
    )
    
    # Enhanced Rule 1: Minimum Working Hours Rule
    enable_minimum_working_hours_rule = models.BooleanField(
        _("Enable Minimum Working Hours Rule"), 
        default=False,
        help_text=_("Convert present to absent if working hours below threshold")
    )
    minimum_working_hours_for_present = models.FloatField(
        _("Minimum Working Hours for Present"), 
        default=4.0,
        help_text=_("Minimum hours required to mark as present")
    )
    
    # Enhanced Rule 2: Working Hours Half Day Rule
    enable_working_hours_half_day_rule = models.BooleanField(
        _("Enable Working Hours Half Day Rule"), 
        default=False,
        help_text=_("Convert to half day based on working hours range")
    )
    half_day_minimum_hours = models.FloatField(
        _("Half Day Minimum Hours"), 
        default=4.0,
        help_text=_("Minimum hours for half day qualification")
    )
    half_day_maximum_hours = models.FloatField(
        _("Half Day Maximum Hours"), 
        default=6.0,
        help_text=_("Maximum hours for half day qualification")
    )
    
    # Enhanced Rule 3: Both In and Out Time Requirement
    require_both_in_and_out = models.BooleanField(
        _("Require Both In and Out Time"), 
        default=False,
        help_text=_("Mark as absent if either check-in or check-out is missing")
    )
    
    # Enhanced Rule 4: Maximum Working Hours Rule
    enable_maximum_working_hours_rule = models.BooleanField(
        _("Enable Maximum Working Hours Rule"), 
        default=False,
        help_text=_("Flag records with excessive working hours")
    )
    maximum_allowable_working_hours = models.FloatField(
        _("Maximum Allowable Working Hours"), 
        default=16.0,
        help_text=_("Maximum allowed working hours per day")
    )
    
    # Enhanced Rule 5: Dynamic Shift Detection
    enable_dynamic_shift_detection = models.BooleanField(
        _("Enable Dynamic Shift Detection"), 
        default=False,
        help_text=_("Automatically detect shift based on attendance pattern")
    )
    dynamic_shift_tolerance_minutes = models.PositiveIntegerField(
        _("Dynamic Shift Tolerance (minutes)"), 
        default=30,
        help_text=_("Tolerance in minutes for shift pattern matching")
    )
    multiple_shift_priority = models.CharField(
        _("Multiple Shift Priority"),
        max_length=20,
        choices=[
            ('least_break', _('Least Break Time')),
            ('shortest_duration', _('Shortest Duration')),
            ('alphabetical', _('Alphabetical')),
            ('highest_score', _('Highest Score')),
        ],
        default='least_break',
        help_text=_("Priority method when multiple shifts match")
    )
    dynamic_shift_fallback_to_default = models.BooleanField(
        _("Dynamic Shift Fallback to Default"), 
        default=True,
        help_text=_("Use employee's default shift if dynamic detection fails")
    )
    dynamic_shift_fallback_shift = models.ForeignKey(
        'Shift', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("Fallback Shift"),
        help_text=_("Fixed shift to use if dynamic detection fails and no default shift")
    )
    
    # Enhanced Rule 6: Shift Grace Time
    use_shift_grace_time = models.BooleanField(
        _("Use Shift-Specific Grace Time"), 
        default=False,
        help_text=_("Use grace time from shift instead of global grace time")
    )
    
    # Enhanced Rule 7: Consecutive Absence Flagging
    enable_consecutive_absence_flagging = models.BooleanField(
        _("Enable Consecutive Absence Flagging"), 
        default=False,
        help_text=_("Flag employees with consecutive absences as termination risk")
    )
    consecutive_absence_termination_risk_days = models.PositiveIntegerField(
        _("Consecutive Absence Risk Days"), 
        default=5,
        help_text=_("Number of consecutive absent days to flag as termination risk")
    )
    
    # Enhanced Rule 8: Early Out Flagging
    enable_max_early_out_flagging = models.BooleanField(
        _("Enable Max Early Out Flagging"), 
        default=False,
        help_text=_("Flag employees with excessive early departures")
    )
    max_early_out_threshold_minutes = models.PositiveIntegerField(
        _("Max Early Out Threshold (minutes)"), 
        default=120,
        help_text=_("Minutes of early departure to consider excessive")
    )
    max_early_out_occurrences = models.PositiveIntegerField(
        _("Max Early Out Occurrences"), 
        default=3,
        help_text=_("Number of early departures in a month to flag")
    )
    
    # Overtime Configuration
    overtime_calculation_method = models.CharField(
        _("Overtime Calculation Method"),
        max_length=20,
        choices=[
            ('shift_based', _('Shift Based')),
            ('employee_based', _('Employee Based')),
            ('fixed_hours', _('Fixed Hours')),
        ],
        default='employee_based',
        help_text=_("Method to calculate overtime")
    )
    holiday_overtime_full_day = models.BooleanField(
        _("Holiday Overtime Full Day"), 
        default=True,
        help_text=_("Count all holiday working hours as overtime")
    )
    weekend_overtime_full_day = models.BooleanField(
        _("Weekend Overtime Full Day"), 
        default=True,
        help_text=_("Count all weekend working hours as overtime")
    )
    late_affects_overtime = models.BooleanField(
        _("Late Arrival Affects Overtime"), 
        default=False,
        help_text=_("Reduce overtime if employee arrives late")
    )
    separate_ot_break_time = models.PositiveIntegerField(
        _("Separate OT Break Time (minutes)"), 
        default=0,
        help_text=_("Additional break time to deduct from overtime")
    )
    
    # Employee-Specific Settings
    use_employee_specific_grace = models.BooleanField(
        _("Use Employee Specific Grace"), 
        default=True,
        help_text=_("Use employee-specific grace time if available")
    )
    use_employee_specific_overtime = models.BooleanField(
        _("Use Employee Specific Overtime"), 
        default=True,
        help_text=_("Use employee-specific overtime settings if available")
    )
    use_employee_expected_hours = models.BooleanField(
        _("Use Employee Expected Hours"), 
        default=True,
        help_text=_("Use employee-specific expected working hours")
    )
    
    # Advanced Rules
    late_to_absent_days = models.PositiveIntegerField(
        _("Late to Absent Days"), 
        default=3,
        help_text=_("Convert late to absent after consecutive late days")
    )
    holiday_before_after_absent = models.BooleanField(
        _("Holiday Before/After Absent"), 
        default=True,
        help_text=_("Consider attendance around holidays for absence rules")
    )
    weekend_before_after_absent = models.BooleanField(
        _("Weekend Before/After Absent"), 
        default=True,
        help_text=_("Consider attendance around weekends for absence rules")
    )
    require_holiday_presence = models.BooleanField(
        _("Require Holiday Presence"), 
        default=False,
        help_text=_("Require attendance on designated working holidays")
    )
    include_holiday_analysis = models.BooleanField(
        _("Include Holiday Analysis"), 
        default=True,
        help_text=_("Include holiday patterns in attendance analysis")
    )
    holiday_buffer_days = models.PositiveIntegerField(
        _("Holiday Buffer Days"), 
        default=1,
        help_text=_("Days before/after holiday to consider for analysis")
    )
    
    # Display Options
    show_absent_employees = models.BooleanField(
        _("Show Absent Employees"), 
        default=True,
        help_text=_("Include absent employees in reports")
    )
    show_leave_employees = models.BooleanField(
        _("Show Leave Employees"), 
        default=True,
        help_text=_("Include employees on leave in reports")
    )
    show_holiday_status = models.BooleanField(
        _("Show Holiday Status"), 
        default=True,
        help_text=_("Show holiday information in reports")
    )
    include_roster_info = models.BooleanField(
        _("Include Roster Info"), 
        default=True,
        help_text=_("Include roster information in attendance records")
    )
    
    # Metadata
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_by = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_attendance_configs',
        verbose_name=_("Created By")
    )
    
    class Meta:
        verbose_name = _("Attendance Processor Configuration")
        verbose_name_plural = _("Attendance Processor Configurations")
        unique_together = ('company', 'name')
        ordering = ['-is_active', 'name']
    
    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.name} - {self.company.name} ({status})"
    
    @property
    def weekend_days(self):
        """Get weekend days as a list of integers (0=Monday, 6=Sunday)"""
        days = []
        if self.weekend_monday:
            days.append(0)
        if self.weekend_tuesday:
            days.append(1)
        if self.weekend_wednesday:
            days.append(2)
        if self.weekend_thursday:
            days.append(3)
        if self.weekend_friday:
            days.append(4)
        if self.weekend_saturday:
            days.append(5)
        if self.weekend_sunday:
            days.append(6)
        return days
    
    def get_config_dict(self):
        """Convert model instance to dictionary for processor"""
        return {
            # Basic settings
            'grace_minutes': self.grace_minutes,
            'early_out_threshold_minutes': self.early_out_threshold_minutes,
            'overtime_start_after_minutes': self.overtime_start_after_minutes,
            'minimum_overtime_minutes': self.minimum_overtime_minutes,
            'weekend_days': self.weekend_days,
            
            # Break time
            'default_break_minutes': self.default_break_minutes,
            'use_shift_break_time': self.use_shift_break_time,
            'break_deduction_method': self.break_deduction_method,
            
            # Enhanced rules
            'enable_minimum_working_hours_rule': self.enable_minimum_working_hours_rule,
            'minimum_working_hours_for_present': self.minimum_working_hours_for_present,
            'enable_working_hours_half_day_rule': self.enable_working_hours_half_day_rule,
            'half_day_minimum_hours': self.half_day_minimum_hours,
            'half_day_maximum_hours': self.half_day_maximum_hours,
            'require_both_in_and_out': self.require_both_in_and_out,
            'enable_maximum_working_hours_rule': self.enable_maximum_working_hours_rule,
            'maximum_allowable_working_hours': self.maximum_allowable_working_hours,
            
            # Dynamic shift detection
            'enable_dynamic_shift_detection': self.enable_dynamic_shift_detection,
            'dynamic_shift_tolerance_minutes': self.dynamic_shift_tolerance_minutes,
            'multiple_shift_priority': self.multiple_shift_priority,
            'dynamic_shift_fallback_to_default': self.dynamic_shift_fallback_to_default,
            'dynamic_shift_fallback_shift_id': self.dynamic_shift_fallback_shift_id,
            
            # Shift grace time
            'use_shift_grace_time': self.use_shift_grace_time,
            
            # Consecutive absence
            'enable_consecutive_absence_flagging': self.enable_consecutive_absence_flagging,
            'consecutive_absence_termination_risk_days': self.consecutive_absence_termination_risk_days,
            
            # Early out flagging
            'enable_max_early_out_flagging': self.enable_max_early_out_flagging,
            'max_early_out_threshold_minutes': self.max_early_out_threshold_minutes,
            'max_early_out_occurrences': self.max_early_out_occurrences,
            
            # Overtime configuration
            'overtime_calculation_method': self.overtime_calculation_method,
            'holiday_overtime_full_day': self.holiday_overtime_full_day,
            'weekend_overtime_full_day': self.weekend_overtime_full_day,
            'late_affects_overtime': self.late_affects_overtime,
            'separate_ot_break_time': self.separate_ot_break_time,
            
            # Employee-specific settings
            'use_employee_specific_grace': self.use_employee_specific_grace,
            'use_employee_specific_overtime': self.use_employee_specific_overtime,
            'use_employee_expected_hours': self.use_employee_expected_hours,
            
            # Advanced rules
            'late_to_absent_days': self.late_to_absent_days,
            'holiday_before_after_absent': self.holiday_before_after_absent,
            'weekend_before_after_absent': self.weekend_before_after_absent,
            'require_holiday_presence': self.require_holiday_presence,
            'include_holiday_analysis': self.include_holiday_analysis,
            'holiday_buffer_days': self.holiday_buffer_days,
            
            # Display options
            'show_absent_employees': self.show_absent_employees,
            'show_leave_employees': self.show_leave_employees,
            'show_holiday_status': self.show_holiday_status,
            'include_roster_info': self.include_roster_info,
        }
    
    def save(self, *args, **kwargs):
        # Ensure only one active configuration per company
        if self.is_active:
            AttendanceProcessorConfiguration.objects.filter(
                company=self.company, 
                is_active=True
            ).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_config(cls, company):
        """Get active configuration for a company"""
        try:
            return cls.objects.filter(company=company, is_active=True).first()
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def get_config_dict_for_company(cls, company):
        """Get configuration dictionary for a company"""
        config = cls.get_active_config(company)
        if config:
            return config.get_config_dict()
        else:
            # Return default configuration
            return cls.get_default_config()
    
    @classmethod
    def get_default_config(cls):
        """Get default configuration dictionary"""
        return {
            'grace_minutes': 15,
            'early_out_threshold_minutes': 30,
            'overtime_start_after_minutes': 15,
            'minimum_overtime_minutes': 60,
            'weekend_days': [4],  # Friday
            'default_break_minutes': 60,
            'use_shift_break_time': True,
            'break_deduction_method': 'fixed',
            'enable_minimum_working_hours_rule': False,
            'minimum_working_hours_for_present': 4.0,
            'enable_working_hours_half_day_rule': False,
            'half_day_minimum_hours': 4.0,
            'half_day_maximum_hours': 6.0,
            'require_both_in_and_out': False,
            'enable_maximum_working_hours_rule': False,
            'maximum_allowable_working_hours': 16.0,
            'enable_dynamic_shift_detection': False,
            'dynamic_shift_tolerance_minutes': 30,
            'multiple_shift_priority': 'least_break',
            'dynamic_shift_fallback_to_default': True,
            'dynamic_shift_fallback_shift_id': None,
            'use_shift_grace_time': False,
            'enable_consecutive_absence_flagging': False,
            'consecutive_absence_termination_risk_days': 5,
            'enable_max_early_out_flagging': False,
            'max_early_out_threshold_minutes': 120,
            'max_early_out_occurrences': 3,
            'overtime_calculation_method': 'employee_based',
            'holiday_overtime_full_day': True,
            'weekend_overtime_full_day': True,
            'late_affects_overtime': False,
            'separate_ot_break_time': 0,
            'use_employee_specific_grace': True,
            'use_employee_specific_overtime': True,
            'use_employee_expected_hours': True,
            'late_to_absent_days': 3,
            'holiday_before_after_absent': True,
            'weekend_before_after_absent': True,
            'require_holiday_presence': False,
            'include_holiday_analysis': True,
            'holiday_buffer_days': 1,
            'show_absent_employees': True,
            'show_leave_employees': True,
            'show_holiday_status': True,
            'include_roster_info': True,
        }

# ==================== EMPLOYEE INFORMATION ====================

class Department(models.Model):
    """
    প্রতিষ্ঠানের একটি বিভাগকে উপস্থাপন করে।
    এখন Company মডেলের সাথে ForeignKey সম্পর্ক রয়েছে।
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    code = models.CharField(_("Code"), max_length=20)
    description = models.TextField(_("Description"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.company.name}"

    class Meta:
        verbose_name = _("Department")
        verbose_name_plural = _("Departments")
        unique_together = ('company', 'code')
        ordering = ['name']

class Designation(models.Model):
    """
    একটি বিভাগের মধ্যে একটি কাজের পদকে উপস্থাপন করে।
    এখন Company এবং Department এর সাথে ForeignKey সম্পর্ক রয়েছে।
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    department = models.ForeignKey(Department, on_delete=models.CASCADE, verbose_name=_("Department"), blank=True, null=True)
    name = models.CharField(_("Name"), max_length=100)
    code = models.CharField(_("Code"), max_length=20)
    description = models.TextField(_("Description"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.company.name}"

    class Meta:
        verbose_name = _("Designation")
        verbose_name_plural = _("Designations")
        unique_together = ('company', 'code')
        ordering = ['name']



class Employee(models.Model):
    
    # --- Choices ---
    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
        ('O', _('Other')),
    ]

    MARITAL_CHOICES = [
        ('S', _('Single')),
        ('M', _('Married')),
        ('D', _('Divorced')),
        ('W', _('Widowed')),
    ]
    
    JOB_TYPE_CHOICES = [
        ('FT', _('Full-Time')),
        ('PT', _('Part-Time')),
        ('CT', _('Contract')),
        ('IN', _('Internship')),
        ('TP', _('Temporary')),
    ]

    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
    ]

    EMPLOYMENT_STATUS_CHOICES = [
        ('active', _('Active')),
        ('probation', _('Probation')),
        ('suspended', _('Suspended')),
        ('terminated', _('Terminated')),
        ('resigned', _('Resigned')),
    ]

    # --- 1. Core & Organizational Details ---
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        verbose_name=_("Company")
    )
    department = models.ForeignKey(
        Department, 
        on_delete=models.SET_NULL, 
        verbose_name=_("Department"), 
        blank=True, 
        null=True
    )
    designation = models.ForeignKey(
        Designation, 
        on_delete=models.SET_NULL, 
        verbose_name=_("Designation"), 
        blank=True, 
        null=True
    )
    
    default_shift = models.ForeignKey(
        'Shift', 
        on_delete=models.SET_NULL, 
        verbose_name=_("Default Shift"), 
        blank=True, 
        null=True
    )

    # --- 2. Identifiers ---
    employee_id = models.CharField(
        _("Employee ID"), 
        max_length=50, 
        unique=True
    )
    zkteco_id = models.CharField(
        _("ZKTeco ID"), 
        max_length=50, 
        unique=True, 
        blank=True, 
        null=True,
        help_text=_("Employee ID used in the ZKTeco attendance machine (optional)")
    )

    # --- 3. Name and User Linking ---
    name = models.CharField(
        _("Name"), 
        max_length=100
    )
    first_name = models.CharField(
        _("First Name"), 
        max_length=50, 
        blank=True, 
        null=True
    )
    last_name = models.CharField(
        _("Last Name"), 
        max_length=50, 
        blank=True, 
        null=True
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='employee_user',
        verbose_name=_("System User Account"),
        help_text=_("Linked Django user account for login/mobile attendance (optional)")
    )
    
    # --- 4. Personal Information ---
    gender = models.CharField(
        _("Gender"),
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
        null=True
    )
    date_of_birth = models.DateField(
        _("Date of Birth"), 
        blank=True, 
        null=True
    )
    blood_group = models.CharField(
        _("Blood Group"),
        max_length=3,
        choices=BLOOD_GROUP_CHOICES,
        blank=True,
        null=True
    )
    marital_status = models.CharField(
        _("Marital Status"), 
        max_length=20, 
        choices=MARITAL_CHOICES,
        blank=True, 
        null=True
    )
    nid = models.CharField(
        _("National ID"), 
        max_length=30, 
        blank=True, 
        null=True, 
        default=""
    )
    passport_no = models.CharField(
        _("Passport Number"),
        max_length=50,
        blank=True,
        null=True
    )
    
    # --- 5. Contact Information ---
    contact_number = models.CharField(
        _("Contact Number"), 
        max_length=20, 
        blank=True, 
        null=True, 
        default=""
    )
    email = models.EmailField(
        _("Email Address"),
        blank=True,
        null=True
    )
    emergency_contact = models.CharField(
        _("Emergency Contact"),
        max_length=20,
        blank=True,
        null=True
    )
    emergency_contact_name = models.CharField(
        _("Emergency Contact Name"),
        max_length=100,
        blank=True,
        null=True
    )
    emergency_contact_relation = models.CharField(
        _("Emergency Contact Relation"),
        max_length=50,
        blank=True,
        null=True
    )
    
    # --- 6. Simple Address Information ---
    present_address = models.TextField(
        _("Present Address"),
        blank=True,
        null=True
    )
    permanent_address = models.TextField(
        _("Permanent Address"),
        blank=True,
        null=True
    )
    
    # --- 7. Employment Details ---
    joining_date = models.DateField(
        _("Joining Date"), 
        blank=True, 
        null=True
    )
    confirmation_date = models.DateField(
        _("Confirmation Date"),
        blank=True,
        null=True
    )
    job_type = models.CharField(
        _("Job Type"),
        max_length=2,
        choices=JOB_TYPE_CHOICES,
        default='FT'
    )
    employment_status = models.CharField(
        _("Employment Status"),
        max_length=20,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default='active'
    )
    resignation_date = models.DateField(
        _("Resignation Date"),
        blank=True,
        null=True
    )
    termination_date = models.DateField(
        _("Termination Date"),
        blank=True,
        null=True
    )
    
    # --- 8. Educational Information ---
    highest_education = models.CharField(
        _("Highest Education"),
        max_length=100,
        blank=True,
        null=True
    )
    university = models.CharField(
        _("University/Institution"),
        max_length=200,
        blank=True,
        null=True
    )
    passing_year = models.IntegerField(
        _("Passing Year"),
        blank=True,
        null=True
    )
    
    # --- 9. Payroll & Financial Details ---
    base_salary = models.DecimalField(
        _("Basic Salary (Monthly)"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        blank=True, 
        null=True,
        help_text=_("The employee's basic monthly gross salary.")
    )

    # Calculation fields
    per_hour_rate = models.DecimalField(
        _("Per Hour Rate"), 
        max_digits=8, 
        decimal_places=2, 
        default=Decimal('30.00'), 
        blank=True, 
        null=True,
        help_text=_("Explicitly set rate for hourly attendance/calculations.")
    )  
    expected_working_hours = models.FloatField(
        _("Expected Working Hours (Daily)"), 
        default=8.0, 
        blank=True, 
        null=True,
        help_text=_("Daily contractual working hours (e.g., 8.0)")
    )
    overtime_rate = models.DecimalField(
        _("Overtime Rate (per hour)"), 
        max_digits=8, 
        decimal_places=2, 
        default=Decimal('0.00'),
        blank=True, 
        null=True,
        help_text=_("Explicitly set fixed rate for overtime.")
    )
    overtime_grace_minutes = models.IntegerField(
        _("Overtime Grace Minutes"), 
        default=15, 
        blank=True, 
        null=True
    )
    
    # Allowances (All Optional)
    house_rent_allowance = models.DecimalField(
        _("House Rent Allowance"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    medical_allowance = models.DecimalField(
        _("Medical Allowance"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    conveyance_allowance = models.DecimalField(
        _("Conveyance Allowance"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    food_allowance = models.DecimalField(
        _("Food Allowance"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    attendance_bonus = models.DecimalField(
        _("Attendance Bonus"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    festival_bonus = models.DecimalField(
        _("Festival Bonus"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )

    # Deductions (All Optional)
    provident_fund = models.DecimalField(
        _("Provident Fund"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    tax_deduction = models.DecimalField(
        _("Tax Deduction"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )
    loan_deduction = models.DecimalField(
        _("Loan Deduction"), 
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        blank=True, 
        null=True
    )

    # Banking and Payment
    bank_name = models.CharField(
        _("Bank Name"),
        max_length=100,
        blank=True,
        null=True
    )
    bank_account_no = models.CharField(
        _("Bank Account No"), 
        max_length=50, 
        blank=True, 
        null=True, 
        default=""
    )
    bank_branch = models.CharField(
        _("Bank Branch"),
        max_length=100,
        blank=True,
        null=True
    )
    payment_method = models.CharField(
        _("Payment Method"), 
        max_length=20, 
        default="Cash", 
        blank=True, 
        null=True
    )
    
    # --- 10. Additional Information ---
    bio = models.TextField(
        _("Bio/Description"),
        blank=True,
        null=True
    )
    skills = models.TextField(
        _("Skills"),
        blank=True,
        null=True,
        help_text=_("Comma separated list of skills")
    )
    experience = models.TextField(
        _("Previous Experience"),
        blank=True,
        null=True
    )
    
    # --- 11. System Fields ---
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_employees',
        verbose_name=_("Created By")
    )

    # --- Custom Methods ---
    def __str__(self):
        return f"{self.employee_id} - {self.name}"

    def get_full_name(self):
        """Returns the employee's full name for RosterAssignment."""
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or self.name
    
    def get_age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            today = timezone.now().date()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    def get_service_period(self):
        """Calculate service period in years"""
        if self.joining_date:
            today = timezone.now().date()
            return today.year - self.joining_date.year - (
                (today.month, today.day) < (self.joining_date.month, self.joining_date.day)
            )
        return 0
    
    def get_hourly_rate(self):
        """Calculate hourly rate from basic salary (assuming 22 working days and expected_working_hours)"""
        basic_salary = self.base_salary if self.base_salary is not None else Decimal('0.00')
        expected_hours = self.expected_working_hours if self.expected_working_hours is not None else 8.0
        
        if basic_salary > Decimal('0.00') and expected_hours > 0:
            try:
                return float(basic_salary) / (22 * expected_hours)
            except (ZeroDivisionError, TypeError):
                return 0.0
        return 0.0
    
    def get_per_hour_rate(self):
        """Get per hour rate from the dedicated field for hourly attendance calculation"""
        per_hour_rate = self.per_hour_rate if self.per_hour_rate is not None else Decimal('0.00')
        return float(per_hour_rate)
    
    def get_overtime_rate(self):
        """Get overtime rate, fallback to 1.5x hourly rate if not explicitly set"""
        if self.overtime_rate and self.overtime_rate > Decimal('0.00'):
            return float(self.overtime_rate)
        else:
            return self.get_hourly_rate() * 1.5

    class Meta:
        verbose_name = _("Employee")
        verbose_name_plural = _("Employees")
        unique_together = ('company', 'employee_id') 
        ordering = ['employee_id']
        
class EmployeeSeparation(models.Model):
    """
    Represents an employee's separation from the organization.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name=_("Employee"))
    separation_date = models.DateField(_("Separation Date"))
    reason = models.TextField(_("Reason"), blank=True, null=True)
    is_voluntary = models.BooleanField(_("Voluntary"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.separation_date}"

    class Meta:
        verbose_name = _("Employee Separation")
        verbose_name_plural = _("Employee Separations")
        ordering = ['-separation_date']

class Holiday(models.Model):
    """
    Represents a company holiday.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    date = models.DateField(_("Date"))
    description = models.TextField(_("Description"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.date}"

    class Meta:
        verbose_name = _("Holiday")
        verbose_name_plural = _("Holidays")
        unique_together = ('company', 'date')
        ordering = ['-date']

class LeaveType(models.Model):
    """
    Represents different types of leaves available to employees.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    code = models.CharField(_("Code"), max_length=20)
    max_days = models.PositiveIntegerField(_("Maximum Days"), default=0)
    paid = models.BooleanField(_("Paid"), default=True)
    carry_forward = models.BooleanField(_("Carry Forward"), default=False)
    max_carry_forward_days = models.PositiveIntegerField(_("Max Carry Forward Days"), default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.company.name}"

    class Meta:
        verbose_name = _("Leave Type")
        verbose_name_plural = _("Leave Types")
        unique_together = ('company', 'code')
        ordering = ['name']

class LeaveBalance(models.Model):
    """
    Tracks the leave balance for each employee by leave type.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name=_("Employee"))
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, verbose_name=_("Leave Type"))
    entitled_days = models.FloatField(_("Entitled Days"), default=0)
    used_days = models.FloatField(_("Used Days"), default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name}"

    @property
    def remaining_days(self):
        return self.entitled_days - self.used_days

    class Meta:
        verbose_name = _("Leave Balance")
        verbose_name_plural = _("Leave Balances")
        unique_together = ('employee', 'leave_type')
        ordering = ['employee__employee_id']

class LeaveApplication(models.Model):
    """
    Represents a leave application submitted by an employee.
    """
    STATUS_CHOICES = (
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_applications', verbose_name=_("Employee"))
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, verbose_name=_("Leave Type"))
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    reason = models.TextField(_("Reason"), blank=True, null=True)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS_CHOICES, default='P')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, verbose_name=_("Approved By"), null=True, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.start_date} to {self.end_date}"

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError(_("End date cannot be earlier than start date"))

    class Meta:
        verbose_name = _("Leave Application")
        verbose_name_plural = _("Leave Applications")
        ordering = ['-start_date']

class ZkDevice(models.Model):
    """
    Represents a ZKTeco biometric device for attendance tracking.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    ip_address = models.CharField(_("IP Address"), max_length=15)
    port = models.PositiveIntegerField(_("Port"), default=4370)
    password = models.CharField(_("Password"), max_length=50, blank=True, null=True)
    is_active = models.BooleanField(_("Active"), default=True)
    description = models.TextField(_("Description"), blank=True, null=True)
    last_synced = models.DateTimeField(_("Last Synced"), null=True, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.ip_address}"

    class Meta:
        verbose_name = _("ZKTeco Device")
        verbose_name_plural = _("ZKTeco Devices")
        unique_together = ('company', 'ip_address')
        ordering = ['name']

class Location(models.Model):
    """Represents a geolocation for attendance tracking."""
    name = models.CharField(_("Name"), max_length=100)
    address = models.TextField(_("Address"))
    latitude = models.DecimalField(_("Latitude"), max_digits=10, decimal_places=8)
    longitude = models.DecimalField(_("Longitude"), max_digits=11, decimal_places=8)
    radius = models.DecimalField(_("Radius (km)"), max_digits=5, decimal_places=2)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")
        ordering = ['name']        
class UserLocation(models.Model):
    """Associates users with locations for attendance tracking."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, 
                            related_name='user_locations', verbose_name=_("User"))
    location = models.ForeignKey(Location, on_delete=models.CASCADE, 
                                related_name='user_locations', verbose_name=_("Location"))
    is_primary = models.BooleanField(_("Is Primary"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.location.name}"

    class Meta:
        verbose_name = _("User Location")
        verbose_name_plural = _("User Locations")
        unique_together = ('user', 'location')
        ordering = ['user__username', 'location__name']

class AttendanceLog(models.Model):
    """
    Stores raw attendance data from ZKTeco devices and mobile/location-based attendance.
    """
    SOURCE_TYPES = (
        ('ZK', 'ZKTeco Device'),
        ('MN', 'Manual'),
        ('MB', 'Mobile'),  # New: Mobile attendance
    )
    
    ATTENDANCE_TYPE_CHOICES = (
        ('IN', 'Check-in'),
        ('OUT', 'Check-out'),
    )

    # Required fields
    device = models.ForeignKey(ZkDevice, on_delete=models.CASCADE, verbose_name=_("Device"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name=_("Employee"))
    timestamp = models.DateTimeField(_("Timestamp"))
    status_code = models.IntegerField(_("Status Code"), default=0)
    punch_type = models.CharField(_("Punch Type"), max_length=50, default='UNKNOWN')
    source_type = models.CharField(_("Source Type"), max_length=10, choices=SOURCE_TYPES, default='ZK')
    
    # Optional fields for mobile/location-based attendance
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='attendance_logs',
        verbose_name=_("User"),
        help_text=_("User who marked attendance (for mobile attendance)")
    )
    location = models.ForeignKey(
        Location, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='attendance_logs',
        verbose_name=_("Location"),
        help_text=_("Location where attendance was marked")
    )
    attendance_type = models.CharField(
        _("Attendance Type"), 
        max_length=3, 
        choices=ATTENDANCE_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text=_("Check-in or Check-out type")
    )
    latitude = models.DecimalField(
        _("Latitude"), 
        max_digits=10, 
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_("GPS latitude coordinate")
    )
    longitude = models.DecimalField(
        _("Longitude"), 
        max_digits=11, 
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_("GPS longitude coordinate")
    )
    is_within_radius = models.BooleanField(
        _("Is Within Radius"), 
        default=False,
        help_text=_("Whether attendance was marked within location radius")
    )
    distance = models.DecimalField(
        _("Distance (km)"), 
        max_digits=8, 
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance from location center in kilometers")
    )

    location_name = models.TextField(
        _("Location Name"), 
        blank=True, 
        null=True,
        help_text=_("Location device information")
    )    
    device_info = models.TextField(
        _("Device Info"), 
        blank=True, 
        null=True,
        help_text=_("Mobile device information")
    )
    ip_address = models.GenericIPAddressField(
        _("IP Address"), 
        blank=True, 
        null=True,
        help_text=_("IP address from which attendance was marked")
    )
    
    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        if self.source_type == 'MB' and self.location:
            return f"{self.employee.employee_id} - {self.location.name} - {self.timestamp}"
        return f"{self.employee.employee_id} - {self.timestamp}"

    class Meta:
        verbose_name = _("Attendance Log")
        verbose_name_plural = _("Attendance Logs")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', 'timestamp']),
            models.Index(fields=['device', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['location', 'timestamp']),
            models.Index(fields=['source_type', 'timestamp']),
        ]



class Attendance(models.Model):
    """
    প্রতিটি কর্মচারীর জন্য দৈনিক উপস্থিতি রেকর্ড সংরক্ষণ করে।
    এখন Employee এবং Shift এর সাথে ForeignKey সম্পর্ক রয়েছে।
    """
    STATUS_CHOICES = (
        ('A', 'Absent'),
        ('P', 'Present'),
        ('W', 'Weekly Off'),
        ('H', 'Holiday'),
        ('L', 'Leave'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name=_("Employee"))
    shift = models.ForeignKey('Shift', on_delete=models.SET_NULL, verbose_name=_("Shift"), blank=True, null=True)
    date = models.DateField(_("Date"))
    check_in_time = models.DateTimeField(_("Check In Time"), null=True, blank=True)
    check_out_time = models.DateTimeField(_("Check Out Time"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS_CHOICES, default='A')
    overtime_hours = models.DecimalField(_("Overtime Hours"), max_digits=5, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} on {self.date}"

    @property
    def work_hours(self):
        """কাজের মোট সময় (ঘণ্টা) গণনা করে।"""
        if self.check_in_time and self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            return round(delta.total_seconds() / 3600, 2)
        return 0

    class Meta:
        verbose_name = _("Attendance")
        verbose_name_plural = _("Attendance")
        unique_together = ('employee', 'date')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
        ]

class Shift(models.Model):
    """Represents a work shift with start and end times."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    start_time = models.TimeField(_("Start Time"))
    end_time = models.TimeField(_("End Time"))
    break_time = models.PositiveIntegerField(_("Break Time (minutes)"), default=60)
    grace_time = models.PositiveIntegerField(_("Grace Time (minutes)"), default=15)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"
    
    @property
    def duration(self):
        start_datetime = timezone.datetime.combine(timezone.now().date(), self.start_time)
        end_datetime = timezone.datetime.combine(timezone.now().date(), self.end_time)
        
        if end_datetime < start_datetime:
            end_datetime += timezone.timedelta(days=1)
        
        duration = end_datetime - start_datetime
        duration_in_minutes = duration.total_seconds() / 60 - self.break_time
        
        hours = int(duration_in_minutes // 60)
        minutes = int(duration_in_minutes % 60)
        
        return f"{hours}h {minutes}m"
    
    @property
    def duration_minutes(self):
        start = timezone.datetime.combine(timezone.now().date(), self.start_time)
        end = timezone.datetime.combine(timezone.now().date(), self.end_time)
        if end < start:
            end += timezone.timedelta(days=1)
        return int((end - start).total_seconds() / 60 - self.break_time)

    @property
    def duration_hours(self):
        return round(self.duration_minutes / 60, 2)

    class Meta:
        verbose_name = _("Shift")
        verbose_name_plural = _("Shifts")
        ordering = ['start_time']

class Roster(models.Model):
    """Represents a roster schedule for employees."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    description = models.TextField(_("Description"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"
    
    def extend_roster(self, new_end_date):
        if new_end_date <= self.end_date:
            raise ValueError("New end date must be after the current end date")
        
        assignments = self.roster_assignments.all()
        days_to_extend = (new_end_date - self.end_date).days
        
        for assignment in assignments:
            last_day = assignment.roster_days.order_by('-date').first()
            if last_day:
                shift = last_day.shift
                
                for i in range(1, days_to_extend + 1):
                    new_date = self.end_date + timezone.timedelta(days=i)
                    RosterDay.objects.create(
                        roster_assignment=assignment,
                        date=new_date,
                        shift=shift
                    )
        
        self.end_date = new_end_date
        self.save()

    class Meta:
        verbose_name = _("Roster")
        verbose_name_plural = _("Rosters")
        ordering = ['-start_date']

class RosterAssignment(models.Model):
    """Assigns an employee to a roster."""
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, 
                              related_name='roster_assignments', verbose_name=_("Roster"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, 
                                related_name='roster_assignments', verbose_name=_("Employee"))
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, 
                             related_name='roster_assignment', verbose_name=_("Shift"))                                
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.roster.name}"

    class Meta:
        verbose_name = _("Roster Assignment")
        verbose_name_plural = _("Roster Assignments")
        unique_together = ('roster', 'employee')
        ordering = ['roster__name', 'employee__first_name']

class RosterDay(models.Model):
    """Represents a specific day in a roster assignment."""
    roster_assignment = models.ForeignKey(RosterAssignment, on_delete=models.CASCADE, 
                                         related_name='roster_days', 
                                         verbose_name=_("Roster Assignment"))
    date = models.DateField(_("Date"))
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, 
                             related_name='roster_days', verbose_name=_("Shift"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.roster_assignment.employee.get_full_name()} - {self.date} - {self.shift.name}"

    class Meta:
        verbose_name = _("Roster Day")
        verbose_name_plural = _("Roster Days")
        unique_together = ('roster_assignment', 'date')
        ordering = ['date']

# ==================== NOTICE & ANNOUNCEMENTS ====================

class Notice(models.Model):
    """
    কোম্পানির নোটিস এবং ঘোষণা পরিচালনা করে।
    """
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('urgent', _('Urgent')),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"))
    priority = models.CharField(_("Priority"), max_length=20, choices=PRIORITY_CHOICES, default='medium')
    published_date = models.DateField(_("Published Date"))
    expiry_date = models.DateField(_("Expiry Date"), null=True, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Created By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.company.name}"

    class Meta:
        verbose_name = _("Notice")
        verbose_name_plural = _("Notices")
        ordering = ['-published_date']


# ==================== RECRUITMENT ====================

class Recruitment(models.Model):
    """
    চাকরির পোস্ট এবং নিয়োগ প্রক্রিয়া পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('open', _('Open')),
        ('closed', _('Closed')),
        ('on_hold', _('On Hold')),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Department"))
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Designation"))
    job_title = models.CharField(_("Job Title"), max_length=200)
    job_description = models.TextField(_("Job Description"))
    requirements = models.TextField(_("Requirements"), blank=True, null=True)
    vacancies = models.PositiveIntegerField(_("Number of Vacancies"), default=1)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='draft')
    posted_date = models.DateField(_("Posted Date"))
    closing_date = models.DateField(_("Closing Date"))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Created By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.job_title} - {self.company.name}"

    class Meta:
        verbose_name = _("Recruitment")
        verbose_name_plural = _("Recruitments")
        ordering = ['-posted_date']


class JobApplication(models.Model):
    """
    চাকরির আবেদন এবং প্রার্থী তথ্য সংরক্ষণ করে।
    """
    STATUS_CHOICES = [
        ('applied', _('Applied')),
        ('shortlisted', _('Shortlisted')),
        ('interview', _('Interview Scheduled')),
        ('selected', _('Selected')),
        ('rejected', _('Rejected')),
    ]
    
    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name='applications', verbose_name=_("Recruitment"))
    applicant_name = models.CharField(_("Applicant Name"), max_length=100)
    email = models.EmailField(_("Email"))
    phone = models.CharField(_("Phone"), max_length=20)
    resume = models.TextField(_("Resume/CV"), blank=True, null=True)
    cover_letter = models.TextField(_("Cover Letter"), blank=True, null=True)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='applied')
    applied_date = models.DateField(_("Applied Date"), auto_now_add=True)
    notes = models.TextField(_("Notes"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.applicant_name} - {self.recruitment.job_title}"

    class Meta:
        verbose_name = _("Job Application")
        verbose_name_plural = _("Job Applications")
        ordering = ['-applied_date']


# ==================== TRAINING ====================

class Training(models.Model):
    """
    প্রশিক্ষণ প্রোগ্রাম পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('scheduled', _('Scheduled')),
        ('ongoing', _('Ongoing')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    title = models.CharField(_("Training Title"), max_length=200)
    description = models.TextField(_("Description"))
    trainer = models.CharField(_("Trainer Name"), max_length=100)
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    duration_hours = models.PositiveIntegerField(_("Duration (Hours)"), default=0)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Created By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.company.name}"

    class Meta:
        verbose_name = _("Training")
        verbose_name_plural = _("Trainings")
        ordering = ['-start_date']


class TrainingEnrollment(models.Model):
    """
    কর্মচারীদের প্রশিক্ষণে নথিভুক্তি পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('enrolled', _('Enrolled')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('withdrawn', _('Withdrawn')),
    ]
    
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name='enrollments', verbose_name=_("Training"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='training_enrollments', verbose_name=_("Employee"))
    enrollment_date = models.DateField(_("Enrollment Date"), auto_now_add=True)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='enrolled')
    completion_date = models.DateField(_("Completion Date"), null=True, blank=True)
    score = models.DecimalField(_("Score"), max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(_("Feedback"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.training.title}"

    class Meta:
        verbose_name = _("Training Enrollment")
        verbose_name_plural = _("Training Enrollments")
        unique_together = ('training', 'employee')
        ordering = ['-enrollment_date']


# ==================== PERFORMANCE ====================

class Performance(models.Model):
    """
    কর্মচারীর কর্মক্ষমতা মূল্যায়ন পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('submitted', _('Submitted')),
        ('reviewed', _('Reviewed')),
        ('approved', _('Approved')),
    ]
    
    RATING_CHOICES = [
        (1, _('Poor')),
        (2, _('Below Average')),
        (3, _('Average')),
        (4, _('Good')),
        (5, _('Excellent')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performances', verbose_name=_("Employee"))
    review_period_start = models.DateField(_("Review Period Start"))
    review_period_end = models.DateField(_("Review Period End"))
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Reviewer"))
    overall_rating = models.IntegerField(_("Overall Rating"), choices=RATING_CHOICES, null=True, blank=True)
    strengths = models.TextField(_("Strengths"), blank=True, null=True)
    weaknesses = models.TextField(_("Areas for Improvement"), blank=True, null=True)
    comments = models.TextField(_("Comments"), blank=True, null=True)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='draft')
    review_date = models.DateField(_("Review Date"), null=True, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.review_period_start} to {self.review_period_end}"

    class Meta:
        verbose_name = _("Performance Review")
        verbose_name_plural = _("Performance Reviews")
        ordering = ['-review_period_end']


class PerformanceGoal(models.Model):
    """
    কর্মচারীর কর্মক্ষমতা লক্ষ্য এবং উদ্দেশ্য পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name='goals', verbose_name=_("Performance Review"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_goals', verbose_name=_("Employee"))
    goal_title = models.CharField(_("Goal Title"), max_length=200)
    description = models.TextField(_("Description"))
    target_date = models.DateField(_("Target Date"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    achievement = models.TextField(_("Achievement"), blank=True, null=True)
    completion_date = models.DateField(_("Completion Date"), null=True, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.goal_title}"

    class Meta:
        verbose_name = _("Performance Goal")
        verbose_name_plural = _("Performance Goals")
        ordering = ['-target_date']


# ==================== DOCUMENTS ====================


# models.py - Update EmployeeDocument model

class EmployeeDocument(models.Model):
    """
    কর্মচারী সম্পর্কিত ডকুমেন্ট সংরক্ষণ করে।
    """
    DOCUMENT_TYPE_CHOICES = [
        ('resume', _('Resume/CV')),
        ('certificate', _('Certificate')),
        ('contract', _('Contract')),
        ('nid', _('National ID')),
        ('passport', _('Passport')),
        ('other', _('Other')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents', verbose_name=_("Employee"))
    document_type = models.CharField(_("Document Type"), max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"), blank=True, null=True)
    file = models.FileField(
        _("Document File"), 
        upload_to='employee_documents/%Y/%m/%d/',
        max_length=500,
        blank=True,
        null=True,
        help_text=_("Upload document file (PDF, DOC, DOCX, JPG, PNG)")
    )
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Uploaded By"))
    uploaded_at = models.DateTimeField(_("Uploaded At"), auto_now_add=True)
    is_verified = models.BooleanField(_("Verified"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.title}"

    @property
    def filename(self):
        """Get the filename from the file path"""
        if self.file:
            return os.path.basename(self.file.name)
        return None

    @property
    def file_extension(self):
        """Get file extension"""
        if self.file and self.file.name:
            return os.path.splitext(self.file.name)[1].lower()
        return None

    @property
    def file_size(self):
        """Get file size in human readable format"""
        if self.file and self.file.size:
            size = self.file.size
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            else:
                return f"{size / (1024 * 1024):.1f} MB"
        return "0 B"

    class Meta:
        verbose_name = _("Employee Document")
        verbose_name_plural = _("Employee Documents")
        ordering = ['-uploaded_at']


# ==================== OVERTIME ====================

class Overtime(models.Model):
    """
    কর্মচারীর অতিরিক্ত সময়ের অনুরোধ এবং অনুমোদন পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('cancelled', _('Cancelled')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='overtime_requests', verbose_name=_("Employee"))
    date = models.DateField(_("Overtime Date"))
    start_time = models.TimeField(_("Start Time"))
    end_time = models.TimeField(_("End Time"))
    hours = models.DecimalField(_("Overtime Hours"), max_digits=5, decimal_places=2)
    reason = models.TextField(_("Reason"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Approved By"))
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.date} ({self.hours}h)"

    class Meta:
        verbose_name = _("Overtime Request")
        verbose_name_plural = _("Overtime Requests")
        ordering = ['-date']


# ==================== RESIGNATION ====================

class Resignation(models.Model):
    """
    কর্মচারীর পদত্যাগ প্রক্রিয়া পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('submitted', _('Submitted')),
        ('accepted', _('Accepted')),
        ('rejected', _('Rejected')),
        ('withdrawn', _('Withdrawn')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='resignations', verbose_name=_("Employee"))
    resignation_date = models.DateField(_("Resignation Date"))
    last_working_date = models.DateField(_("Last Working Date"))
    reason = models.TextField(_("Reason"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='submitted')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Approved By"))
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.resignation_date}"

    class Meta:
        verbose_name = _("Resignation")
        verbose_name_plural = _("Resignations")
        ordering = ['-resignation_date']


# ==================== CLEARANCE ====================

class Clearance(models.Model):
    """
    কর্মচারী ছাড়ার সময় ক্লিয়ারেন্স প্রক্রিয়া পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('on_hold', _('On Hold')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='clearances', verbose_name=_("Employee"))
    resignation = models.ForeignKey(Resignation, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Resignation"))
    clearance_date = models.DateField(_("Clearance Date"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    hr_clearance = models.BooleanField(_("HR Clearance"), default=False)
    finance_clearance = models.BooleanField(_("Finance Clearance"), default=False)
    it_clearance = models.BooleanField(_("IT Clearance"), default=False)
    admin_clearance = models.BooleanField(_("Admin Clearance"), default=False)
    final_settlement_amount = models.DecimalField(_("Final Settlement Amount"), max_digits=10, decimal_places=2, default=0.00)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Cleared By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - Clearance"

    class Meta:
        verbose_name = _("Clearance")
        verbose_name_plural = _("Clearances")
        ordering = ['-clearance_date']


# ==================== COMPLAINT ====================

class Complaint(models.Model):
    """
    কর্মচারীর অভিযোগ এবং সমাধান প্রক্রিয়া পরিচালনা করে।
    """
    STATUS_CHOICES = [
        ('submitted', _('Submitted')),
        ('under_review', _('Under Review')),
        ('resolved', _('Resolved')),
        ('closed', _('Closed')),
    ]
    
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='complaints', verbose_name=_("Employee"))
    title = models.CharField(_("Complaint Title"), max_length=200)
    description = models.TextField(_("Description"))
    priority = models.CharField(_("Priority"), max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='submitted')
    submitted_date = models.DateField(_("Submitted Date"), auto_now_add=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_complaints', verbose_name=_("Assigned To"))
    resolution = models.TextField(_("Resolution"), blank=True, null=True)
    resolved_date = models.DateField(_("Resolved Date"), null=True, blank=True)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.name} - {self.title}"

    class Meta:
        verbose_name = _("Complaint")
        verbose_name_plural = _("Complaints")
        ordering = ['-submitted_date']
# models.py এ এই মডেলগুলো যোগ করুন

class PayrollCycle(models.Model):
    """
    পেরোল সাইকেল - মাসিক/সাপ্তাহিক পেরোল পিরিয়ড
    """
    CYCLE_TYPE_CHOICES = (
        ('monthly', 'মাসিক'),
        ('weekly', 'সাপ্তাহিক'),
        ('biweekly', 'পাক্ষিক'),
    )
    
    STATUS_CHOICES = (
        ('draft', 'ড্রাফট'),
        ('generated', 'জেনারেট হয়েছে'),
        ('approved', 'অনুমোদিত'),
        ('paid', 'পরিশোধিত'),
        ('closed', 'বন্ধ'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Cycle Name"), max_length=100)
    cycle_type = models.CharField(_("Cycle Type"), max_length=20, choices=CYCLE_TYPE_CHOICES, default='monthly')
    
    # Date Range
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    payment_date = models.DateField(_("Payment Date"), null=True, blank=True)
    
    # Status
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Financial Summary
    total_gross_salary = models.DecimalField(_("Total Gross Salary"), max_digits=12, decimal_places=2, default=0.00)
    total_deductions = models.DecimalField(_("Total Deductions"), max_digits=12, decimal_places=2, default=0.00)
    total_net_salary = models.DecimalField(_("Total Net Salary"), max_digits=12, decimal_places=2, default=0.00)
    total_overtime_amount = models.DecimalField(_("Total Overtime Amount"), max_digits=12, decimal_places=2, default=0.00)
    
    # Metadata
    generated_at = models.DateTimeField(_("Generated At"), null=True, blank=True)
    generated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, 
                                     related_name='generated_payrolls', verbose_name=_("Generated By"))
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='approved_payrolls', verbose_name=_("Approved By"))
    
    notes = models.TextField(_("Notes"), blank=True, null=True)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Payroll Cycle")
        verbose_name_plural = _("Payroll Cycles")
        ordering = ['-start_date']
        unique_together = ('company', 'start_date', 'end_date')
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date}) - {self.get_status_display()}"
    
    @property
    def total_employees(self):
        """Total employees in this cycle"""
        return self.payroll_records.count()
    
    @property
    def paid_employees(self):
        """Total employees paid"""
        return self.payroll_records.filter(payment_status='paid').count()
    
    def calculate_totals(self):
        """Calculate and update total amounts"""
        records = self.payroll_records.all()
        
        self.total_gross_salary = sum([r.gross_salary for r in records])
        self.total_deductions = sum([r.total_deductions for r in records])
        self.total_net_salary = sum([r.net_salary for r in records])
        self.total_overtime_amount = sum([r.overtime_amount for r in records])
        
        self.save()


class PayrollRecord(models.Model):
    """
    পেরোল রেকর্ড - প্রতিটি কর্মচারীর পেরোল তথ্য
    """
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'বকেয়া'),
        ('processing', 'প্রক্রিয়াধীন'),
        ('paid', 'পরিশোধিত'),
        ('hold', 'স্থগিত'),
        ('cancelled', 'বাতিল'),
    )
    
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'নগদ'),
        ('bank_transfer', 'ব্যাংক ট্রান্সফার'),
        ('cheque', 'চেক'),
        ('mobile_banking', 'মোবাইল ব্যাংকিং'),
    )
    
    # Core Fields
    payroll_cycle = models.ForeignKey(PayrollCycle, on_delete=models.CASCADE, 
                                     related_name='payroll_records', verbose_name=_("Payroll Cycle"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, 
                                related_name='payroll_records', verbose_name=_("Employee"))
    
    # Salary Components
    basic_salary = models.DecimalField(_("Basic Salary"), max_digits=10, decimal_places=2, default=0.00)
    
    # Allowances
    house_rent_allowance = models.DecimalField(_("House Rent"), max_digits=10, decimal_places=2, default=0.00)
    medical_allowance = models.DecimalField(_("Medical"), max_digits=10, decimal_places=2, default=0.00)
    conveyance_allowance = models.DecimalField(_("Conveyance"), max_digits=10, decimal_places=2, default=0.00)
    food_allowance = models.DecimalField(_("Food"), max_digits=10, decimal_places=2, default=0.00)
    attendance_bonus = models.DecimalField(_("Attendance Bonus"), max_digits=10, decimal_places=2, default=0.00)
    festival_bonus = models.DecimalField(_("Festival Bonus"), max_digits=10, decimal_places=2, default=0.00)
    other_allowances = models.DecimalField(_("Other Allowances"), max_digits=10, decimal_places=2, default=0.00)
    
    # Overtime
    overtime_hours = models.DecimalField(_("Overtime Hours"), max_digits=6, decimal_places=2, default=0.00)
    overtime_rate = models.DecimalField(_("Overtime Rate"), max_digits=8, decimal_places=2, default=0.00)
    overtime_amount = models.DecimalField(_("Overtime Amount"), max_digits=10, decimal_places=2, default=0.00)
    
    # Hourly Wage (for hourly paid employees)
    working_hours = models.DecimalField(_("Working Hours"), max_digits=6, decimal_places=2, default=0.00)
    hourly_rate = models.DecimalField(_("Hourly Rate"), max_digits=8, decimal_places=2, default=0.00)
    hourly_wage_amount = models.DecimalField(_("Hourly Wage Amount"), max_digits=10, decimal_places=2, default=0.00)
    
    # Deductions
    provident_fund = models.DecimalField(_("Provident Fund"), max_digits=10, decimal_places=2, default=0.00)
    tax_deduction = models.DecimalField(_("Tax"), max_digits=10, decimal_places=2, default=0.00)
    loan_deduction = models.DecimalField(_("Loan"), max_digits=10, decimal_places=2, default=0.00)
    absence_deduction = models.DecimalField(_("Absence Deduction"), max_digits=10, decimal_places=2, default=0.00)
    other_deductions = models.DecimalField(_("Other Deductions"), max_digits=10, decimal_places=2, default=0.00)
    
    # Attendance Data
    working_days = models.IntegerField(_("Working Days"), default=0)
    present_days = models.DecimalField(_("Present Days"), max_digits=5, decimal_places=1, default=0.0)
    absent_days = models.IntegerField(_("Absent Days"), default=0)
    leave_days = models.IntegerField(_("Leave Days"), default=0)
    half_days = models.IntegerField(_("Half Days"), default=0)
    late_arrivals = models.IntegerField(_("Late Arrivals"), default=0)
    early_departures = models.IntegerField(_("Early Departures"), default=0)
    
    # Calculated Totals
    total_allowances = models.DecimalField(_("Total Allowances"), max_digits=10, decimal_places=2, default=0.00)
    total_deductions = models.DecimalField(_("Total Deductions"), max_digits=10, decimal_places=2, default=0.00)
    gross_salary = models.DecimalField(_("Gross Salary"), max_digits=10, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(_("Net Salary"), max_digits=10, decimal_places=2, default=0.00)
    
    # Payment Information
    payment_status = models.CharField(_("Payment Status"), max_length=20, 
                                     choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(_("Payment Method"), max_length=30, 
                                     choices=PAYMENT_METHOD_CHOICES, default='cash')
    payment_date = models.DateField(_("Payment Date"), null=True, blank=True)
    payment_reference = models.CharField(_("Payment Reference"), max_length=100, blank=True, null=True)
    
    # Bank Details
    bank_name = models.CharField(_("Bank Name"), max_length=100, blank=True, null=True)
    bank_account = models.CharField(_("Bank Account"), max_length=50, blank=True, null=True)
    
    # Additional Info
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    
    # Metadata
    generated_at = models.DateTimeField(_("Generated At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Payroll Record")
        verbose_name_plural = _("Payroll Records")
        unique_together = ('payroll_cycle', 'employee')
        ordering = ['employee__employee_id']
        indexes = [
            models.Index(fields=['payroll_cycle', 'employee']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['payment_date']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.payroll_cycle.name}"
    
    def calculate_totals(self):
        """Calculate all totals"""
        # Total Allowances
        self.total_allowances = (
            self.house_rent_allowance + 
            self.medical_allowance + 
            self.conveyance_allowance + 
            self.food_allowance + 
            self.attendance_bonus + 
            self.festival_bonus + 
            self.other_allowances
        )
        
        # Overtime Amount
        self.overtime_amount = self.overtime_hours * self.overtime_rate
        
        # Hourly Wage Amount
        self.hourly_wage_amount = self.working_hours * self.hourly_rate
        
        # Total Deductions
        self.total_deductions = (
            self.provident_fund + 
            self.tax_deduction + 
            self.loan_deduction + 
            self.absence_deduction + 
            self.other_deductions
        )
        
        # Gross Salary = Basic + Allowances + Overtime + Hourly Wage
        self.gross_salary = (
            self.basic_salary + 
            self.total_allowances + 
            self.overtime_amount + 
            self.hourly_wage_amount
        )
        
        # Net Salary = Gross - Deductions
        self.net_salary = self.gross_salary - self.total_deductions
        
        self.save()
    
    def save(self, *args, **kwargs):
        # Auto-calculate totals before saving
        if not kwargs.pop('skip_calculation', False):
            # Calculate totals inline to avoid recursion
            self.total_allowances = (
                self.house_rent_allowance + 
                self.medical_allowance + 
                self.conveyance_allowance + 
                self.food_allowance + 
                self.attendance_bonus + 
                self.festival_bonus + 
                self.other_allowances
            )
            
            self.overtime_amount = self.overtime_hours * self.overtime_rate
            self.hourly_wage_amount = self.working_hours * self.hourly_rate
            
            self.total_deductions = (
                self.provident_fund + 
                self.tax_deduction + 
                self.loan_deduction + 
                self.absence_deduction + 
                self.other_deductions
            )
            
            self.gross_salary = (
                self.basic_salary + 
                self.total_allowances + 
                self.overtime_amount + 
                self.hourly_wage_amount
            )
            
            self.net_salary = self.gross_salary - self.total_deductions
        
        super().save(*args, **kwargs)


class PayrollAdjustment(models.Model):
    """
    পেরোল সমন্বয় - বোনাস, কর্তন বা অন্যান্য সমন্বয়
    """
    ADJUSTMENT_TYPE_CHOICES = (
        ('addition', 'যোগ'),
        ('deduction', 'বাদ'),
    )
    
    payroll_record = models.ForeignKey(PayrollRecord, on_delete=models.CASCADE, 
                                      related_name='adjustments', verbose_name=_("Payroll Record"))
    
    adjustment_type = models.CharField(_("Type"), max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    title = models.CharField(_("Title"), max_length=200)
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    description = models.TextField(_("Description"), blank=True, null=True)
    
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, 
                                  verbose_name=_("Created By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("Payroll Adjustment")
        verbose_name_plural = _("Payroll Adjustments")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.amount} ({self.get_adjustment_type_display()})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update payroll record
        if self.adjustment_type == 'addition':
            self.payroll_record.other_allowances += self.amount
        else:
            self.payroll_record.other_deductions += self.amount
        
        self.payroll_record.calculate_totals()


class PayrollPayment(models.Model):
    """
    পেরোল পেমেন্ট - পেমেন্ট ট্র্যাকিং
    """
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'বকেয়া'),
        ('processing', 'প্রক্রিয়াধীন'),
        ('completed', 'সম্পন্ন'),
        ('failed', 'ব্যর্থ'),
        ('cancelled', 'বাতিল'),
    )
    
    payroll_record = models.ForeignKey(PayrollRecord, on_delete=models.CASCADE, 
                                      related_name='payments', verbose_name=_("Payroll Record"))
    
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    payment_date = models.DateField(_("Payment Date"))
    payment_method = models.CharField(_("Payment Method"), max_length=30)
    
    reference_number = models.CharField(_("Reference Number"), max_length=100, blank=True, null=True)
    transaction_id = models.CharField(_("Transaction ID"), max_length=100, blank=True, null=True)
    
    status = models.CharField(_("Status"), max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    notes = models.TextField(_("Notes"), blank=True, null=True)
    
    processed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, 
                                    verbose_name=_("Processed By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Payroll Payment")
        verbose_name_plural = _("Payroll Payments")
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"Payment {self.amount} - {self.payroll_record.employee.name} - {self.payment_date}"


class PayrollTemplate(models.Model):
    """
    পেরোল টেমপ্লেট - পূর্ব-সংজ্ঞায়িত সেটিংস
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Template Name"), max_length=100)
    description = models.TextField(_("Description"), blank=True, null=True)
    
    # Default Settings
    default_cycle_type = models.CharField(_("Default Cycle Type"), max_length=20, default='monthly')
    payment_day = models.IntegerField(_("Payment Day"), default=5, 
                                     help_text=_("Day of month for payment"))
    
    # Auto-calculate flags
    auto_calculate_overtime = models.BooleanField(_("Auto Calculate Overtime"), default=True)
    auto_calculate_deductions = models.BooleanField(_("Auto Calculate Deductions"), default=True)
    auto_calculate_bonuses = models.BooleanField(_("Auto Calculate Bonuses"), default=False)
    
    # Bonus Rules
    perfect_attendance_bonus = models.DecimalField(_("Perfect Attendance Bonus"), 
                                                   max_digits=10, decimal_places=2, default=0.00)
    minimum_attendance_for_bonus = models.DecimalField(_("Min Attendance % for Bonus"), 
                                                       max_digits=5, decimal_places=2, default=95.0)
    
    # Deduction Rules
    per_day_absence_deduction_rate = models.DecimalField(_("Per Day Absence Deduction %"), 
                                                         max_digits=5, decimal_places=2, default=100.0)
    late_arrival_penalty = models.DecimalField(_("Late Arrival Penalty"), 
                                               max_digits=10, decimal_places=2, default=0.00)
    
    is_active = models.BooleanField(_("Active"), default=True)
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Payroll Template")
        verbose_name_plural = _("Payroll Templates")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.company.name}"