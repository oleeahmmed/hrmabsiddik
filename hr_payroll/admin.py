# admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect

from .models import (
    Department, Designation, Shift, Employee,
    EmployeeSeparation, Roster, RosterAssignment, RosterDay,
    Holiday, LeaveType, LeaveBalance, LeaveApplication,
    ZkDevice, AttendanceLog, Attendance
)


class CustomModelAdmin(ModelAdmin):
    """কাস্টম বেস ModelAdmin যাতে সাধারণ সেটিংস থাকে"""
    search_help_text = _("Search by name, code, or ID")
    list_per_page = 25
    empty_value_display = _("Not set")


class RosterAssignmentInline(admin.TabularInline):
    model = RosterAssignment
    extra = 1
    fields = ('employee', 'shift')
    autocomplete_fields = ['employee', 'shift']
    verbose_name = _("Roster Assignment")
    verbose_name_plural = _("Roster Assignments")


class RosterDayInline(admin.TabularInline):
    model = RosterDay
    extra = 7
    fields = ('date', 'shift')
    autocomplete_fields = ['shift']
    verbose_name = _("Roster Day")
    verbose_name_plural = _("Roster Days")


class LeaveBalanceInline(admin.TabularInline):
    model = LeaveBalance
    extra = 1
    fields = ('leave_type', 'entitled_days', 'used_days', 'remaining_days')
    readonly_fields = ('remaining_days',)
    autocomplete_fields = ['leave_type']
    verbose_name = _("Leave Balance")
    verbose_name_plural = _("Leave Balances")


class LeaveApplicationInline(admin.TabularInline):
    model = LeaveApplication
    extra = 1
    fields = ('leave_type', 'start_date', 'end_date', 'status', 'reason')
    autocomplete_fields = ['leave_type', 'approved_by']
    fk_name = 'employee'
    verbose_name = _("Leave Application")
    verbose_name_plural = _("Leave Applications")


@admin.register(Department)
class DepartmentAdmin(CustomModelAdmin):
    list_display = ('name', 'code', 'company', 'created_at')
    list_filter = ('company', 'created_at')
    search_fields = ('name', 'code', 'company__name')
    ordering = ('company', 'name')
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'code')
        }),
        (_("Additional Information"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Designation)
class DesignationAdmin(CustomModelAdmin):
    list_display = ('name', 'code', 'company', 'department', 'created_at')
    list_filter = ('company', 'department', 'created_at')
    search_fields = ('name', 'code', 'company__name', 'department__name')
    ordering = ('company', 'name')
    list_select_related = ('company', 'department')
    
    fieldsets = (
        (None, {
            'fields': ('company', 'department', 'name', 'code')
        }),
        (_("Additional Information"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Shift)
class ShiftAdmin(CustomModelAdmin):
    list_display = ('name', 'company', 'start_time', 'end_time', 'duration', 'grace_time')
    list_filter = ('company', 'start_time')
    search_fields = ('name', 'company__name')
    ordering = ('company', 'start_time')
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name')
        }),
        (_("Time Settings"), {
            'fields': ('start_time', 'end_time', 'break_time', 'grace_time')
        }),
    )


