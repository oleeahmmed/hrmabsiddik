from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Min, Max, Avg, Sum
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, date, timedelta
from django.utils.dateparse import parse_date, parse_datetime
from django.core.cache import cache
from django.conf import settings

import json
import logging
import csv
import threading
from collections import defaultdict
from decimal import Decimal

from ..models import ZkDevice, AttendanceLog, Employee, Attendance, Shift, Department, Designation, Holiday, LeaveApplication
from ..zkteco_device_manager import ZKTecoDeviceManager
from core.models import Company
from ..forms import ZkDeviceForm

logger = logging.getLogger(__name__)

# Initialize device manager
device_manager = ZKTecoDeviceManager()

def get_company_from_request(request):
    """Helper to get company - modify based on your auth system"""
    try:
        # Get first company or implement your company selection logic
        company = Company.objects.first()
        if company:
            return company
        return None
    except Exception as e:
        logger.error(f"Error getting company: {str(e)}")
        return None

# ==================== AUTH VIEWS ====================
@login_required
def home_dashboard(request):
    """Main dashboard/home page"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:login')
    
    today = timezone.now().date()
    
    # Get statistics
    total_devices = ZkDevice.objects.filter(company=company).count()
    active_devices = ZkDevice.objects.filter(company=company, is_active=True).count()
    inactive_devices = total_devices - active_devices
    
    active_employees = Employee.objects.filter(company=company, is_active=True)
    total_employees = active_employees.count()
    
    # --- আজকের অ্যাটেনডেন্স গণনার নতুন যুক্তি ---
    employees_on_leave_today_ids = LeaveApplication.objects.filter(
        employee__company=company,
        status='A',
        start_date__lte=today,
        end_date__gte=today
    ).values_list('employee_id', flat=True).distinct()
    today_leave = len(employees_on_leave_today_ids)

    employees_with_logs_today_ids = AttendanceLog.objects.filter(
        employee__company=company,
        timestamp__date=today
    ).values_list('employee_id', flat=True).distinct()
    today_present = len(employees_with_logs_today_ids)

    present_or_on_leave_count = today_present + today_leave
    today_absent = total_employees - present_or_on_leave_count
    if today_absent < 0:
        today_absent = 0

    attendance_rate = round((today_present / total_employees * 100) if total_employees > 0 else 0, 1)
    
    # --- নতুন ড্যাশবোর্ড উইজেট ডেটা ---

    # ১. আজকের লেট উপস্থিতি (Today's Late Comers)
    todays_late_comers = []
    first_check_ins = AttendanceLog.objects.filter(
        employee__in=active_employees,
        timestamp__date=today
    ).values('employee_id').annotate(first_in=Min('timestamp'))

    for check_in in first_check_ins:
        try:
            employee = active_employees.select_related('default_shift').get(id=check_in['employee_id'])
            if employee.default_shift:
                shift_start_time = employee.default_shift.start_time
                grace_minutes = employee.default_shift.grace_time or 0
                
                shift_start_datetime = timezone.make_aware(datetime.combine(today, shift_start_time))
                grace_deadline = shift_start_datetime + timedelta(minutes=grace_minutes)
                
                if check_in['first_in'] > grace_deadline:
                    todays_late_comers.append({
                        'employee': employee,
                        'check_in': check_in['first_in'],
                        'shift_start': shift_start_time
                    })
        except Employee.DoesNotExist:
            continue

    # ২. আজকের তাড়াতাড়ি প্রস্থানকারী (Today's Early Leavers)
    todays_early_leavers = []
    last_check_outs = AttendanceLog.objects.filter(
        employee__in=active_employees,
        timestamp__date=today
    ).values('employee_id').annotate(
        last_out=Max('timestamp'), 
        log_count=Count('id')
    ).filter(log_count__gt=1) # Ensure there's more than just a check-in

    for check_out in last_check_outs:
        try:
            employee = active_employees.select_related('default_shift').get(id=check_out['employee_id'])
            if employee.default_shift:
                shift_end_time = employee.default_shift.end_time
                shift_end_datetime = timezone.make_aware(datetime.combine(today, shift_end_time))

                if check_out['last_out'] < shift_end_datetime:
                    todays_early_leavers.append({
                        'employee': employee,
                        'check_out': check_out['last_out'],
                        'shift_end': shift_end_time
                    })
        except Employee.DoesNotExist:
            continue

    # ৩. অনুমোদনের জন্য অপেক্ষারত ছুটির আবেদন (Pending Leave Approvals)
    pending_leaves = LeaveApplication.objects.filter(
        employee__company=company, status='P'
    ).select_related('employee', 'leave_type').order_by('created_at')[:5]

    # ৪. জন্মদিনের শুভেচ্ছা (Birthday Alerts) - Assuming Employee model has 'date_of_birth' field
    # Note: Employee model needs a `date_of_birth = models.DateField(null=True, blank=True)` field.
    # upcoming_birthdays = []
    # if hasattr(Employee, 'date_of_birth'):
    #     today_month_day = (today.month, today.day)
    #     in_a_week_month_day = ((today + timedelta(days=7)).month, (today + timedelta(days=7)).day)
    #     upcoming_birthdays = active_employees.filter(
    #         date_of_birth__month=today.month, date_of_birth__day__gte=today.day
    #     ).or(
    #         active_employees.filter(date_of_birth__month=(today + timedelta(days=7)).month, date_of_birth__day__lte=(today + timedelta(days=7)).day)
    #     ).order_by('date_of_birth__month', 'date_of_birth__day')[:5]


    # --- বাকি পরিসংখ্যান ---
    monthly_leaves = LeaveApplication.objects.filter(
        employee__company=company,
        status='A',
        start_date__month=today.month,
        start_date__year=today.year
    ).count()
    
    upcoming_holidays = Holiday.objects.filter(
        company=company, date__gte=today
    ).order_by('date')[:5]
    
    total_shifts = Shift.objects.filter(company=company).count()
    recent_leaves = LeaveApplication.objects.filter(
        employee__company=company
    ).select_related('employee', 'leave_type').order_by('-created_at')[:5]
    
    departments = Department.objects.filter(company=company).annotate(
        employee_count=Count('employee', filter=Q(employee__is_active=True))
    )[:6]
    
    # Weekly attendance trend
    dates, present_counts, absent_counts = [], [], []
    for i in range(6, -1, -1):
        date_obj = today - timedelta(days=i)
        dates.append(date_obj.strftime('%a'))
        
        day_present_count = AttendanceLog.objects.filter(
            employee__company=company, timestamp__date=date_obj
        ).values('employee_id').distinct().count()
        
        day_leave_count = LeaveApplication.objects.filter(
            employee__company=company, status='A', start_date__lte=date_obj, end_date__gte=date_obj
        ).values('employee_id').distinct().count()
        
        day_absent_count = total_employees - day_present_count - day_leave_count
        present_counts.append(day_present_count)
        absent_counts.append(max(0, day_absent_count))

    dept_names = [dept.name for dept in departments]
    dept_counts = [dept.employee_count for dept in departments]
    
    total_logs = AttendanceLog.objects.filter(device__company=company).count()
    today_logs = AttendanceLog.objects.filter(
        device__company=company, timestamp__date=today
    ).count()
    
    recent_logs = AttendanceLog.objects.filter(
        device__company=company
    ).select_related('employee', 'device').order_by('-timestamp')[:10]
    
    system_health = round((active_devices / total_devices * 100) if total_employees > 0 else 100, 0)
    
    last_device_sync = ZkDevice.objects.filter(
        company=company, last_synced__isnull=False
    ).order_by('-last_synced').first()
    
    last_sync = "Never"
    if last_device_sync and last_device_sync.last_synced:
        time_diff = timezone.now() - last_device_sync.last_synced
        seconds = time_diff.total_seconds()
        if seconds < 60: last_sync = "Just now"
        elif seconds < 3600: last_sync = f"{int(seconds / 60)}m ago"
        else: last_sync = f"{int(seconds / 3600)}h ago"

    stats = {
        'total_devices': total_devices,
        'active_devices': active_devices,
        'total_employees': total_employees,
        'today_present': today_present,
        'today_absent': today_absent,
        'today_leave': today_leave,
        'attendance_rate': attendance_rate,
        'monthly_leaves': monthly_leaves,
        'total_shifts': total_shifts,
        'total_logs': total_logs,
        'today_logs': today_logs,
        'system_health': system_health,
        'last_sync': last_sync,
    }
    
    context = {
        'stats': stats,
        'recent_logs': recent_logs,
        'recent_leaves': recent_leaves,
        'upcoming_holidays': upcoming_holidays,
        'departments': departments,
        'today': today,
        'company': company,
        'attendance_dates': dates,
        'present_counts': present_counts,
        'absent_counts': absent_counts,
        'dept_names': dept_names,
        'dept_counts': dept_counts,
        # নতুন ডেটা কনটেক্সটে যোগ করা হলো
        'todays_late_comers': todays_late_comers,
        'todays_early_leavers': todays_early_leavers,
        'pending_leaves': pending_leaves,
        # 'upcoming_birthdays': upcoming_birthdays, # Uncomment when Employee model is updated
    }
    
    return render(request, 'zkteco/home_dashboard.html', context)

def login_view(request):
    """Custom login view"""
    if request.user.is_authenticated:
        return redirect('zkteco:home')  # Changed from device_list
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                next_url = request.GET.get('next', 'zkteco:home')  # Changed from device_list
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please provide both username and password.')
    
    return render(request, 'zkteco/auth/login.html')
@login_required
def logout_view(request):
    """Custom logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('zkteco:login')

