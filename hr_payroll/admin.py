from django.contrib import admin
from unfold.admin import ModelAdmin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse, path
from django.http import HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.shortcuts import render
from django.template.response import TemplateResponse
from datetime import datetime, timedelta
from django.db import transaction
import logging
from django.contrib.admin.views.decorators import staff_member_required
from .zkteco_device_manager import ZKTecoDeviceManager
import logging
import json

from unfold.admin import TabularInline
from .models import (AttendanceProcessorConfiguration,
    Department, Designation, Shift, Employee,
    EmployeeSeparation, Roster, RosterAssignment, RosterDay,Location, UserLocation,
    Holiday, LeaveType, LeaveBalance, LeaveApplication,
    ZkDevice, AttendanceLog, Attendance,    Notice, Recruitment, JobApplication, Training, TrainingEnrollment,
    Performance, PerformanceGoal, EmployeeDocument, Overtime,
    Resignation, Clearance, Complaint
)
logger = logging.getLogger(__name__)
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required


class CustomAdminPageView(View):
    """Class-based custom admin page view"""
    
    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        """Handle GET requests"""
        context = {
            **admin.site.each_context(request),  # This adds all admin context including sidebar
            'title': 'My Custom Page',
            'subtitle': 'This is a custom admin page',
            'opts': None,  # Add this to avoid template errors
        }
        return render(request, 'admin/custom_page.html', context)

# ADD THIS TO YOUR EXISTING admin.py (usually at the bottom)
# Get the original admin URLs and add our custom one
original_get_urls = admin.site.get_urls

def custom_get_urls():
    from django.urls import path
    custom_urls = [
        path('custom-page/', admin.site.admin_view(CustomAdminPageView.as_view()), name='custom-page'),
    ]
    return custom_urls + original_get_urls()

admin.site.get_urls = custom_get_urls

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
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'code'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('description',),
            'classes': ('tab', 'collapse')
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
        (_("📋 Required Fields"), {
            'fields': ('company', 'department', 'name', 'code'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('description',),
            'classes': ('tab', 'collapse')
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
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'start_time', 'end_time'),
            'classes': ('tab',)
        }),
        (_("⚙️ Optional Settings"), {
            'fields': ('break_time', 'grace_time'),
            'classes': ('tab', 'collapse')
        }),
    )