@admin.register(Employee)
class EmployeeAdmin(CustomModelAdmin):
    list_display = (
        'employee_id', 'name', 'company', 'department', 
        'designation', 'basic_salary', 'is_active', 'created_at'
    )
    list_filter = ('company', 'department', 'designation', 'is_active', 'created_at')
    search_fields = (
        'employee_id', 'name', 'first_name', 'last_name', 
        'zkteco_id', 'department__name', 'designation__name'
    )
    ordering = ('company', 'employee_id')
    list_select_related = ('company', 'department', 'designation')
    inlines = [LeaveBalanceInline, LeaveApplicationInline, RosterAssignmentInline]
    
    fieldsets = (
        (None, {
            'fields': ('company', 'employee_id', 'zkteco_id')
        }),
        (_("Personal Information"), {
            'fields': ('name', 'first_name', 'last_name')
        }),
        (_("Employment Details"), {
            'fields': ('department', 'designation', 'default_shift', 'is_active')
        }),
        (_("Salary & Hours"), {
            'fields': (
                'basic_salary', 'overtime_rate', 
                'expected_working_hours', 'overtime_grace_minutes'
            )
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'department', 'designation', 'default_shift'
    )


@admin.register(EmployeeSeparation)
class EmployeeSeparationAdmin(CustomModelAdmin):
    list_display = ('employee', 'separation_date', 'is_voluntary', 'created_at')
    list_filter = ('is_voluntary', 'separation_date', 'created_at')
    search_fields = ('employee__employee_id', 'employee__name', 'reason')
    ordering = ('-separation_date',)
    list_select_related = ('employee',)
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'separation_date', 'is_voluntary')
        }),
        (_("Separation Details"), {
            'fields': ('reason',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Roster)
class RosterAdmin(CustomModelAdmin):
    list_display = ('name', 'company', 'start_date', 'end_date', 'days_count', 'created_at')
    list_filter = ('company', 'start_date', 'end_date')
    search_fields = ('name', 'company__name', 'description')
    ordering = ('-start_date',)
    inlines = [RosterAssignmentInline]
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'start_date', 'end_date')
        }),
        (_("Description"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )
    
    def days_count(self, obj):
        return obj.roster_assignments.count()
    days_count.short_description = _("Assignments Count")


@admin.register(RosterAssignment)
class RosterAssignmentAdmin(CustomModelAdmin):
    list_display = ('employee', 'roster', 'shift', 'days_count', 'created_at')
    list_filter = ('roster', 'shift', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__name', 
        'roster__name', 'shift__name'
    )
    ordering = ('roster__name', 'employee__first_name')
    inlines = [RosterDayInline]
    list_select_related = ('employee', 'roster', 'shift')
    
    def days_count(self, obj):
        return obj.roster_days.count()
    days_count.short_description = _("Scheduled Days")


@admin.register(RosterDay)
class RosterDayAdmin(CustomModelAdmin):
    list_display = ('employee_name', 'date', 'shift', 'roster_name', 'created_at')
    list_filter = ('shift', 'date', 'created_at')
    search_fields = (
        'roster_assignment__employee__employee_id',
        'roster_assignment__employee__name',
        'shift__name'
    )
    ordering = ('-date',)
    list_select_related = ('roster_assignment__employee', 'shift', 'roster_assignment__roster')
    
    def employee_name(self, obj):
        return obj.roster_assignment.employee.name
    employee_name.short_description = _("Employee")
    employee_name.admin_order_field = 'roster_assignment__employee__name'
    
    def roster_name(self, obj):
        return obj.roster_assignment.roster.name
    roster_name.short_description = _("Roster")
    roster_name.admin_order_field = 'roster_assignment__roster__name'


@admin.register(Holiday)
class HolidayAdmin(CustomModelAdmin):
    list_display = ('name', 'company', 'date', 'created_at')
    list_filter = ('company', 'date', 'created_at')
    search_fields = ('name', 'company__name', 'description')
    ordering = ('-date',)
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'date')
        }),
        (_("Description"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )


@admin.register(LeaveType)
class LeaveTypeAdmin(CustomModelAdmin):
    list_display = ('name', 'code', 'company', 'paid', 'max_days', 'carry_forward', 'created_at')
    list_filter = ('company', 'paid', 'carry_forward', 'created_at')
    search_fields = ('name', 'code', 'company__name')
    ordering = ('company', 'name')
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'code')
        }),
        (_("Leave Policy"), {
            'fields': ('max_days', 'paid', 'carry_forward', 'max_carry_forward_days')
        }),
    )


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(CustomModelAdmin):
    list_display = ('employee', 'leave_type', 'entitled_days', 'used_days', 'remaining_days', 'created_at')
    list_filter = ('leave_type', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__name', 
        'leave_type__name', 'leave_type__code'
    )
    ordering = ('-created_at',)
    list_select_related = ('employee', 'leave_type')
    readonly_fields = ('remaining_days',)
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'leave_type')
        }),
        (_("Balance Information"), {
            'fields': ('entitled_days', 'used_days', 'remaining_days')
        }),
    )


@admin.register(LeaveApplication)
class LeaveApplicationAdmin(CustomModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status', 'duration', 'created_at')
    list_filter = ('leave_type', 'status', 'start_date', 'end_date', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__name', 
        'leave_type__name', 'reason'
    )
    ordering = ('-created_at',)
    list_select_related = ('employee', 'leave_type', 'approved_by')
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'leave_type', 'status', 'approved_by')
        }),
        (_("Leave Period"), {
            'fields': ('start_date', 'end_date')
        }),
        (_("Reason"), {
            'fields': ('reason',),
            'classes': ('collapse',)
        }),
    )
    
    def duration(self, obj):
        if obj.end_date and obj.start_date:
            return (obj.end_date - obj.start_date).days + 1
        return 0
    duration.short_description = _("Duration (Days)")