# ==================== DEVICE CRUD VIEWS ====================

@login_required
def device_list(request):
    """Display list of ZKTeco devices with enhanced UI"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return render(request, 'zkteco/device_list.html', {
            'objects': [], 
            'total_devices': 0,
            'error_message': 'No company access found'
        })
    
    # Search functionality
    search_query = request.GET.get('search', '')
    devices = ZkDevice.objects.filter(company=company)
    
    if search_query:
        devices = devices.filter(
            Q(name__icontains=search_query) |
            Q(ip_address__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        devices = devices.filter(is_active=True)
    elif status_filter == 'inactive':
        devices = devices.filter(is_active=False)
    
    devices = devices.order_by('name')
    active_devices = devices.filter(is_active=True)
    
    # Pagination
    paginator = Paginator(devices, 10)  # Show 10 devices per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get attendance log counts for each device
    device_stats = {}
    total_attendance_records = 0
    
    for device in devices:
        attendance_count = AttendanceLog.objects.filter(device=device).count()
        device_stats[str(device.id)] = {
            'attendance_count': attendance_count,
            'last_synced': device.last_synced.isoformat() if device.last_synced else None,
            'is_active': device.is_active
        }
        total_attendance_records += attendance_count
    
    context = {
        'objects': page_obj,
        'total_devices': devices.count(),
        'active_devices': active_devices.count(),
        'inactive_devices': devices.filter(is_active=False).count(),
        'total_attendance_records': total_attendance_records,
        'device_stats': json.dumps(device_stats),
        'company': company,
        'search_query': search_query,
        'status_filter': status_filter,
        'page_obj': page_obj,
    }
    return render(request, 'zkteco/device_list.html', context)

@login_required
def device_add(request):
    """Add new ZKTeco device"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:device_list')
    
    if request.method == 'POST':
        form = ZkDeviceForm(request.POST)
        if form.is_valid():
            device = form.save(commit=False)
            device.company = company
            
            # Test connection before saving
            try:
                success, message = device_manager.test_connection(
                    device.ip_address, 
                    device.port, 
                    device.password or 0
                )
                
                if success:
                    device.is_active = True
                    device.last_synced = timezone.now()
                    device.save()
                    messages.success(request, f'Device "{device.name}" added successfully and connection verified!')
                    return redirect('zkteco:device_list')
                else:
                    device.is_active = False
                    device.save()
                    messages.warning(request, f'Device "{device.name}" added but connection failed: {message}')
                    return redirect('zkteco:device_list')
                    
            except Exception as e:
                device.is_active = False
                device.save()
                messages.warning(request, f'Device "{device.name}" added but connection test failed: {str(e)}')
                return redirect('zkteco:device_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ZkDeviceForm()
    
    context = {
        'form': form,
        'title': 'Add New Device',
        'submit_text': 'Add Device',
        'company': company,
    }
    return render(request, 'zkteco/device_form.html', context)

@login_required
def device_edit(request, device_id):
    """Edit existing ZKTeco device"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:device_list')
    
    device = get_object_or_404(ZkDevice, id=device_id, company=company)
    
    if request.method == 'POST':
        form = ZkDeviceForm(request.POST, instance=device)
        if form.is_valid():
            device = form.save(commit=False)
            
            # Test connection if IP, port, or password changed
            original_device = ZkDevice.objects.get(id=device_id)
            connection_changed = (
                original_device.ip_address != device.ip_address or
                original_device.port != device.port or
                original_device.password != device.password
            )
            
            if connection_changed:
                try:
                    success, message = device_manager.test_connection(
                        device.ip_address, 
                        device.port, 
                        device.password or 0
                    )
                    
                    if success:
                        device.is_active = True
                        device.last_synced = timezone.now()
                        messages.success(request, f'Device "{device.name}" updated successfully and connection verified!')
                    else:
                        device.is_active = False
                        messages.warning(request, f'Device "{device.name}" updated but connection failed: {message}')
                        
                except Exception as e:
                    device.is_active = False
                    messages.warning(request, f'Device "{device.name}" updated but connection test failed: {str(e)}')
            else:
                messages.success(request, f'Device "{device.name}" updated successfully!')
            
            device.save()
            return redirect('zkteco:device_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ZkDeviceForm(instance=device)
    
    context = {
        'form': form,
        'device': device,
        'title': f'Edit Device - {device.name}',
        'submit_text': 'Update Device',
        'company': company,
    }
    return render(request, 'zkteco/device_form.html', context)

@login_required
def device_detail(request, device_id):
    """View device details and statistics"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:device_list')
    
    device = get_object_or_404(ZkDevice, id=device_id, company=company)
    
    # Get device statistics
    total_logs = AttendanceLog.objects.filter(device=device).count()
    today_logs = AttendanceLog.objects.filter(
        device=device,
        timestamp__date=timezone.now().date()
    ).count()
    
    # Get recent logs
    recent_logs = AttendanceLog.objects.filter(device=device).order_by('-timestamp')[:10]
    
    # Get unique employees
    unique_employees = AttendanceLog.objects.filter(device=device).values('employee').distinct().count()
    
    context = {
        'device': device,
        'total_logs': total_logs,
        'today_logs': today_logs,
        'recent_logs': recent_logs,
        'unique_employees': unique_employees,
        'company': company,
    }
    return render(request, 'zkteco/device_detail.html', context)

@login_required
@require_http_methods(["POST"])
def device_delete(request, device_id):
    """Delete ZKTeco device"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:device_list')
    
    device = get_object_or_404(ZkDevice, id=device_id, company=company)
    
    # Check if device has attendance logs
    log_count = AttendanceLog.objects.filter(device=device).count()
    
    if log_count > 0:
        messages.warning(
            request, 
            f'Cannot delete device "{device.name}" as it has {log_count} attendance logs. '
            'Please delete or transfer the logs first.'
        )
    else:
        device_name = device.name
        device.delete()
        messages.success(request, f'Device "{device_name}" deleted successfully!')
    
    return redirect('zkteco:device_list')

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def device_toggle_status(request, device_id):
    """Toggle device active status"""
    company = get_company_from_request(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company access found'})
    
    device = get_object_or_404(ZkDevice, id=device_id, company=company)
    
    device.is_active = not device.is_active
    device.save()
    
    status_text = "activated" if device.is_active else "deactivated"
    
    return JsonResponse({
        'success': True,
        'is_active': device.is_active,
        'message': f'Device "{device.name}" {status_text} successfully!'
    })

# ==================== EXISTING AJAX ENDPOINTS ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def test_connections(request):
    """AJAX endpoint to test connections to multiple selected devices"""
    try:
        data = json.loads(request.body)
        device_ids = data.get('device_ids', [])
        
        if not device_ids:
            return JsonResponse({'success': False, 'error': 'No devices selected'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        devices = ZkDevice.objects.filter(id__in=device_ids, company=company)
        device_list = []
        
        for device in devices:
            device_data = {
                'ip': device.ip_address,
                'port': device.port,
                'id': device.id,
                'name': device.name,
                'password': device.password if device.password else 0
            }
            device_list.append(device_data)
        
        results = device_manager.test_multiple_connections(device_list)
        
        # Update device status in database
        response_data = []
        for device in devices:
            device_ip = device.ip_address
            if device_ip in results:
                test_result = results[device_ip]
                
                if test_result['success']:
                    device.is_active = True
                    device.last_synced = timezone.now()
                    status_message = "Connected successfully"
                    
                    info = test_result.get('info', {})
                    if info:
                        status_message += f" - Users: {info.get('user_count', 0)}, Records: {info.get('attendance_count', 0)}"
                else:
                    device.is_active = False
                    status_message = test_result.get('error', 'Connection failed')
                
                device.save()
                
                response_data.append({
                    'device_id': device.id,
                    'device_name': device.name,
                    'success': test_result['success'],
                    'message': status_message,
                    'info': test_result.get('info', {}) if test_result['success'] else None
                })
        
        return JsonResponse({
            'success': True,
            'results': response_data,
            'message': f'Tested {len(results)} devices'
        })
        
    except Exception as e:
        logger.error(f"Error testing connections: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def fetch_users_data(request):
    """AJAX endpoint to fetch users from selected devices (preview before import)"""
    try:
        data = json.loads(request.body)
        device_ids = data.get('device_ids', [])
        
        if not device_ids:
            return JsonResponse({'success': False, 'error': 'No devices selected'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        devices = ZkDevice.objects.filter(id__in=device_ids, company=company)
        device_list = []
        
        for device in devices:
            device_data = {
                'ip': device.ip_address,
                'port': device.port,
                'id': device.id,
                'name': device.name,
                'password': device.password if device.password else 0
            }
            device_list.append(device_data)
        
        all_users, results = device_manager.get_multiple_users_data(device_list)
        
        # Format users data for response and check duplicates
        formatted_users = []
        for user in all_users:
            existing_employee = Employee.objects.filter(
                Q(zkteco_id=user['user_id']) | Q(employee_id=user['user_id']),
                company=company
            ).first()
            
            formatted_users.append({
                'user_id': user['user_id'],
                'name': user['name'],
                'privilege': user.get('privilege', 0),
                'device_ip': user['device_ip'],
                'device_name': user['device_name'],
                'existing_employee': existing_employee.name if existing_employee else None,
                'existing_employee_id': existing_employee.employee_id if existing_employee else None,
                'is_existing': bool(existing_employee),
                'can_import': not bool(existing_employee)  # Can only import if not existing
            })
        
        # Store in session for import
        request.session['fetched_users_data'] = [
            {
                'user_id': user['user_id'],
                'name': user['name'],
                'privilege': user.get('privilege', 0),
                'device_ip': user['device_ip'],
                'device_name': user['device_name']
            }
            for user in formatted_users if user['can_import']
        ]
        
        return JsonResponse({
            'success': True,
            'users_data': formatted_users,
            'results': results,
            'total_users': len(all_users),
            'new_users': len([u for u in formatted_users if u['can_import']]),
            'existing_users': len([u for u in formatted_users if not u['can_import']]),
            'message': f'Retrieved {len(all_users)} users from {len(devices)} devices'
        })
        
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def import_users_data(request):
    """AJAX endpoint to import selected users as employees"""
    try:
        data = json.loads(request.body)
        selected_indices = data.get('selected_indices', [])
        import_all = data.get('import_all', False)
        
        fetched_data = request.session.get('fetched_users_data', [])
        
        if not fetched_data:
            return JsonResponse({'success': False, 'error': 'No data to import. Please fetch data first.'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get default department and designation
        default_dept = Department.objects.filter(company=company).first()
        default_designation = Designation.objects.filter(company=company).first()
        
        if not default_dept:
            return JsonResponse({'success': False, 'error': 'No department found. Please create at least one department first.'})
        
        if not default_designation:
            return JsonResponse({'success': False, 'error': 'No designation found. Please create at least one designation first.'})
        
        if import_all:
            users_to_import = fetched_data
        else:
            if not selected_indices:
                return JsonResponse({'success': False, 'error': 'No users selected for import'})
            users_to_import = [fetched_data[i] for i in selected_indices if i < len(fetched_data)]
        
        imported_count = 0
        duplicate_count = 0
        error_count = 0
        
        with transaction.atomic():
            for user in users_to_import:
                try:
                    # Check for duplicates again
                    existing = Employee.objects.filter(
                        Q(zkteco_id=user['user_id']) | Q(employee_id=user['user_id']),
                        company=company
                    ).exists()
                    
                    if existing:
                        duplicate_count += 1
                        continue
                    
                    # Create employee
                    Employee.objects.create(
                        company=company,
                        department=default_dept,
                        designation=default_designation,
                        employee_id=user['user_id'],
                        zkteco_id=user['user_id'],
                        name=user['name'] or f"User_{user['user_id']}",
                        expected_working_hours=8.00,
                        overtime_grace_minutes=15,
                        is_active=True
                    )
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Error importing user {user}: {str(e)}")
                    error_count += 1
        
        # Clear session data after successful import
        if 'fetched_users_data' in request.session:
            del request.session['fetched_users_data']
        
        return JsonResponse({
            'success': True,
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'error_count': error_count,
            'message': f'Import completed: {imported_count} imported, {duplicate_count} duplicates skipped, {error_count} errors.'
        })
        
    except Exception as e:
        logger.error(f"Error importing users: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def clear_device_data(request):
    """AJAX endpoint to clear attendance data from devices"""
    try:
        data = json.loads(request.body)
        device_ids = data.get('device_ids', [])
        
        if not device_ids:
            return JsonResponse({'success': False, 'error': 'No devices selected'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        devices = ZkDevice.objects.filter(id__in=device_ids, company=company)
        results = []
        
        for device in devices:
            try:
                success, message = device_manager.clear_attendance_data(device.ip_address)
                results.append({
                    'device_name': device.name,
                    'success': success,
                    'message': message
                })
            except Exception as e:
                results.append({
                    'device_name': device.name,
                    'success': False,
                    'message': str(e)
                })
        
        success_count = sum(1 for r in results if r['success'])
        
        return JsonResponse({
            'success': True,
            'results': results,
            'message': f'Data cleared from {success_count} out of {len(devices)} devices'
        })
        
    except Exception as e:
        logger.error(f"Error clearing device data: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})