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

from .models import (
    Department, Designation, Shift, Employee,
    EmployeeSeparation, Roster, RosterAssignment, RosterDay,
    Holiday, LeaveType, LeaveBalance, LeaveApplication,
    ZkDevice, AttendanceLog, Attendance,    Notice, Recruitment, JobApplication, Training, TrainingEnrollment,
    Performance, PerformanceGoal, EmployeeDocument, Overtime,
    Resignation, Clearance, Complaint
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
        (_("🏢 Organization"), {
            'fields': (
                'company',
                'department',
                'designation',
                'default_shift',
                'employee_id',
                'zkteco_id',
                'joining_date',
                'is_active',
            ),
            'classes': ('tab', 'col2'),
        }),
        (_("👤 Personal Info"), {
            'fields': (
                'user',
                'name',
                'first_name', 
                'last_name',
                'contact_number',
                'date_of_birth',
                'marital_status',
                'nid',
            ),
            'classes': ('tab', 'col2'),
        }),
        (_("💰 Salary Structure"), {
            'fields': (
                'base_salary',
                'per_hour_rate',
                'expected_working_hours',
                'overtime_rate',
                'overtime_grace_minutes',
            ),
            'classes': ('tab', 'col2'),
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
            'classes': ('tab', 'col2'),
        }),
        (_("📉 Deductions"), {
            'fields': (
                'provident_fund',
                'tax_deduction',
                'loan_deduction',
            ),
            'classes': ('tab', 'col2'),
        }),
        (_("🏦 Banking"), {
            'fields': (
                'bank_account_no',
                'payment_method',
            ),
            'classes': ('tab', 'col2'),
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'department', 'designation', 'default_shift', 'user'
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
                name='attendance_zkdevice_import_users_preview',
            ),
            path(
                'import-users-execute/',
                self.admin_site.admin_view(self.import_users_execute_view),
                name='attendance_zkdevice_import_users_execute',
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
        
        # Prepare device list for testing
        device_list = []
        for device in queryset:
            device_list.append({
                'name': device.name,
                'ip': device.ip_address,
                'port': device.port,
                'password': device.password or 0,
            })
        
        # Test connections
        results = device_manager.test_multiple_connections(device_list, max_workers=5)
        
        # Process results and update devices
        success_count = 0
        failed_count = 0
        
        for device in queryset:
            result = results.get(device.ip_address, {})
            
            if result.get('success'):
                success_count += 1
                device.last_synced = timezone.now()
                device.save(update_fields=['last_synced'])
                
                # Show device info
                info = result.get('info', {})
                self.message_user(
                    request,
                    f"Connected: {device.name} ({device.ip_address}) | "
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
                    f"Failed: {device.name} ({device.ip_address}) - {error}",
                    messages.ERROR
                )
        
        # Disconnect all after testing
        device_manager.disconnect_all()
        
        # Summary message
        summary_level = messages.SUCCESS if failed_count == 0 else messages.WARNING
        self.message_user(
            request,
            f"Connection test completed: {success_count} successful, {failed_count} failed",
            summary_level
        )
    
    test_device_connection.short_description = _("1. Test Device Connection")
    
    def import_users_from_devices(self, request, queryset):
        """Import users from selected devices with preview"""
        # Store selected device IDs in session
        device_ids = list(queryset.values_list('id', flat=True))
        request.session['import_device_ids'] = device_ids
        
        # Redirect to preview page
        return HttpResponseRedirect(
            reverse('admin:attendance_zkdevice_import_users_preview')
        )
    
    import_users_from_devices.short_description = _("2. Import Users from Devices")
    
# In your admin.py, temporarily add this to import_users_preview_view:
    def import_users_preview_view(self, request):
        device_ids = request.session.get('import_device_ids', [])
        
        if not device_ids:
            self.message_user(request, "No devices selected", messages.ERROR)
            return HttpResponseRedirect(reverse('admin:hr_payroll_zkdevice_changelist'))
        
        devices = ZkDevice.objects.filter(id__in=device_ids)
        
        # ADD THESE DEBUG LINES:
        import os
        from django.conf import settings
        template_path = 'admin/hr_payroll/zkdevice/import_users_preview.html'
        print(f"Looking for template: {template_path}")
        print(f"App dirs: {settings.TEMPLATES[0]['APP_DIRS']}")
        # END DEBUG LINES
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Import Users from ZKTeco Devices',
            'devices': devices,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }
        
        return TemplateResponse(
            request,
            template_path,
            context
        )
    
    def import_users_execute_view(self, request):
        """Execute user import via AJAX"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Invalid request method'}, status=400)
        
        device_ids = request.session.get('import_device_ids', [])
        
        if not device_ids:
            return JsonResponse({'error': 'No devices selected'}, status=400)
        
        try:
            devices = ZkDevice.objects.filter(id__in=device_ids)
            device_manager = ZKTecoDeviceManager()
            
            # Step 1: Fetch users from devices
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
            
            # Fetch users
            all_users_data, fetch_results = device_manager.get_multiple_users_data(
                device_list, max_workers=3
            )
            
            # Disconnect immediately after fetching
            device_manager.disconnect_all()
            
            # Step 2: Analyze users
            analysis = self._analyze_users(all_users_data, devices)
            
            # Step 3: Import users to database
            import_results = self._import_users_to_database(
                analysis['new_users'],
                analysis['existing_users'],
                device_map
            )
            
            # Step 4: Update device sync time
            devices.update(last_synced=timezone.now())
            
            # Prepare response
            response_data = {
                'success': True,
                'analysis': analysis,
                'import_results': import_results,
                'fetch_results': fetch_results,
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
        
        # Get existing employees
        existing_employees = Employee.objects.filter(
            company_id__in=company_ids
        ).values('zkteco_id', 'employee_id', 'name', 'company_id')
        
        existing_zkteco_ids = {emp['zkteco_id']: emp for emp in existing_employees}
        
        new_users = []
        existing_users = []
        duplicate_users = []
        
        seen_zkteco_ids = set()
        
        for user_data in users_data:
            zkteco_id = user_data['user_id']
            
            # Check for duplicates in fetched data
            if zkteco_id in seen_zkteco_ids:
                duplicate_users.append(user_data)
                continue
            
            seen_zkteco_ids.add(zkteco_id)
            
            # Check if exists in database
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
            # Import new users
            for user_data in new_users:
                try:
                    device_ip = user_data.get('device_ip')
                    device = device_map.get(device_ip)
                    
                    if not device:
                        error_count += 1
                        errors.append(f"Device not found for user {user_data['user_id']}")
                        continue
                    
                    # Create employee
                    employee = Employee.objects.create(
                        company=device.company,
                        employee_id=f"EMP-{user_data['user_id']}",
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
            
            # Optionally update existing users (name sync)
            for user_data in existing_users:
                try:
                    employee = Employee.objects.get(zkteco_id=user_data['user_id'])
                    
                    # Update name if different
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
            'errors': errors[:10],  # Limit to first 10 errors
        }
    
    def import_attendance_from_devices(self, request, queryset):
        """Import attendance logs from selected devices"""
        device_manager = ZKTecoDeviceManager()
        
        # Date range for import (last 30 days by default)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        # Prepare device list
        device_list = []
        device_map = {}
        for device in queryset:
            device_list.append({
                'name': device.name,
                'ip': device.ip_address,
                'port': device.port,
                'password': device.password or 0,
            })
            device_map[device.ip_address] = device
        
        self.message_user(
            request,
            f"Fetching attendance data from {start_date} to {end_date}...",
            messages.INFO
        )
        
        # Fetch attendance from all devices
        all_attendance_data, results = device_manager.get_multiple_attendance_data(
            device_list, start_date, end_date, max_workers=3
        )
        
        # Process results and import to database
        imported_count = 0
        skipped_count = 0
        error_count = 0
        missing_employees = set()
        
        with transaction.atomic():
            for attendance_record in all_attendance_data:
                try:
                    # Get device object
                    device_ip = attendance_record['device_ip']
                    device = device_map.get(device_ip)
                    
                    if not device:
                        skipped_count += 1
                        continue
                    
                    # Find employee by zkteco_id
                    zkteco_id = attendance_record['zkteco_id']
                    try:
                        employee = Employee.objects.get(
                            zkteco_id=zkteco_id,
                            company=device.company
                        )
                    except Employee.DoesNotExist:
                        missing_employees.add(zkteco_id)
                        skipped_count += 1
                        continue
                    
                    # Create or update attendance log
                    attendance_log, created = AttendanceLog.objects.get_or_create(
                        device=device,
                        employee=employee,
                        timestamp=attendance_record['timestamp'],
                        defaults={
                            'status_code': attendance_record.get('verify_type', 0),
                            'punch_type': str(attendance_record.get('punch_type', 0)),
                            'source_type': 'ZK',
                        }
                    )
                    
                    if created:
                        imported_count += 1
                    else:
                        skipped_count += 1
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error importing attendance: {str(e)}")
                    continue
        
        # Show import summary
        if imported_count > 0:
            self.message_user(
                request,
                f"Successfully imported {imported_count} new attendance records",
                messages.SUCCESS
            )
        
        if skipped_count > 0:
            self.message_user(
                request,
                f"Skipped {skipped_count} records (duplicates or missing employees)",
                messages.WARNING
            )
        
        if missing_employees:
            self.message_user(
                request,
                f"Missing employees (ZKTeco IDs): {', '.join(list(missing_employees)[:10])}{'...' if len(missing_employees) > 10 else ''}",
                messages.WARNING
            )
        
        if error_count > 0:
            self.message_user(
                request,
                f"Encountered {error_count} errors during import",
                messages.ERROR
            )
        
        # Show device-wise results
        for result in results:
            device_name = result['device']['name']
            if result['success']:
                self.message_user(
                    request,
                    f"{device_name}: Fetched {result['records_found']} records",
                    messages.SUCCESS
                )
            else:
                self.message_user(
                    request,
                    f"{device_name}: {result.get('error', 'Unknown error')}",
                    messages.ERROR
                )
        
        # Update last_synced for all devices
        queryset.update(last_synced=timezone.now())
        
        # Disconnect all
        device_manager.disconnect_all()
    
    import_attendance_from_devices.short_description = _("3. Import Attendance Logs (Last 30 Days)")


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
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('mobile-attendance/', 
                 self.admin_site.admin_view(self.mobile_attendance_view), 
                 name='mobile_attendance_admin'),
        ]
        return custom_urls + urls
    
    def mobile_attendance_view(self, request):
        """Admin mobile attendance view"""
        from django.utils import timezone
        from django.db.models import Count
        
        # Get stats for the admin view
        today = timezone.now().date()
        
        context = {
            'title': 'Mobile Attendance Admin',
            'subtitle': 'Manage mobile attendance tracking',
            'mobile_logs_count': AttendanceLog.objects.filter(source_type='MB').count(),
            'today_logs_count': AttendanceLog.objects.filter(
                source_type='MB', 
                timestamp__date=today
            ).count(),
            'active_locations_count': Location.objects.filter(is_active=True).count(),
            'opts': self.model._meta,
            **self.admin_site.each_context(request),
        }
        
        return render(request, 'admin/mobile_attendance_admin.html', context)



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


from .models import Location, UserLocation

from unfold.admin import TabularInline

class UserLocationInline(TabularInline):
    model = UserLocation
    extra = 1
    fields = ('user', 'is_primary')
    verbose_name = _("User Location Assignment")
    verbose_name_plural = _("User Location Assignments")

@admin.register(Location)
class LocationAdmin(ModelAdmin):
    list_display = (
        'name', 'address_short', 'latitude', 'longitude', 
        'radius', 'is_active', 'user_count', 'created_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'address')
    ordering = ('name',)
    
    # Add custom change form template
    change_form_template = 'admin/location_change_form.html'
    
    fieldsets = (
        (None, {
            'fields': ('name', 'address', 'is_active')
        }),
        (_("Geographic Coordinates"), {
            'fields': ('latitude', 'longitude', 'radius'),
            'description': _('Set coordinates manually or use the map below to select location')
        }),
    )
    
    class Media:
        css = {
            'all': ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',)
        }
        js = (
            'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
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
class UserLocationAdmin(ModelAdmin):
    list_display = (
        'user', 'location', 'is_primary', 'created_at'
    )
    list_filter = ('is_primary', 'location', 'created_at')
    search_fields = ('user__username', 'user__email', 'location__name')
    ordering = ('user__username', 'location__name')
    list_select_related = ('user', 'location')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'location', 'is_primary')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'location')
    

class MobileAttendanceAdmin:
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('mobile-attendance/', 
                 self.admin_site.admin_view(self.mobile_attendance_view), 
                 name='mobile_attendance_admin'),
        ]
        return custom_urls + urls
    
    def mobile_attendance_view(self, request):
        """Admin mobile attendance view"""
        from ..models import AttendanceLog, Location
        from django.utils import timezone
        from django.db.models import Count
        
        # Get stats for the admin view
        today = timezone.now().date()
        
        context = {
            'title': 'Mobile Attendance Admin',
            'subtitle': 'Manage mobile attendance tracking',
            'mobile_logs_count': AttendanceLog.objects.filter(source_type='MB').count(),
            'today_logs_count': AttendanceLog.objects.filter(
                source_type='MB', 
                timestamp__date=today
            ).count(),
            'active_locations_count': Location.objects.filter(is_active=True).count(),
            'opts': self.model._meta,
        }
        
        return render(request, 'admin/mobile_attendance_admin.html', context)

# Register the custom admin view
admin.site.register_view = lambda *args, **kwargs: None  # Placeholder


# admin.py

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline   # <-- Unfold
from .models import (
    PayrollCycle, PayrollRecord, PayrollAdjustment,
    PayrollPayment, PayrollTemplate
)

# ---------- PayrollCycle ----------
@admin.register(PayrollCycle)
class PayrollCycleAdmin(ModelAdmin):
    list_display = [
        'name', 'company', 'start_date', 'end_date', 'status',
        'total_employees', 'total_net_salary', 'generated_at'
    ]
    list_filter = ['status', 'company', 'cycle_type', 'start_date']
    search_fields = ['name', 'company__name']
    readonly_fields = [
        'total_gross_salary', 'total_deductions', 'total_net_salary',
        'total_overtime_amount', 'generated_at', 'approved_at'
    ]

    fieldsets = (
        ('মূল তথ্য', {
            'fields': ('company', 'name', 'cycle_type', 'status')
        }),
        ('সময়কাল', {
            'fields': ('start_date', 'end_date', 'payment_date')
        }),
        ('আর্থিক সারাংশ', {
            'fields': (
                'total_gross_salary', 'total_deductions',
                'total_net_salary', 'total_overtime_amount'
            )
        }),
        ('মেটাডেটা', {
            'fields': ('generated_at', 'generated_by', 'approved_at', 'approved_by', 'notes')
        }),
    )

    def total_employees(self, obj):
        return obj.total_employees
    total_employees.short_description = 'মোট কর্মচারী'


# ---------- PayrollRecord ----------
class PayrollAdjustmentInline(TabularInline):  # <-- Unfold TabularInline
    model = PayrollAdjustment
    extra = 0
    fields = ['adjustment_type', 'title', 'amount', 'description']
    readonly_fields = ['created_by', 'created_at']


@admin.register(PayrollRecord)
class PayrollRecordAdmin(ModelAdmin):
    list_display = [
        'employee', 'payroll_cycle', 'present_days', 'working_days',
        'gross_salary', 'net_salary', 'payment_status', 'payment_date'
    ]
    list_filter = ['payment_status', 'payroll_cycle', 'payment_method', 'payment_date']
    search_fields = ['employee__employee_id', 'employee__name', 'payroll_cycle__name']
    readonly_fields = [
        'total_allowances', 'total_deductions', 'gross_salary',
        'net_salary', 'overtime_amount', 'hourly_wage_amount'
    ]
    inlines = [PayrollAdjustmentInline]

    fieldsets = (
        ('মূল তথ্য', {
            'fields': ('payroll_cycle', 'employee')
        }),
        ('বেতন উপাদান', {
            'fields': (
                'basic_salary', 'house_rent_allowance', 'medical_allowance',
                'conveyance_allowance', 'food_allowance', 'attendance_bonus',
                'festival_bonus', 'other_allowances', 'total_allowances'
            )
        }),
        ('ওভারটাইম ও ঘণ্টাভিত্তিক', {
            'fields': (
                'overtime_hours', 'overtime_rate', 'overtime_amount',
                'working_hours', 'hourly_rate', 'hourly_wage_amount'
            )
        }),
        ('কর্তন', {
            'fields': (
                'provident_fund', 'tax_deduction', 'loan_deduction',
                'absence_deduction', 'other_deductions', 'total_deductions'
            )
        }),
        ('উপস্থিতি তথ্য', {
            'fields': (
                'working_days', 'present_days', 'absent_days', 'leave_days',
                'half_days', 'late_arrivals', 'early_departures'
            )
        }),
        ('মোট হিসাব', {
            'fields': ('gross_salary', 'net_salary')
        }),
        ('পেমেন্ট তথ্য', {
            'fields': (
                'payment_status', 'payment_method', 'payment_date',
                'payment_reference', 'bank_name', 'bank_account'
            )
        }),
        ('অতিরিক্ত', {
            'fields': ('remarks',)
        }),
    )

    actions = ['mark_as_paid', 'mark_as_pending', 'export_selected']

    def mark_as_paid(self, request, queryset):
        updated = queryset.update(payment_status='paid')
        self.message_user(request, f'{updated} টি রেকর্ড পরিশোধিত হিসেবে চিহ্নিত করা হয়েছে।')
    mark_as_paid.short_description = 'পরিশোধিত হিসেবে চিহ্নিত করুন'

    def mark_as_pending(self, request, queryset):
        updated = queryset.update(payment_status='pending')
        self.message_user(request, f'{updated} টি রেকর্ড বকেয়া হিসেবে চিহ্নিত করা হয়েছে।')
    mark_as_pending.short_description = 'বকেয়া হিসেবে চিহ্নিত করুন'


# ---------- PayrollAdjustment ----------
@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(ModelAdmin):
    list_display = ['title', 'payroll_record', 'adjustment_type', 'amount', 'created_by', 'created_at']
    list_filter = ['adjustment_type', 'created_at']
    search_fields = ['title', 'payroll_record__employee__name']
    readonly_fields = ['created_by', 'created_at']

    fieldsets = (
        ('মূল তথ্য', {
            'fields': ('payroll_record', 'adjustment_type', 'title', 'amount')
        }),
        ('বিস্তারিত', {
            'fields': ('description',)
        }),
        ('মেটাডেটা', {
            'fields': ('created_by', 'created_at')
        }),
    )


# ---------- PayrollPayment ----------
@admin.register(PayrollPayment)
class PayrollPaymentAdmin(ModelAdmin):
    list_display = ['payroll_record', 'amount', 'payment_date', 'payment_method', 'status', 'reference_number']
    list_filter = ['status', 'payment_method', 'payment_date']
    search_fields = ['payroll_record__employee__name', 'reference_number', 'transaction_id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('মূল তথ্য', {
            'fields': ('payroll_record', 'amount', 'payment_date', 'payment_method')
        }),
        ('রেফারেন্স', {
            'fields': ('reference_number', 'transaction_id')
        }),
        ('স্ট্যাটাস', {
            'fields': ('status', 'notes')
        }),
        ('প্রসেসিং', {
            'fields': ('processed_by', 'created_at', 'updated_at')
        }),
    )


# ---------- PayrollTemplate ----------
@admin.register(PayrollTemplate)
class PayrollTemplateAdmin(ModelAdmin):
    list_display = ['name', 'company', 'default_cycle_type', 'payment_day', 'is_active', 'created_at']
    list_filter = ['is_active', 'default_cycle_type', 'company']
    search_fields = ['name', 'company__name']

    fieldsets = (
        ('মূল তথ্য', {
            'fields': ('company', 'name', 'description', 'is_active')
        }),
        ('ডিফল্ট সেটিংস', {
            'fields': ('default_cycle_type', 'payment_day')
        }),
        ('স্বয়ংক্রিয় গণনা', {
            'fields': ('auto_calculate_overtime', 'auto_calculate_deductions', 'auto_calculate_bonuses')
        }),
        ('বোনাস নিয়ম', {
            'fields': ('perfect_attendance_bonus', 'minimum_attendance_for_bonus')
        }),
        ('কর্তন নিয়ম', {
            'fields': ('per_day_absence_deduction_rate', 'late_arrival_penalty')
        }),
    )

    actions = ['duplicate_template', 'activate_template', 'deactivate_template']

    def duplicate_template(self, request, queryset):
        count = 0
        for template in queryset:
            # make a shallow copy
            original_pk = template.pk
            template.pk = None
            template.name = f"{template.name} (কপি)"
            template.is_active = False
            template.save()
            count += 1
        self.message_user(request, f'{count} টি টেমপ্লেট কপি করা হয়েছে।')
    duplicate_template.short_description = 'টেমপ্লেট কপি করুন'

    def activate_template(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} টি টেমপ্লেট সক্রিয় করা হয়েছে।')
    activate_template.short_description = 'সক্রিয় করুন'

    def deactivate_template(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} টি টেমপ্লেট নিষ্ক্রিয় করা হয়েছে।')
    deactivate_template.short_description = 'নিষ্ক্রিয় করুন'



# ==================== NOTICE & ANNOUNCEMENTS ====================

@admin.register(Notice)
class NoticeAdmin(ModelAdmin):
    list_display = ('title', 'company', 'priority', 'published_date', 'expiry_date', 'is_active', 'created_at')
    list_filter = ('company', 'priority', 'is_active', 'published_date')
    search_fields = ('title', 'description', 'company__name')
    ordering = ('-published_date',)
    list_select_related = ('company', 'created_by')
    
    fieldsets = (
        (None, {
            'fields': ('company', 'title', 'priority', 'is_active')
        }),
        (_("Content"), {
            'fields': ('description',)
        }),
        (_("Dates"), {
            'fields': ('published_date', 'expiry_date')
        }),
        (_("Metadata"), {
            'fields': ('created_by',),
            'classes': ('collapse',)
        }),
    )


# ==================== RECRUITMENT ====================

class JobApplicationInline(TabularInline):
    model = JobApplication
    extra = 0
    fields = ('applicant_name', 'email', 'phone', 'status', 'applied_date')
    readonly_fields = ('applied_date',)
    can_delete = False


@admin.register(Recruitment)
class RecruitmentAdmin(ModelAdmin):
    list_display = ('job_title', 'company', 'department', 'designation', 'vacancies', 'status', 'posted_date', 'closing_date')
    list_filter = ('company', 'department', 'designation', 'status', 'posted_date')
    search_fields = ('job_title', 'company__name', 'department__name')
    ordering = ('-posted_date',)
    list_select_related = ('company', 'department', 'designation', 'created_by')
    inlines = [JobApplicationInline]
    
    fieldsets = (
        (_("Basic Information"), {
            'fields': ('company', 'department', 'designation', 'job_title', 'vacancies')
        }),
        (_("Job Details"), {
            'fields': ('job_description', 'requirements')
        }),
        (_("Status & Dates"), {
            'fields': ('status', 'posted_date', 'closing_date')
        }),
        (_("Metadata"), {
            'fields': ('created_by',),
            'classes': ('collapse',)
        }),
    )


@admin.register(JobApplication)
class JobApplicationAdmin(ModelAdmin):
    list_display = ('applicant_name', 'recruitment_title', 'email', 'phone', 'status', 'applied_date')
    list_filter = ('status', 'applied_date', 'recruitment__company')
    search_fields = ('applicant_name', 'email', 'phone', 'recruitment__job_title')
    ordering = ('-applied_date',)
    list_select_related = ('recruitment',)
    
    fieldsets = (
        (_("Recruitment"), {
            'fields': ('recruitment', 'status')
        }),
        (_("Applicant Information"), {
            'fields': ('applicant_name', 'email', 'phone')
        }),
        (_("Application Details"), {
            'fields': ('resume', 'cover_letter')
        }),
        (_("Notes"), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    def recruitment_title(self, obj):
        return obj.recruitment.job_title
    recruitment_title.short_description = _("Job Title")
    recruitment_title.admin_order_field = 'recruitment__job_title'


# ==================== TRAINING ====================

class TrainingEnrollmentInline(TabularInline):
    model = TrainingEnrollment
    extra = 1
    fields = ('employee', 'status', 'enrollment_date', 'completion_date', 'score')
    readonly_fields = ('enrollment_date',)


@admin.register(Training)
class TrainingAdmin(ModelAdmin):
    list_display = ('title', 'company', 'trainer', 'start_date', 'end_date', 'duration_hours', 'status', 'enrollment_count')
    list_filter = ('company', 'status', 'start_date')
    search_fields = ('title', 'trainer', 'company__name')
    ordering = ('-start_date',)
    list_select_related = ('company', 'created_by')
    inlines = [TrainingEnrollmentInline]
    
    fieldsets = (
        (_("Basic Information"), {
            'fields': ('company', 'title', 'trainer', 'status')
        }),
        (_("Training Details"), {
            'fields': ('description', 'duration_hours')
        }),
        (_("Schedule"), {
            'fields': ('start_date', 'end_date')
        }),
        (_("Metadata"), {
            'fields': ('created_by',),
            'classes': ('collapse',)
        }),
    )
    
    def enrollment_count(self, obj):
        return obj.enrollments.count()
    enrollment_count.short_description = _("Enrollments")


@admin.register(TrainingEnrollment)
class TrainingEnrollmentAdmin(ModelAdmin):
    list_display = ('employee', 'training', 'status', 'enrollment_date', 'completion_date', 'score')
    list_filter = ('status', 'enrollment_date', 'training__company')
    search_fields = ('employee__name', 'employee__employee_id', 'training__title')
    ordering = ('-enrollment_date',)
    list_select_related = ('employee', 'training')
    
    fieldsets = (
        (_("Enrollment Information"), {
            'fields': ('training', 'employee', 'status')
        }),
        (_("Progress"), {
            'fields': ('enrollment_date', 'completion_date', 'score')
        }),
        (_("Feedback"), {
            'fields': ('feedback',),
            'classes': ('collapse',)
        }),
    )


# ==================== PERFORMANCE ====================

class PerformanceGoalInline(TabularInline):
    model = PerformanceGoal
    extra = 1
    fields = ('goal_title', 'target_date', 'status', 'completion_date')


@admin.register(Performance)
class PerformanceAdmin(ModelAdmin):
    list_display = ('employee', 'review_period_display', 'overall_rating', 'status', 'reviewer', 'review_date')
    list_filter = ('status', 'overall_rating', 'review_period_start', 'review_period_end')
    search_fields = ('employee__name', 'employee__employee_id', 'reviewer__username')
    ordering = ('-review_period_end',)
    list_select_related = ('employee', 'reviewer')
    inlines = [PerformanceGoalInline]
    
    fieldsets = (
        (_("Review Information"), {
            'fields': ('employee', 'reviewer', 'status')
        }),
        (_("Review Period"), {
            'fields': ('review_period_start', 'review_period_end', 'review_date')
        }),
        (_("Rating & Feedback"), {
            'fields': ('overall_rating', 'strengths', 'weaknesses', 'comments')
        }),
    )
    
    def review_period_display(self, obj):
        return f"{obj.review_period_start} to {obj.review_period_end}"
    review_period_display.short_description = _("Review Period")


@admin.register(PerformanceGoal)
class PerformanceGoalAdmin(ModelAdmin):
    list_display = ('employee', 'goal_title', 'target_date', 'status', 'completion_date')
    list_filter = ('status', 'target_date', 'performance__employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'goal_title')
    ordering = ('-target_date',)
    list_select_related = ('employee', 'performance')
    
    fieldsets = (
        (_("Goal Information"), {
            'fields': ('performance', 'employee', 'goal_title', 'status')
        }),
        (_("Description"), {
            'fields': ('description',)
        }),
        (_("Timeline"), {
            'fields': ('target_date', 'completion_date')
        }),
        (_("Achievement"), {
            'fields': ('achievement',),
            'classes': ('collapse',)
        }),
    )


# ==================== DOCUMENTS ====================

@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(ModelAdmin):
    list_display = ['title', 'employee', 'document_type', 'is_verified', 'uploaded_at', 'file_preview']
    list_filter = ['document_type', 'is_verified', 'uploaded_at']
    search_fields = ['title', 'employee__name', 'employee__employee_id']
    readonly_fields = ['uploaded_at', 'created_at', 'updated_at', 'file_preview']
    
    def file_preview(self, obj):
        if obj.file:
            return f'<a href="{obj.file.url}" target="_blank">View File</a>'
        return "No file"
    file_preview.allow_tags = True
    file_preview.short_description = "File Preview"
    



# ==================== OVERTIME ====================

@admin.register(Overtime)
class OvertimeAdmin(ModelAdmin):
    list_display = ('employee', 'date', 'start_time', 'end_time', 'hours', 'status', 'approved_by')
    list_filter = ('status', 'date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'reason')
    ordering = ('-date',)
    list_select_related = ('employee', 'approved_by')
    
    fieldsets = (
        (_("Overtime Request"), {
            'fields': ('employee', 'date', 'status')
        }),
        (_("Time Details"), {
            'fields': ('start_time', 'end_time', 'hours')
        }),
        (_("Reason"), {
            'fields': ('reason',)
        }),
        (_("Approval"), {
            'fields': ('approved_by', 'approved_at', 'remarks'),
            'classes': ('collapse',)
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


# ==================== RESIGNATION ====================

@admin.register(Resignation)
class ResignationAdmin(ModelAdmin):
    list_display = ('employee', 'resignation_date', 'last_working_date', 'status', 'approved_by')
    list_filter = ('status', 'resignation_date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'reason')
    ordering = ('-resignation_date',)
    list_select_related = ('employee', 'approved_by')
    
    fieldsets = (
        (_("Resignation Information"), {
            'fields': ('employee', 'status')
        }),
        (_("Dates"), {
            'fields': ('resignation_date', 'last_working_date')
        }),
        (_("Reason"), {
            'fields': ('reason',)
        }),
        (_("Approval"), {
            'fields': ('approved_by', 'approved_at', 'remarks'),
            'classes': ('collapse',)
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


# ==================== CLEARANCE ====================

@admin.register(Clearance)
class ClearanceAdmin(ModelAdmin):
    list_display = (
        'employee', 'clearance_date', 'status', 'hr_status', 'finance_status', 
        'it_status', 'admin_status', 'final_settlement_amount'
    )
    list_filter = ('status', 'hr_clearance', 'finance_clearance', 'it_clearance', 'admin_clearance', 'clearance_date')
    search_fields = ('employee__name', 'employee__employee_id')
    ordering = ('-clearance_date',)
    list_select_related = ('employee', 'resignation', 'cleared_by')
    
    fieldsets = (
        (_("Clearance Information"), {
            'fields': ('employee', 'resignation', 'clearance_date', 'status')
        }),
        (_("Department Clearances"), {
            'fields': ('hr_clearance', 'finance_clearance', 'it_clearance', 'admin_clearance')
        }),
        (_("Settlement"), {
            'fields': ('final_settlement_amount',)
        }),
        (_("Additional Information"), {
            'fields': ('remarks', 'cleared_by'),
            'classes': ('collapse',)
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


# ==================== COMPLAINT ====================

@admin.register(Complaint)
class ComplaintAdmin(ModelAdmin):
    list_display = ('employee', 'title', 'priority', 'status', 'submitted_date', 'assigned_to', 'resolved_date')
    list_filter = ('status', 'priority', 'submitted_date', 'employee__company')
    search_fields = ('employee__name', 'employee__employee_id', 'title', 'description')
    ordering = ('-submitted_date',)
    list_select_related = ('employee', 'assigned_to')
    
    fieldsets = (
        (_("Complaint Information"), {
            'fields': ('employee', 'title', 'priority', 'status')
        }),
        (_("Description"), {
            'fields': ('description',)
        }),
        (_("Assignment"), {
            'fields': ('assigned_to',)
        }),
        (_("Resolution"), {
            'fields': ('resolution', 'resolved_date'),
            'classes': ('collapse',)
        }),
        (_("Additional Notes"), {
            'fields': ('remarks',),
            'classes': ('collapse',)
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