@admin.register(Employee)
class EmployeeAdmin(CustomModelAdmin):
    list_display = (
        'employee_id', 'name', 'company', 'department', 
        'designation', 'base_salary', 'is_active', 'created_at'
    )
    list_filter = ('company', 'department', 'designation', 'is_active', 'created_at')
    search_fields = (
        'employee_id', 'name', 'first_name', 'last_name', 
        'zkteco_id', 'department__name', 'designation__name',
        'contact_number', 'nid'
    )
    ordering = ('company', 'employee_id')
    list_select_related = ('company', 'department', 'designation', 'default_shift')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': (
                'employee_id',
                'name',
                'is_active',
            ),
            'classes': ('tab',)
        }),
        (_("🏢 Organization"), {
            'fields': (
                'department',
                'designation',
                'default_shift',
                'zkteco_id',
                'joining_date',
            ),
            'classes': ('tab',)
        }),
        (_("💰 Salary Structure"), {
            'fields': (
                'base_salary',
                'per_hour_rate',
                'expected_working_hours',
                'overtime_rate',
                'overtime_grace_minutes',
            ),
            'classes': ('tab',)
        }),
        (_("💵 Allowances"), {
            'fields': (
                'house_rent_allowance',
                'medical_allowance',
                'conveyance_allowance',
                'food_allowance',
                'attendance_bonus',
                'festival_bonus',
            ),
            'classes': ('tab', 'collapse')
        }),
        (_("📉 Deductions"), {
            'fields': (
                'provident_fund',
                'tax_deduction',
                'loan_deduction',
            ),
            'classes': ('tab', 'collapse')
        }),
        (_("👤 Personal Info"), {
            'fields': (
                'user',
                'first_name', 
                'last_name',
                'contact_number',
                'date_of_birth',
                'marital_status',
                'nid',
                'gender',
                'blood_group',
                'passport_no',
                'email',
            ),
            'classes': ('tab', 'collapse')
        }),
        (_("🏠 Address & Contacts"), {
            'fields': (
                'emergency_contact',
                'emergency_contact_name',
                'emergency_contact_relation',
                'present_address',
                'permanent_address',
            ),
            'classes': ('tab', 'collapse')
        }),
        (_("🏦 Banking"), {
            'fields': (
                'bank_account_no',
                'payment_method',
                'bank_name',
                'bank_branch',
            ),
            'classes': ('tab', 'collapse')
        }),
        (_("📋 Additional Info"), {
            'fields': (
                'job_type',
                'employment_status',
                'highest_education',
                'university',
                'passing_year',
                'bio',
                'skills',
                'experience',
            ),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'department', 'designation', 'default_shift', 'user'
        )

    def get_readonly_fields(self, request, obj=None):
        """Make company readonly if user has limited permissions"""
        readonly_fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            return readonly_fields + ('company',)
        return readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        """Set the company field based on user's profile"""
        form = super().get_form(request, obj, **kwargs)
        
        # If user has a profile with company, set it as default
        try:
            from core.models import UserProfile  # Adjust import based on your app structure
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.company:
                form.base_fields['company'].initial = user_profile.company
                
                # If user is not superuser, limit company choices to their company only
                if not request.user.is_superuser:
                    form.base_fields['company'].queryset = Company.objects.filter(id=user_profile.company.id)
                    form.base_fields['company'].empty_label = None
                    
        except (UserProfile.DoesNotExist, ImportError):
            pass
            
        return form

    def save_model(self, request, obj, form, change):
        """Automatically set company from user profile if not set"""
        if not obj.company_id:
            try:
                from core.models import UserProfile
                user_profile = UserProfile.objects.get(user=request.user)
                if user_profile.company:
                    obj.company = user_profile.company
            except (UserProfile.DoesNotExist, ImportError):
                pass
        
        # Set created_by if it's a new object
        if not obj.pk:
            obj.created_by = request.user
            
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        """Remove company field from display if user has limited permissions"""
        fieldsets = super().get_fieldsets(request, obj)
        
        # If user has a company in their profile and is not superuser, hide company field
        try:
            from core.models import UserProfile
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.company and not request.user.is_superuser:
                # Remove company field from all fieldsets
                modified_fieldsets = []
                for name, data in fieldsets:
                    if 'fields' in data:
                        # Filter out company field
                        filtered_fields = tuple(
                            field for field in data['fields'] 
                            if field != 'company'
                        )
                        modified_fieldsets.append((name, {
                            'fields': filtered_fields,
                            'classes': data.get('classes', ())
                        }))
                    else:
                        modified_fieldsets.append((name, data))
                return modified_fieldsets
                
        except (UserProfile.DoesNotExist, ImportError):
            pass
            
        return fieldsets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices based on user's company"""
        # If user has a company in profile and is not superuser, filter related objects
        try:
            from core.models import UserProfile
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.company and not request.user.is_superuser:
                company = user_profile.company
                
                if db_field.name == "department":
                    kwargs["queryset"] = Department.objects.filter(company=company)
                elif db_field.name == "designation":
                    kwargs["queryset"] = Designation.objects.filter(company=company)
                elif db_field.name == "default_shift":
                    kwargs["queryset"] = Shift.objects.filter(company=company)
                elif db_field.name == "user":
                    # Optionally filter users by company if you have that relation
                    pass
                    
        except (UserProfile.DoesNotExist, ImportError):
            pass
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
@admin.register(EmployeeSeparation)
class EmployeeSeparationAdmin(CustomModelAdmin):
    list_display = ('employee', 'separation_date', 'is_voluntary', 'created_at')
    list_filter = ('is_voluntary', 'separation_date', 'created_at')
    search_fields = ('employee__employee_id', 'employee__name', 'reason')
    ordering = ('-separation_date',)
    list_select_related = ('employee',)
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'separation_date', 'is_voluntary'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('reason',),
            'classes': ('tab', 'collapse')
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
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'start_date', 'end_date'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('description',),
            'classes': ('tab', 'collapse')
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
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('roster', 'employee', 'shift'),
            'classes': ('tab',)
        }),
    )
    
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
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('roster_assignment', 'date', 'shift'),
            'classes': ('tab',)
        }),
    )
    
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
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'date'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('description',),
            'classes': ('tab', 'collapse')
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
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'code'),
            'classes': ('tab',)
        }),
        (_("⚙️ Leave Policy"), {
            'fields': ('max_days', 'paid', 'carry_forward', 'max_carry_forward_days'),
            'classes': ('tab',)
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
        (_("📋 Required Fields"), {
            'fields': ('employee', 'leave_type'),
            'classes': ('tab',)
        }),
        (_("📊 Balance Information"), {
            'fields': ('entitled_days', 'used_days', 'remaining_days'),
            'classes': ('tab',)
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
        (_("📋 Required Fields"), {
            'fields': ('employee', 'leave_type', 'start_date', 'end_date', 'status'),
            'classes': ('tab',)
        }),
        (_("👤 Approval"), {
            'fields': ('approved_by',),
            'classes': ('tab', 'collapse')
        }),
        (_("📝 Reason"), {
            'fields': ('reason',),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def duration(self, obj):
        if obj.end_date and obj.start_date:
            return (obj.end_date - obj.start_date).days + 1
        return 0
    duration.short_description = _("Duration (Days)")


@admin.register(ZkDevice)
class ZkDeviceAdmin(ModelAdmin):
    list_display = (
        'name', 'company', 'ip_address', 'port', 'is_active', 
        'last_synced', 'connection_status_display', 'created_at'
    )
    list_filter = ('company', 'is_active', 'last_synced', 'created_at')
    search_fields = ('name', 'ip_address', 'company__name')
    ordering = ('company', 'name')
    list_select_related = ('company',)
    
    actions = [
        'test_device_connection',
        'import_users_from_devices',
        'import_attendance_from_devices',
        # 'clear_device_attendance',
    ]
    
    fieldsets = (
        (None, {
            'fields': ('company', 'name', 'ip_address', 'port', 'is_active')
        }),
        (_("Authentication"), {
            'fields': ('password',),
            'classes': ('collapse',)
        }),
        (_("Sync Information"), {
            'fields': ('last_synced',),
            'classes': ('collapse',)
        }),
        (_("Description"), {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )
    
    def get_urls(self):
        """Add custom URLs for AJAX operations"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'import-users-preview/',
                self.admin_site.admin_view(self.import_users_preview_view),
                name='hr_payroll_zkdevice_import_users_preview',
            ),
            path(
                'import-users-execute/',
                self.admin_site.admin_view(self.import_users_execute_view),
                name='hr_payroll_zkdevice_import_users_execute',
            ),
            path(
                'import-users-confirm/',
                self.admin_site.admin_view(self.import_users_confirm_view),
                name='hr_payroll_zkdevice_import_users_confirm',
            ),
            path(
                'import-attendance-preview/',
                self.admin_site.admin_view(self.import_attendance_preview_view),
                name='hr_payroll_zkdevice_import_attendance_preview',
            ),
            path(
                'import-attendance-execute/',
                self.admin_site.admin_view(self.import_attendance_execute_view),
                name='hr_payroll_zkdevice_import_attendance_execute',
            ),
            path(
                'import-attendance-confirm/',
                self.admin_site.admin_view(self.import_attendance_confirm_view),
                name='hr_payroll_zkdevice_import_attendance_confirm',
            ),
        ]
        return custom_urls + urls
    
    def connection_status_display(self, obj):
        """Display connection status with color indicator"""
        if obj.last_synced:
            time_diff = timezone.now() - obj.last_synced
            if time_diff < timedelta(hours=1):
                color = 'green'
                status = 'Recently Synced'
            elif time_diff < timedelta(days=1):
                color = 'orange'
                status = 'Synced Today'
            else:
                color = 'red'
                status = 'Not Recently Synced'
        else:
            color = 'gray'
            status = 'Never Synced'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color, status
        )
    connection_status_display.short_description = _("Connection Status")
    
    def test_device_connection(self, request, queryset):
        """Test connection to selected devices"""
        device_manager = ZKTecoDeviceManager()
        
        device_list = []
        for device in queryset:
            device_list.append({
                'name': device.name,
                'ip': device.ip_address,
                'port': device.port,
                'password': device.password or 0,
            })
        
        results = device_manager.test_multiple_connections(device_list, max_workers=5)
        
        success_count = 0
        failed_count = 0
        
        for device in queryset:
            result = results.get(device.ip_address, {})
            
            if result.get('success'):
                success_count += 1
                device.last_synced = timezone.now()
                device.save(update_fields=['last_synced'])
                
                info = result.get('info', {})
                self.message_user(
                    request,
                    f"✓ Connected: {device.name} ({device.ip_address}) | "
                    f"Users: {info.get('user_count', 0)}, "
                    f"Records: {info.get('attendance_count', 0)}, "
                    f"Firmware: {info.get('firmware_version', 'Unknown')}",
                    messages.SUCCESS
                )
            else:
                failed_count += 1
                error = result.get('error', 'Unknown error')
                self.message_user(
                    request,
                    f"✗ Failed: {device.name} ({device.ip_address}) - {error}",
                    messages.ERROR
                )
        
        device_manager.disconnect_all()
        
        summary_level = messages.SUCCESS if failed_count == 0 else messages.WARNING
        self.message_user(
            request,
            f"Connection test completed: {success_count} successful, {failed_count} failed",
            summary_level
        )
    
    test_device_connection.short_description = _("1. Test Device Connection")
    
    def clear_device_attendance(self, request, queryset):
        """Clear attendance data from selected devices"""
        device_manager = ZKTecoDeviceManager()
        
        success_count = 0
        failed_count = 0
        
        for device in queryset:
            try:
                success, message = device_manager.clear_attendance_data(device.ip_address)
                if success:
                    success_count += 1
                    self.message_user(
                        request,
                        f"✓ Cleared: {device.name} ({device.ip_address})",
                        messages.SUCCESS
                    )
                else:
                    failed_count += 1
                    self.message_user(
                        request,
                        f"✗ Failed: {device.name} ({device.ip_address}) - {message}",
                        messages.ERROR
                    )
            except Exception as e:
                failed_count += 1
                self.message_user(
                    request,
                    f"✗ Error: {device.name} ({device.ip_address}) - {str(e)}",
                    messages.ERROR
                )
        
        device_manager.disconnect_all()
        
        summary_level = messages.SUCCESS if failed_count == 0 else messages.WARNING
        self.message_user(
            request,
            f"Clear attendance completed: {success_count} successful, {failed_count} failed",
            summary_level
        )
    
    clear_device_attendance.short_description = _("Clear Attendance Data")
    
    def import_users_from_devices(self, request, queryset):
        """Import users from selected devices with preview"""
        device_ids = list(queryset.values_list('id', flat=True))
        request.session['import_device_ids'] = device_ids
        
        return HttpResponseRedirect(
            reverse('admin:hr_payroll_zkdevice_import_users_preview')
        )
    
    import_users_from_devices.short_description = _("2. Import Users from Devices")
    
    def import_users_preview_view(self, request):
        """Preview users before importing"""
        device_ids = request.session.get('import_device_ids', [])
        
        if not device_ids:
            self.message_user(request, "No devices selected", messages.ERROR)
            return HttpResponseRedirect(reverse('admin:hr_payroll_zkdevice_changelist'))
        
        devices = ZkDevice.objects.filter(id__in=device_ids)
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Import Users from ZKTeco Devices',
            'devices': devices,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }
        
        return TemplateResponse(
            request,
            'admin/hr_payroll/zkdevice/import_users_preview.html',
            context
        )
    
    def import_users_execute_view(self, request):
        """Execute user fetch via AJAX"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        device_ids = request.session.get('import_device_ids', [])
        
        if not device_ids:
            return JsonResponse({'error': 'No devices selected'}, status=400)
        
        try:
            devices = ZkDevice.objects.filter(id__in=device_ids)
            device_manager = ZKTecoDeviceManager()
            
            device_list = []
            device_map = {}
            
            for device in devices:
                device_list.append({
                    'name': device.name,
                    'ip': device.ip_address,
                    'port': device.port,
                    'password': device.password or 0,
                })
                device_map[device.ip_address] = device
            
            # Fetch users data
            all_users_data, fetch_results = device_manager.get_multiple_users_data(
                device_list, max_workers=3
            )
            
            device_manager.disconnect_all()
            
            # Analyze users data
            analysis = self._analyze_users(all_users_data, devices)
            
            # Store data in session for actual import
            request.session['user_import_data'] = {
                'new_users': analysis['new_users'],
                'existing_users': analysis['existing_users'],
                'device_map': {ip: device.id for ip, device in device_map.items()}
            }
            
            response_data = {
                'success': True,
                'analysis': analysis,
                'fetch_results': fetch_results,
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error fetching users: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def import_users_confirm_view(self, request):
        """Confirm and execute user import"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        import_data = request.session.get('user_import_data')
        if not import_data:
            return JsonResponse({'error': 'No user data to import'}, status=400)
        
        try:
            # Actual import logic
            import_results = self._import_users_to_database(
                import_data['new_users'],
                import_data['existing_users'],
                import_data['device_map']
            )
            
            # Update device sync times
            device_ids = list(import_data['device_map'].values())
            ZkDevice.objects.filter(id__in=device_ids).update(last_synced=timezone.now())
            
            # Clear session data
            request.session.pop('user_import_data', None)
            request.session.pop('import_device_ids', None)
            
            response_data = {
                'success': True,
                'import_results': import_results,
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error importing users: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _analyze_users(self, users_data, devices):
        """Analyze users data and categorize them"""
        company_ids = devices.values_list('company_id', flat=True).distinct()
        
        existing_employees = Employee.objects.filter(
            company_id__in=company_ids
        ).values('zkteco_id', 'employee_id', 'name', 'company_id')
        
        existing_zkteco_ids = {emp['zkteco_id']: emp for emp in existing_employees if emp['zkteco_id']}
        
        new_users = []
        existing_users = []
        duplicate_users = []
        
        seen_zkteco_ids = set()
        
        for user_data in users_data:
            zkteco_id = user_data['user_id']
            
            if zkteco_id in seen_zkteco_ids:
                duplicate_users.append(user_data)
                continue
            
            seen_zkteco_ids.add(zkteco_id)
            
            if zkteco_id in existing_zkteco_ids:
                existing_user = existing_zkteco_ids[zkteco_id]
                user_data['existing_employee_id'] = existing_user['employee_id']
                user_data['existing_name'] = existing_user['name']
                existing_users.append(user_data)
            else:
                new_users.append(user_data)
        
        return {
            'total_fetched': len(users_data),
            'new_users': new_users,
            'existing_users': existing_users,
            'duplicate_users': duplicate_users,
            'new_count': len(new_users),
            'existing_count': len(existing_users),
            'duplicate_count': len(duplicate_users),
        }
    
    def _import_users_to_database(self, new_users, existing_users, device_map):
        """Import new users to Employee table"""
        imported_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        with transaction.atomic():
            for user_data in new_users:
                try:
                    device_ip = user_data.get('device_ip')
                    device_id = device_map.get(device_ip)
                    
                    if not device_id:
                        error_count += 1
                        errors.append(f"Device not found for user {user_data['user_id']}")
                        continue
                    
                    device = ZkDevice.objects.get(id=device_id)
                    
                    # Generate unique employee ID
                    base_emp_id = f"EMP{user_data['user_id']}"
                    employee_id = base_emp_id
                    counter = 1
                    
                    while Employee.objects.filter(employee_id=employee_id, company=device.company).exists():
                        employee_id = f"{base_emp_id}_{counter}"
                        counter += 1
                    
                    employee = Employee.objects.create(
                        company=device.company,
                        employee_id=employee_id,
                        zkteco_id=user_data['user_id'],
                        name=user_data['name'],
                        first_name=user_data['name'].split()[0] if user_data['name'] else '',
                        last_name=' '.join(user_data['name'].split()[1:]) if len(user_data['name'].split()) > 1 else '',
                        is_active=True,
                        base_salary=0.00,
                        overtime_rate=0.00,
                        per_hour_rate=30.00,
                        expected_working_hours=8.0,
                    )
                    
                    imported_count += 1
                    logger.info(f"Imported employee: {employee.employee_id} - {employee.name}")
                    
                except Exception as e:
                    error_count += 1
                    error_msg = f"Error importing user {user_data['user_id']}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            for user_data in existing_users:
                try:
                    employee = Employee.objects.get(zkteco_id=user_data['user_id'])
                    
                    if employee.name != user_data['name']:
                        employee.name = user_data['name']
                        employee.first_name = user_data['name'].split()[0] if user_data['name'] else ''
                        employee.last_name = ' '.join(user_data['name'].split()[1:]) if len(user_data['name'].split()) > 1 else ''
                        employee.save(update_fields=['name', 'first_name', 'last_name'])
                        updated_count += 1
                        
                except Exception as e:
                    error_count += 1
                    errors.append(f"Error updating user {user_data['user_id']}: {str(e)}")
        
        return {
            'imported_count': imported_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'errors': errors[:10],
        }
    
    def import_attendance_from_devices(self, request, queryset):
        """Import attendance logs from selected devices with preview"""
        device_ids = list(queryset.values_list('id', flat=True))
        request.session['import_attendance_device_ids'] = device_ids
        
        return HttpResponseRedirect(
            reverse('admin:hr_payroll_zkdevice_import_attendance_preview')
        )
    
    import_attendance_from_devices.short_description = _("3. Import Attendance Logs")
    
    def import_attendance_preview_view(self, request):
        """Preview attendance before importing"""
        device_ids = request.session.get('import_attendance_device_ids', [])
        
        if not device_ids:
            self.message_user(request, "No devices selected", messages.ERROR)
            return HttpResponseRedirect(reverse('admin:hr_payroll_zkdevice_changelist'))
        
        devices = ZkDevice.objects.filter(id__in=device_ids)
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Import Attendance from ZKTeco Devices',
            'devices': devices,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }
        
        return TemplateResponse(
            request,
            'admin/hr_payroll/zkdevice/import_attendance_preview.html',
            context
        )
    
    def import_attendance_execute_view(self, request):
        """Execute attendance fetch via AJAX"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        device_ids = request.session.get('import_attendance_device_ids', [])
        
        if not device_ids:
            return JsonResponse({'error': 'No devices selected'}, status=400)
        
        try:
            body = json.loads(request.body) if request.body else {}
            days = body.get('days', 30)
            
            devices = ZkDevice.objects.filter(id__in=device_ids)
            device_manager = ZKTecoDeviceManager()
            
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            device_list = []
            device_map = {}
            
            for device in devices:
                device_list.append({
                    'name': device.name,
                    'ip': device.ip_address,
                    'port': device.port,
                    'password': device.password or 0,
                })
                device_map[device.ip_address] = device
            
            # Fetch attendance data
            all_attendance_data, fetch_results = device_manager.get_multiple_attendance_data(
                device_list, start_date, end_date, max_workers=3
            )
            
            device_manager.disconnect_all()
            
            # Analyze attendance data
            analysis_results = self._analyze_attendance_preview(
                all_attendance_data, device_map
            )
            
            # Store data in session for actual import
            request.session['attendance_import_data'] = {
                'attendance_data': [
                    {
                        'zkteco_id': record['zkteco_id'],
                        'timestamp': record['timestamp'].isoformat(),
                        'device_ip': record['device_ip'],
                        'punch_type': record.get('punch_type', 0),
                        'verify_type': record.get('verify_type', 0),
                        'device_name': record.get('device_name', '')
                    }
                    for record in all_attendance_data
                ],
                'device_map': {ip: device.id for ip, device in device_map.items()},
                'date_range': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                }
            }
            
            response_data = {
                'success': True,
                'date_range': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                },
                'analysis_results': analysis_results,
                'fetch_results': fetch_results,
                'total_records': len(all_attendance_data),
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error fetching attendance: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def import_attendance_confirm_view(self, request):
        """Confirm and execute attendance import"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        import_data = request.session.get('attendance_import_data')
        if not import_data:
            return JsonResponse({'error': 'No attendance data to import'}, status=400)
        
        try:
            # Actual import logic
            import_results = self._import_attendance_to_database(
                import_data['attendance_data'], 
                import_data['device_map']
            )
            
            # Update device sync times
            device_ids = list(import_data['device_map'].values())
            ZkDevice.objects.filter(id__in=device_ids).update(last_synced=timezone.now())
            
            # Clear session data
            request.session.pop('attendance_import_data', None)
            request.session.pop('import_attendance_device_ids', None)
            
            response_data = {
                'success': True,
                'import_results': import_results,
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error importing attendance: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _analyze_attendance_preview(self, attendance_data, device_map):
        """Analyze attendance data for preview without importing"""
        imported_count = 0
        skipped_count = 0
        missing_employees = set()
        
        for record in attendance_data:
            device_ip = record['device_ip']
            device = device_map.get(device_ip)
            
            if not device:
                skipped_count += 1
                continue
            
            zkteco_id = record['zkteco_id']
            try:
                employee = Employee.objects.get(
                    zkteco_id=zkteco_id,
                    company=device.company
                )
                imported_count += 1
            except Employee.DoesNotExist:
                missing_employees.add(zkteco_id)
                skipped_count += 1
                continue
        
        return {
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'missing_employees': list(missing_employees)[:10],
            'missing_employees_count': len(missing_employees),
        }
    
    def _import_attendance_to_database(self, attendance_data, device_map):
        """Import attendance records to database"""
        imported_count = 0
        skipped_count = 0
        error_count = 0
        missing_employees = set()
        errors = []
        
        with transaction.atomic():
            for record_data in attendance_data:
                try:
                    device_ip = record_data['device_ip']
                    device_id = device_map.get(device_ip)
                    
                    if not device_id:
                        skipped_count += 1
                        continue
                    
                    device = ZkDevice.objects.get(id=device_id)
                    zkteco_id = record_data['zkteco_id']
                    
                    try:
                        employee = Employee.objects.get(
                            zkteco_id=zkteco_id,
                            company=device.company
                        )
                    except Employee.DoesNotExist:
                        missing_employees.add(zkteco_id)
                        skipped_count += 1
                        continue
                    
                    # Convert string timestamp back to datetime
                    timestamp = datetime.fromisoformat(record_data['timestamp'])
                    
                    attendance_log, created = AttendanceLog.objects.get_or_create(
                        device=device,
                        employee=employee,
                        timestamp=timestamp,
                        defaults={
                            'status_code': record_data.get('verify_type', 0),
                            'punch_type': str(record_data.get('punch_type', 0)),
                            'source_type': 'ZK',
                        }
                    )
                    
                    if created:
                        imported_count += 1
                    else:
                        skipped_count += 1
                        
                except Exception as e:
                    error_count += 1
                    error_msg = f"Error importing record: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        return {
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'error_count': error_count,
            'missing_employees': list(missing_employees)[:10],
            'errors': errors[:10],
        }

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
    
    actions = [
        'generate_attendance_from_logs',
        'clear_attendance_logs',
    ]
    
    fieldsets = (
        (None, {
            'fields': ('employee', 'device', 'timestamp')
        }),
        (_("Log Details"), {
            'fields': ('status_code', 'punch_type', 'source_type'),
            'classes': ('collapse',)
        }),
        (_("Mobile/Location Info"), {
            'fields': ('user', 'location', 'attendance_type', 'latitude', 'longitude'),
            'classes': ('collapse',)
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'generate-attendance-preview/',
                self.admin_site.admin_view(self.generate_attendance_preview_view),
                name='hr_payroll_attendancelog_generate_attendance_preview',
            ),
            path(
                'generate-attendance-execute/',
                self.admin_site.admin_view(self.generate_attendance_execute_view),
                name='hr_payroll_attendancelog_generate_attendance_execute',
            ),
        ]
        return custom_urls + urls
    
    def generate_attendance_from_logs(self, request, queryset):
        """Generate attendance records from selected logs with preview"""
        # Store selected log IDs in session
        log_ids = list(queryset.values_list('id', flat=True))
        request.session['generate_attendance_log_ids'] = log_ids
        
        return HttpResponseRedirect(
            reverse('admin:hr_payroll_attendancelog_generate_attendance_preview')
        )
    
    generate_attendance_from_logs.short_description = _("Generate Attendance Records from Logs")
    
    def clear_attendance_logs(self, request, queryset):
        """Clear selected attendance logs"""
        count = queryset.count()
        queryset.delete()
        
        self.message_user(
            request,
            f"Successfully deleted {count} attendance logs",
            messages.SUCCESS
        )
    
    clear_attendance_logs.short_description = _("Delete Selected Attendance Logs")
    
    def generate_attendance_preview_view(self, request):
        """Preview attendance generation from logs"""
        log_ids = request.session.get('generate_attendance_log_ids', [])
        
        if not log_ids:
            self.message_user(request, "No attendance logs selected", messages.ERROR)
            return HttpResponseRedirect(reverse('admin:hr_payroll_attendancelog_changelist'))
        
        logs = AttendanceLog.objects.filter(id__in=log_ids).select_related('employee', 'device')
        
        # Calculate date range from logs
        dates = logs.values_list('timestamp__date', flat=True).distinct().order_by('timestamp__date')
        if dates:
            start_date = dates.first()
            end_date = dates.last()
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = "No dates found"
        
        # Get unique employees
        employees = Employee.objects.filter(
            id__in=logs.values_list('employee_id', flat=True).distinct()
        )
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Generate Attendance Records from Logs',
            'logs': logs,
            'total_logs': len(log_ids),
            'unique_employees': employees.count(),
            'date_range': date_range,
            'start_date': start_date if dates else None,
            'end_date': end_date if dates else None,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }
        
        return TemplateResponse(
            request,
            'admin/hr_payroll/attendancelog/generate_attendance_preview.html',
            context
        )
    def generate_attendance_execute_view(self, request):
        """Direct implementation without importing external functions"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        log_ids = request.session.get('generate_attendance_log_ids', [])
        
        if not log_ids:
            return JsonResponse({'error': 'No attendance logs selected'}, status=400)
        
        try:
            body = json.loads(request.body) if request.body else {}
            start_date_str = body.get('start_date')
            end_date_str = body.get('end_date')
            regenerate_existing = body.get('regenerate_existing', False)
            
            # Parse dates
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            # Get logs and employees
            logs = AttendanceLog.objects.filter(id__in=log_ids)
            employee_ids = list(logs.values_list('employee_id', flat=True).distinct())
            employees = Employee.objects.filter(id__in=employee_ids)
            
            # Get company
            company = employees.first().company if employees.exists() else None
            if not company:
                return JsonResponse({'error': 'Could not determine company'}, status=400)
            
            # Get active configuration
            config = AttendanceProcessorConfiguration.get_active_config(company)
            if not config:
                return JsonResponse({'error': 'No active attendance configuration found'}, status=400)
            
            config_dict = config.get_config_dict()
            
            # Initialize counters
            created_count = 0
            updated_count = 0
            error_count = 0
            
            # Process each day in the range
            current_date = start_date
            while current_date <= end_date:
                for employee in employees:
                    try:
                        # Get logs for this employee and date
                        day_logs = logs.filter(
                            employee=employee,
                            timestamp__date=current_date
                        ).order_by('timestamp')
                        
                        if not day_logs.exists():
                            continue
                        
                        # Get first check-in and last check-out
                        check_in = day_logs.first().timestamp if day_logs else None
                        check_out = day_logs.last().timestamp if len(day_logs) > 1 else None
                        
                        # Skip if both are None
                        if not check_in and not check_out:
                            continue
                        
                        # Determine shift (simplified logic)
                        shift = employee.default_shift
                        
                        # Calculate working hours
                        working_hours = 0.0
                        if check_in and check_out:
                            total_seconds = (check_out - check_in).total_seconds()
                            working_hours = round(total_seconds / 3600, 2)
                        
                        # Determine status (simplified)
                        status = 'P' if working_hours > 0 else 'A'
                        
                        # Check if record already exists
                        existing_attendance = Attendance.objects.filter(
                            employee=employee,
                            date=current_date
                        ).first()
                        
                        if existing_attendance and not regenerate_existing:
                            # Skip if exists and not regenerating
                            continue
                        
                        # Create or update attendance record
                        attendance_data = {
                            'check_in_time': check_in,
                            'check_out_time': check_out,
                            'status': status,
                            'overtime_hours': 0.0,  # Simplified
                            'shift': shift,
                        }
                        
                        if existing_attendance:
                            # Update existing
                            for field, value in attendance_data.items():
                                setattr(existing_attendance, field, value)
                            existing_attendance.save()
                            updated_count += 1
                        else:
                            # Create new
                            Attendance.objects.create(
                                employee=employee,
                                date=current_date,
                                **attendance_data
                            )
                            created_count += 1
                            
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing {employee.name} on {current_date}: {str(e)}")
                
                current_date += timedelta(days=1)
            
            # Clear session data
            request.session.pop('generate_attendance_log_ids', None)
            
            message = f'Successfully created {created_count} and updated {updated_count} attendance records'
            if error_count > 0:
                message += f' with {error_count} errors'
            
            return JsonResponse({
                'success': True,
                'message': message,
                'results': {
                    'records_created': created_count,
                    'records_updated': updated_count,
                    'error_count': error_count
                }
            })
                    
        except Exception as e:
            logger.error(f"Error generating attendance: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': f'Generation failed: {str(e)}'
            }, status=500)

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
        (_("📋 Required Fields"), {
            'fields': ('employee', 'date', 'status'),
            'classes': ('tab',)
        }),
        (_("⏰ Time Records"), {
            'fields': ('shift', 'check_in_time', 'check_out_time', 'work_hours'),
            'classes': ('tab',)
        }),
        (_("⚡ Overtime"), {
            'fields': ('overtime_hours',),
            'classes': ('tab', 'collapse')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Filter attendance by user's company if not superuser
        if not request.user.is_superuser:
            try:
                from core.models import UserProfile
                user_profile = UserProfile.objects.get(user=request.user)
                if user_profile.company:
                    qs = qs.filter(employee__company=user_profile.company)
            except (UserProfile.DoesNotExist, ImportError):
                pass
        return qs.select_related('employee', 'shift')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices based on user's company"""
        try:
            from core.models import UserProfile
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.company and not request.user.is_superuser:
                company = user_profile.company
                
                if db_field.name == "employee":
                    kwargs["queryset"] = Employee.objects.filter(company=company)
                elif db_field.name == "shift":
                    kwargs["queryset"] = Shift.objects.filter(company=company)
                    
        except (UserProfile.DoesNotExist, ImportError):
            pass
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AttendanceProcessorConfiguration)
class AttendanceProcessorConfigurationAdmin(CustomModelAdmin):
    list_display = ['name', 'company', 'is_active', 'weekend_display', 'created_at']
    list_filter = ['is_active', 'company', 'created_at']
    search_fields = ['name', 'company__name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (_("📋 Required Fields"), {
            "fields": ("company", "name", "is_active"),
            "classes": ("tab",)
        }),
        (_("⚙️ Basic Settings"), {
            "fields": (
                "grace_minutes",
                "early_out_threshold_minutes",
                "overtime_start_after_minutes",
                "minimum_overtime_minutes",
            ),
            "classes": ("tab",)
        }),
        (_("📅 Weekend & Breaks"), {
            "fields": (
                ("weekend_monday", "weekend_tuesday", "weekend_wednesday", "weekend_thursday"),
                ("weekend_friday", "weekend_saturday", "weekend_sunday"),
                "default_break_minutes",
                "use_shift_break_time",
                "break_deduction_method",
            ),
            "classes": ("tab",)
        }),
        (_("👤 User Info"), {
            "fields": ("created_by",),
            "classes": ("tab", "collapse")
        }),
        (_("📊 Minimum & Half Day Rules"), {
            "fields": (
                "enable_minimum_working_hours_rule",
                "minimum_working_hours_for_present",
                "enable_working_hours_half_day_rule",
                "half_day_minimum_hours",
                "half_day_maximum_hours",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("⏰ In/Out & Max Hours Rules"), {
            "fields": (
                "require_both_in_and_out",
                "enable_maximum_working_hours_rule",
                "maximum_allowable_working_hours",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("🔄 Shift Management"), {
            "fields": (
                "enable_dynamic_shift_detection",
                "dynamic_shift_tolerance_minutes",
                "multiple_shift_priority",
                "dynamic_shift_fallback_to_default",
                "dynamic_shift_fallback_shift",
                "use_shift_grace_time",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("⚠️ Absence & Early Out"), {
            "fields": (
                "enable_consecutive_absence_flagging",
                "consecutive_absence_termination_risk_days",
                "enable_max_early_out_flagging",
                "max_early_out_threshold_minutes",
                "max_early_out_occurrences",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("💰 Overtime Settings"), {
            "fields": (
                "overtime_calculation_method",
                "holiday_overtime_full_day",
                "weekend_overtime_full_day",
                "late_affects_overtime",
                "separate_ot_break_time",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("👤 Employee Specific"), {
            "fields": (
                "use_employee_specific_grace",
                "use_employee_specific_overtime",
                "use_employee_expected_hours",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("⚡ Advanced Rules"), {
            "fields": (
                "late_to_absent_days",
                "holiday_before_after_absent",
                "weekend_before_after_absent",
                "require_holiday_presence",
                "include_holiday_analysis",
                "holiday_buffer_days",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("👀 Display Options"), {
            "fields": (
                "show_absent_employees",
                "show_leave_employees",
                "show_holiday_status",
                "include_roster_info",
            ),
            "classes": ("tab", "collapse")
        }),
        (_("📝 Metadata"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("tab", "collapse")
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


class UserLocationInline(admin.TabularInline):
    model = UserLocation
    extra = 1
    fields = ('user', 'is_primary')
    verbose_name = _("User Location Assignment")
    verbose_name_plural = _("User Location Assignments")


@admin.register(Location)
class LocationAdmin(CustomModelAdmin):
    list_display = (
        'name', 'address_short', 'latitude', 'longitude', 
        'radius', 'is_active', 'user_count', 'created_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'address')
    ordering = ('name',)
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('name', 'address', 'is_active'),
            'classes': ('tab',)
        }),
        (_("📍 Geographic Coordinates"), {
            'fields': ('latitude', 'longitude', 'radius'),
            'classes': ('tab',)
        }),
    )
    
    def address_short(self, obj):
        """Display truncated address"""
        return obj.address[:50] + '...' if len(obj.address) > 50 else obj.address
    address_short.short_description = _("Address")
    
    def user_count(self, obj):
        """Count of users assigned to this location"""
        return obj.user_locations.count()
    user_count.short_description = _("Assigned Users")


@admin.register(UserLocation)
class UserLocationAdmin(CustomModelAdmin):
    list_display = (
        'user', 'location', 'is_primary', 'created_at'
    )
    list_filter = ('is_primary', 'location', 'created_at')
    search_fields = ('user__username', 'user__email', 'location__name')
    ordering = ('user__username', 'location__name')
    list_select_related = ('user', 'location')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('user', 'location', 'is_primary'),
            'classes': ('tab',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'location')


@admin.register(Notice)
class NoticeAdmin(CustomModelAdmin):
    list_display = ('title', 'company', 'priority', 'published_date', 'expiry_date', 'is_active', 'created_at')
    list_filter = ('company', 'priority', 'is_active', 'published_date')
    search_fields = ('title', 'description', 'company__name')
    ordering = ('-published_date',)
    list_select_related = ('company', 'created_by')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('company', 'title', 'priority', 'is_active', 'published_date'),
            'classes': ('tab',)
        }),
        (_("📝 Content"), {
            'fields': ('description',),
            'classes': ('tab',)
        }),
        (_("📅 Optional Dates"), {
            'fields': ('expiry_date',),
            'classes': ('tab', 'collapse')
        }),
        (_("👤 Optional Metadata"), {
            'fields': ('created_by',),
            'classes': ('tab', 'collapse')
        }),
    )


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    fields = ('applicant_name', 'email', 'phone', 'status', 'applied_date')
    readonly_fields = ('applied_date',)
    can_delete = False


@admin.register(Recruitment)
class RecruitmentAdmin(CustomModelAdmin):
    list_display = ('job_title', 'company', 'department', 'designation', 'vacancies', 'status', 'posted_date', 'closing_date')
    list_filter = ('company', 'department', 'designation', 'status', 'posted_date')
    search_fields = ('job_title', 'company__name', 'department__name')
    ordering = ('-posted_date',)
    list_select_related = ('company', 'department', 'designation', 'created_by')
    inlines = [JobApplicationInline]
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('company', 'job_title', 'vacancies', 'status', 'posted_date', 'closing_date'),
            'classes': ('tab',)
        }),
        (_("📝 Job Details"), {
            'fields': ('job_description', 'requirements'),
            'classes': ('tab',)
        }),
        (_("🏢 Department Info"), {
            'fields': ('department', 'designation'),
            'classes': ('tab', 'collapse')
        }),
        (_("👤 Optional Metadata"), {
            'fields': ('created_by',),
            'classes': ('tab', 'collapse')
        }),
    )


@admin.register(JobApplication)
class JobApplicationAdmin(CustomModelAdmin):
    list_display = ('applicant_name', 'recruitment_title', 'email', 'phone', 'status', 'applied_date')
    list_filter = ('status', 'applied_date', 'recruitment__company')
    search_fields = ('applicant_name', 'email', 'phone', 'recruitment__job_title')
    ordering = ('-applied_date',)
    list_select_related = ('recruitment',)
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('recruitment', 'applicant_name', 'email', 'phone', 'status'),
            'classes': ('tab',)
        }),
        (_("📄 Application Details"), {
            'fields': ('resume', 'cover_letter'),
            'classes': ('tab', 'collapse')
        }),
        (_("📝 Optional Notes"), {
            'fields': ('notes',),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def recruitment_title(self, obj):
        return obj.recruitment.job_title
    recruitment_title.short_description = _("Job Title")
    recruitment_title.admin_order_field = 'recruitment__job_title'


class TrainingEnrollmentInline(admin.TabularInline):
    model = TrainingEnrollment
    extra = 1
    fields = ('employee', 'status', 'enrollment_date', 'completion_date', 'score')
    readonly_fields = ('enrollment_date',)


@admin.register(Training)
class TrainingAdmin(CustomModelAdmin):
    list_display = ('title', 'company', 'trainer', 'start_date', 'end_date', 'duration_hours', 'status', 'enrollment_count')
    list_filter = ('company', 'status', 'start_date')
    search_fields = ('title', 'trainer', 'company__name')
    ordering = ('-start_date',)
    list_select_related = ('company', 'created_by')
    inlines = [TrainingEnrollmentInline]
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('company', 'title', 'trainer', 'status', 'start_date', 'end_date'),
            'classes': ('tab',)
        }),
        (_("📝 Training Details"), {
            'fields': ('description', 'duration_hours'),
            'classes': ('tab',)
        }),
        (_("👤 Optional Metadata"), {
            'fields': ('created_by',),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def enrollment_count(self, obj):
        return obj.enrollments.count()
    enrollment_count.short_description = _("Enrollments")


@admin.register(TrainingEnrollment)
class TrainingEnrollmentAdmin(CustomModelAdmin):
    list_display = ('employee', 'training', 'status', 'enrollment_date', 'completion_date', 'score')
    list_filter = ('status', 'enrollment_date', 'training__company')
    search_fields = ('employee__name', 'employee__employee_id', 'training__title')
    ordering = ('-enrollment_date',)
    list_select_related = ('employee', 'training')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('training', 'employee', 'status'),
            'classes': ('tab',)
        }),
        (_("📊 Progress"), {
            'fields': ('enrollment_date', 'completion_date', 'score'),
            'classes': ('tab', 'collapse')
        }),
        (_("💬 Optional Feedback"), {
            'fields': ('feedback',),
            'classes': ('tab', 'collapse')
        }),
    )


class PerformanceGoalInline(admin.TabularInline):
    model = PerformanceGoal
    extra = 1
    fields = ('goal_title', 'target_date', 'status', 'completion_date')


@admin.register(Performance)
class PerformanceAdmin(CustomModelAdmin):
    list_display = ('employee', 'review_period_display', 'overall_rating', 'status', 'reviewer', 'review_date')
    list_filter = ('status', 'overall_rating', 'review_period_start', 'review_period_end')
    search_fields = ('employee__name', 'employee__employee_id', 'reviewer__username')
    ordering = ('-review_period_end',)
    list_select_related = ('employee', 'reviewer')
    inlines = [PerformanceGoalInline]
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'review_period_start', 'review_period_end', 'status'),
            'classes': ('tab',)
        }),
        (_("📊 Review Information"), {
            'fields': ('reviewer', 'review_date', 'overall_rating'),
            'classes': ('tab',)
        }),
        (_("💬 Feedback"), {
            'fields': ('strengths', 'weaknesses', 'comments'),
            'classes': ('tab',)
        }),
    )
    
    def review_period_display(self, obj):
        return f"{obj.review_period_start} to {obj.review_period_end}"
    review_period_display.short_description = _("Review Period")


@admin.register(PerformanceGoal)
class PerformanceGoalAdmin(CustomModelAdmin):
    list_display = ('employee', 'goal_title', 'target_date', 'status', 'completion_date')
    list_filter = ('status', 'target_date', 'performance__employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'goal_title')
    ordering = ('-target_date',)
    list_select_related = ('employee', 'performance')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('performance', 'employee', 'goal_title', 'status', 'target_date'),
            'classes': ('tab',)
        }),
        (_("📝 Description"), {
            'fields': ('description',),
            'classes': ('tab',)
        }),
        (_("📅 Optional Timeline"), {
            'fields': ('completion_date',),
            'classes': ('tab', 'collapse')
        }),
        (_("🏆 Optional Achievement"), {
            'fields': ('achievement',),
            'classes': ('tab', 'collapse')
        }),
    )


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(CustomModelAdmin):
    list_display = ['title', 'employee', 'document_type', 'is_verified', 'uploaded_at', 'file_preview']
    list_filter = ['document_type', 'is_verified', 'uploaded_at']
    search_fields = ['title', 'employee__name', 'employee__employee_id']
    readonly_fields = ['uploaded_at', 'created_at', 'updated_at', 'file_preview']
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'document_type', 'title', 'file'),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('description', 'is_verified', 'uploaded_by'),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def file_preview(self, obj):
        if obj.file:
            return f'<a href="{obj.file.url}" target="_blank">View File</a>'
        return "No file"
    file_preview.allow_tags = True
    file_preview.short_description = "File Preview"


@admin.register(Overtime)
class OvertimeAdmin(CustomModelAdmin):
    list_display = ('employee', 'date', 'start_time', 'end_time', 'hours', 'status', 'approved_by')
    list_filter = ('status', 'date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'reason')
    ordering = ('-date',)
    list_select_related = ('employee', 'approved_by')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'date', 'status', 'start_time', 'end_time', 'hours'),
            'classes': ('tab',)
        }),
        (_("📝 Reason"), {
            'fields': ('reason',),
            'classes': ('tab',)
        }),
        (_("👤 Approval"), {
            'fields': ('approved_by', 'approved_at', 'remarks'),
            'classes': ('tab', 'collapse')
        }),
    )
    
    actions = ['approve_overtime', 'reject_overtime']
    
    def approve_overtime(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='approved', approved_by=request.user, approved_at=timezone.now())
        self.message_user(request, f'{updated} overtime requests approved.')
    approve_overtime.short_description = _("Approve selected overtime requests")
    
    def reject_overtime(self, request, queryset):
        updated = queryset.update(status='rejected', approved_by=request.user)
        self.message_user(request, f'{updated} overtime requests rejected.')
    reject_overtime.short_description = _("Reject selected overtime requests")


@admin.register(Resignation)
class ResignationAdmin(CustomModelAdmin):
    list_display = ('employee', 'resignation_date', 'last_working_date', 'status', 'approved_by')
    list_filter = ('status', 'resignation_date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'reason')
    ordering = ('-resignation_date',)
    list_select_related = ('employee', 'approved_by')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'resignation_date', 'last_working_date', 'status'),
            'classes': ('tab',)
        }),
        (_("📝 Reason"), {
            'fields': ('reason',),
            'classes': ('tab',)
        }),
        (_("👤 Approval"), {
            'fields': ('approved_by', 'approved_at', 'remarks'),
            'classes': ('tab', 'collapse')
        }),
    )
    
    actions = ['accept_resignation', 'reject_resignation']
    
    def accept_resignation(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='accepted', approved_by=request.user, approved_at=timezone.now())
        self.message_user(request, f'{updated} resignations accepted.')
    accept_resignation.short_description = _("Accept selected resignations")
    
    def reject_resignation(self, request, queryset):
        updated = queryset.update(status='rejected', approved_by=request.user)
        self.message_user(request, f'{updated} resignations rejected.')
    reject_resignation.short_description = _("Reject selected resignations")


