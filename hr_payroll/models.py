from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import logging
from django.utils.dateparse import parse_datetime

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

# models.py - Employee model এর updated version

# Add this field to your Employee model in models.py

class Employee(models.Model):
    """
    Represents an employee in the organization.
    Has ForeignKey relationships with Company, Department, Designation, and Shift.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, verbose_name=_("Department"), blank=True, null=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, verbose_name=_("Designation"), blank=True, null=True)
    default_shift = models.ForeignKey('Shift', on_delete=models.SET_NULL, verbose_name=_("Default Shift"), blank=True, null=True)
    employee_id = models.CharField(_("Employee ID"), max_length=50, unique=True)
    zkteco_id = models.CharField(_("ZKTeco ID"), max_length=50, unique=True)
    name = models.CharField(_("Name"), max_length=100)
    first_name = models.CharField(_("First Name"), max_length=50, blank=True, null=True)
    last_name = models.CharField(_("Last Name"), max_length=50, blank=True, null=True)
    
    # Salary and working hour configurations
    basic_salary = models.DecimalField(_("Basic Salary"), max_digits=10, decimal_places=2, default=0.00)
    overtime_rate = models.DecimalField(_("Overtime Rate (per hour)"), max_digits=8, decimal_places=2, default=0.00)
    per_hour_rate = models.DecimalField(_("Per Hour Rate"), max_digits=8, decimal_places=2, default=30.00)  # NEW FIELD
    expected_working_hours = models.FloatField(_("Expected Working Hours"), default=8.0)
    
    overtime_grace_minutes = models.IntegerField(_("Overtime Grace Minutes"), default=15)
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee_id} - {self.name}"

    def get_full_name(self):
        """Returns the employee's full name for RosterAssignment."""
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or self.name
    
    def get_hourly_rate(self):
        """Calculate hourly rate from basic salary"""
        if self.basic_salary and self.expected_working_hours:
            # Assuming monthly salary and 22 working days
            return float(self.basic_salary) / (22 * self.expected_working_hours)
        return 0.0
    
    def get_per_hour_rate(self):
        """Get per hour rate for hourly attendance calculation"""
        return float(self.per_hour_rate)
    
    def get_overtime_rate(self):
        """Get overtime rate, fallback to 1.5x hourly rate if not set"""
        if self.overtime_rate:
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

class AttendanceLog(models.Model):
    """
    Stores raw attendance data from ZKTeco devices.
    """
    SOURCE_TYPES = (
        ('ZK', 'ZKTeco Device'),
        ('MN', 'Manual'),
    )

    device = models.ForeignKey(ZkDevice, on_delete=models.CASCADE, verbose_name=_("Device"))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name=_("Employee"))
    timestamp = models.DateTimeField(_("Timestamp"))
    status_code = models.IntegerField(_("Status Code"), default=0)
    punch_type = models.CharField(_("Punch Type"), max_length=50, default='UNKNOWN')
    source_type = models.CharField(_("Source Type"), max_length=10, choices=SOURCE_TYPES, default='ZK')
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.timestamp}"

    class Meta:
        verbose_name = _("Attendance Log")
        verbose_name_plural = _("Attendance Logs")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', 'timestamp']),
            models.Index(fields=['device', 'timestamp']),
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