@admin.register(ZkDevice)
class ZkDeviceAdmin(CustomModelAdmin):
    list_display = ('name', 'company', 'ip_address', 'port', 'is_active', 'last_synced', 'created_at')
    list_filter = ('company', 'is_active', 'last_synced', 'created_at')
    search_fields = ('name', 'ip_address', 'company__name')
    ordering = ('company', 'name')
    list_select_related = ('company',)
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'ip_address', 'port', 'is_active')
        }),
        (_("Authentication"), {
            'fields': ('password',),
            'classes': ('collapse',)
        }),
        (_("Description"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )


@admin.register(AttendanceLog)
class AttendanceLogAdmin(CustomModelAdmin):
    list_display = ('employee', 'device', 'timestamp', 'punch_type', 'source_type', 'created_at')
    list_filter = ('source_type', 'punch_type', 'timestamp', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__name', 
        'device__name', 'device__ip_address'
    )
    ordering = ('-timestamp',)
    list_select_related = ('employee', 'device')
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'device', 'timestamp')
        }),
        (_("Log Details"), {
            'fields': ('status_code', 'punch_type', 'source_type'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Attendance)
class AttendanceAdmin(CustomModelAdmin):
    list_display = (
        'employee', 'date', 'shift', 'status', 
        'check_in_time', 'check_out_time', 'work_hours', 
        'overtime_hours', 'created_at'
    )
    list_filter = ('status', 'date', 'shift', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__name',
        'shift__name'
    )
    ordering = ('-date',)
    list_select_related = ('employee', 'shift')
    readonly_fields = ('work_hours',)
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'date', 'shift', 'status')
        }),
        (_("Time Records"), {
            'fields': ('check_in_time', 'check_out_time', 'work_hours')
        }),
        (_("Overtime"), {
            'fields': ('overtime_hours',),
            'classes': ('collapse',)
        }),
    )



from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from .models import AttendanceProcessorConfiguration

@admin.register(AttendanceProcessorConfiguration)
class AttendanceProcessorConfigurationAdmin(ModelAdmin):
    list_display = ['name', 'company', 'is_active', 'weekend_display', 'created_at']
    list_filter = ['is_active', 'company', 'created_at']
    search_fields = ['name', 'company__name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (_("General Info"), {
            "fields": ("company", "name", "is_active", "created_by"),
            "classes": ("tab", "col2"),
        }),
        (_("Basic Attendance"), {
            "fields": (
                "grace_minutes",
                "early_out_threshold_minutes",
                "overtime_start_after_minutes",
                "minimum_overtime_minutes",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Weekend & Breaks"), {
            "fields": (
                ("weekend_monday", "weekend_tuesday", "weekend_wednesday", "weekend_thursday"),
                ("weekend_friday", "weekend_saturday", "weekend_sunday"),
                "default_break_minutes",
                "use_shift_break_time",
                "break_deduction_method",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Minimum & Half Day Rules"), {
            "fields": (
                "enable_minimum_working_hours_rule",
                "minimum_working_hours_for_present",
                "enable_working_hours_half_day_rule",
                "half_day_minimum_hours",
                "half_day_maximum_hours",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("In/Out & Max Hours Rules"), {
            "fields": (
                "require_both_in_and_out",
                "enable_maximum_working_hours_rule",
                "maximum_allowable_working_hours",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Shift Management"), {
            "fields": (
                "enable_dynamic_shift_detection",
                "dynamic_shift_tolerance_minutes",
                "multiple_shift_priority",
                "dynamic_shift_fallback_to_default",
                "dynamic_shift_fallback_shift",
                "use_shift_grace_time",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Absence & Early Out"), {
            "fields": (
                "enable_consecutive_absence_flagging",
                "consecutive_absence_termination_risk_days",
                "enable_max_early_out_flagging",
                "max_early_out_threshold_minutes",
                "max_early_out_occurrences",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Overtime Settings"), {
            "fields": (
                "overtime_calculation_method",
                "holiday_overtime_full_day",
                "weekend_overtime_full_day",
                "late_affects_overtime",
                "separate_ot_break_time",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Employee Specific"), {
            "fields": (
                "use_employee_specific_grace",
                "use_employee_specific_overtime",
                "use_employee_expected_hours",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Advanced Rules"), {
            "fields": (
                "late_to_absent_days",
                "holiday_before_after_absent",
                "weekend_before_after_absent",
                "require_holiday_presence",
                "include_holiday_analysis",
                "holiday_buffer_days",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Display Options"), {
            "fields": (
                "show_absent_employees",
                "show_leave_employees",
                "show_holiday_status",
                "include_roster_info",
            ),
            "classes": ("tab", "col2"),
        }),
        (_("Metadata"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("tab", "col2"),
        }),
    )

    def weekend_display(self, obj):
        days = []
        if obj.weekend_monday: days.append('Mon')
        if obj.weekend_tuesday: days.append('Tue')
        if obj.weekend_wednesday: days.append('Wed')
        if obj.weekend_thursday: days.append('Thu')
        if obj.weekend_friday: days.append('Fri')
        if obj.weekend_saturday: days.append('Sat')
        if obj.weekend_sunday: days.append('Sun')
        return ', '.join(days) if days else 'None'
    weekend_display.short_description = 'Weekend Days'