@admin.register(Clearance)
class ClearanceAdmin(CustomModelAdmin):
    list_display = (
        'employee', 'clearance_date', 'status', 'hr_status', 'finance_status', 
        'it_status', 'admin_status', 'final_settlement_amount'
    )
    list_filter = ('status', 'hr_clearance', 'finance_clearance', 'it_clearance', 'admin_clearance', 'clearance_date')
    search_fields = ('employee__name', 'employee__employee_id')
    ordering = ('-clearance_date',)
    list_select_related = ('employee', 'resignation', 'cleared_by')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'clearance_date', 'status'),
            'classes': ('tab',)
        }),
        (_("🏢 Department Clearances"), {
            'fields': ('hr_clearance', 'finance_clearance', 'it_clearance', 'admin_clearance'),
            'classes': ('tab',)
        }),
        (_("💰 Settlement"), {
            'fields': ('final_settlement_amount',),
            'classes': ('tab',)
        }),
        (_("📝 Optional Fields"), {
            'fields': ('resignation', 'remarks', 'cleared_by'),
            'classes': ('tab', 'collapse')
        }),
    )
    
    def hr_status(self, obj):
        return self._status_icon(obj.hr_clearance)
    hr_status.short_description = _("HR")
    
    def finance_status(self, obj):
        return self._status_icon(obj.finance_clearance)
    finance_status.short_description = _("Finance")
    
    def it_status(self, obj):
        return self._status_icon(obj.it_clearance)
    it_status.short_description = _("IT")
    
    def admin_status(self, obj):
        return self._status_icon(obj.admin_clearance)
    admin_status.short_description = _("Admin")
    
    def _status_icon(self, status):
        if status:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')


