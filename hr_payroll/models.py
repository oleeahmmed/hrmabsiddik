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