@admin.register(Complaint)
class ComplaintAdmin(CustomModelAdmin):
    list_display = ('employee', 'title', 'priority', 'status', 'submitted_date', 'assigned_to', 'resolved_date')
    list_filter = ('status', 'priority', 'submitted_date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'title', 'description')
    ordering = ('-submitted_date',)
    list_select_related = ('employee', 'assigned_to')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'title', 'priority', 'status'),
            'classes': ('tab',)
        }),
        (_("📝 Description"), {
            'fields': ('description',),
            'classes': ('tab',)
        }),
        (_("👤 Assignment"), {
            'fields': ('assigned_to',),
            'classes': ('tab', 'collapse')
        }),
        (_("✅ Resolution"), {
            'fields': ('resolution', 'resolved_date', 'remarks'),
            'classes': ('tab', 'collapse')
        }),
    )
    
    actions = ['mark_as_under_review', 'mark_as_resolved']
    
    def mark_as_under_review(self, request, queryset):
        updated = queryset.update(status='under_review')
        self.message_user(request, f'{updated} complaints marked as under review.')
    mark_as_under_review.short_description = _("Mark as under review")
    
    def mark_as_resolved(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='resolved', resolved_date=timezone.now().date())
        self.message_user(request, f'{updated} complaints marked as resolved.')
    mark_as_resolved.short_description = _("Mark as resolved")