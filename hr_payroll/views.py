from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Min, Max, Avg, Sum
from django.utils import timezone
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

import calendar

from .models import ZkDevice, AttendanceLog, Employee, Attendance, Shift, Department, Designation,Holiday,LeaveApplication
from .zkteco_device_manager import ZKTecoDeviceManager
from core.models import Company

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
    
    devices = ZkDevice.objects.filter(company=company).order_by('name')
    active_devices = devices.filter(is_active=True)
    
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
        'objects': devices,
        'total_devices': devices.count(),
        'active_devices': active_devices.count(),
        'inactive_devices': devices.filter(is_active=False).count(),
        'total_attendance_records': total_attendance_records,
        'device_stats': json.dumps(device_stats),
        'company': company,
    }
    return render(request, 'zkteco/device_list.html', context)

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
def fetch_attendance_data(request):
    """AJAX endpoint to fetch attendance data from selected devices (preview before import)"""
    try:
        data = json.loads(request.body)
        device_ids = data.get('device_ids', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
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
        
        # Convert string dates to date objects
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
        
        attendance_data, fetch_results = device_manager.get_multiple_attendance_data(
            device_list, start_date_obj, end_date_obj
        )
        
        # Process and format the data with duplicate checking
        formatted_data = []
        for record in attendance_data:
            # Find matching employee
            employee = Employee.objects.filter(
                Q(zkteco_id=record['zkteco_id']) | Q(employee_id=record['zkteco_id']),
                company=company
            ).first()
            
            # Check if already imported (duplicate check)
            is_imported = False
            if employee:
                is_imported = AttendanceLog.objects.filter(
                    employee=employee,
                    timestamp=record['timestamp'],
                    device__ip_address=record['device_ip']
                ).exists()
            
            formatted_record = {
                'device_name': record['device_name'],
                'device_ip': record['device_ip'],
                'zkteco_id': record['zkteco_id'],
                'employee_id': employee.employee_id if employee else record['zkteco_id'],
                'employee_name': employee.name if employee else 'Unknown Employee',
                'timestamp': record['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                'date': record['timestamp'].strftime('%Y-%m-%d'),
                'time': record['timestamp'].strftime('%H:%M:%S'),
                'punch_type': record.get('punch_type', 0),
                'verify_type': record.get('verify_type', 0),
                'source_type': record.get('source_type', 'device'),
                'is_imported': is_imported,
                'has_employee': bool(employee),
                'can_import': bool(employee) and not is_imported,
                'raw_timestamp': record['timestamp']
            }
            formatted_data.append(formatted_record)
        
        # Sort by timestamp (newest first)
        formatted_data.sort(key=lambda x: x['raw_timestamp'], reverse=True)
        
        # Store in session for import (only importable records)
        session_data = []
        for record in formatted_data:
            if record['can_import']:
                session_record = {
                    'zkteco_id': record['zkteco_id'],
                    'timestamp': record['raw_timestamp'].isoformat(),
                    'device_ip': record['device_ip'],
                    'punch_type': record['punch_type'],
                    'verify_type': record['verify_type'],
                    'source_type': record['source_type']
                }
                session_data.append(session_record)
        
        request.session['fetched_attendance_data'] = session_data
        
        return JsonResponse({
            'success': True,
            'data': formatted_data,
            'total_records': len(formatted_data),
            'new_records': len([r for r in formatted_data if r['can_import']]),
            'imported_records': len([r for r in formatted_data if r['is_imported']]),
            'missing_employee_records': len([r for r in formatted_data if not r['has_employee']]),
            'fetch_results': fetch_results,
            'message': f'Fetched {len(formatted_data)} attendance records'
        })
        
    except Exception as e:
        logger.error(f"Error fetching attendance data: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def import_attendance_data(request):
    """AJAX endpoint to import selected attendance data to database"""
    try:
        data = json.loads(request.body)
        selected_indices = data.get('selected_indices', [])
        import_all = data.get('import_all', False)
        
        fetched_data = request.session.get('fetched_attendance_data', [])
        
        if not fetched_data:
            return JsonResponse({'success': False, 'error': 'No data to import. Please fetch data first.'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        if import_all:
            records_to_import = fetched_data
        else:
            if not selected_indices:
                return JsonResponse({'success': False, 'error': 'No records selected for import'})
            records_to_import = [fetched_data[i] for i in selected_indices if i < len(fetched_data)]
        
        imported_count = 0
        duplicate_count = 0
        error_count = 0
        missing_employee_count = 0
        
        with transaction.atomic():
            for record in records_to_import:
                try:
                    # Find employee
                    employee = Employee.objects.filter(
                        Q(zkteco_id=record['zkteco_id']) | Q(employee_id=record['zkteco_id']),
                        company=company
                    ).first()
                    
                    if not employee:
                        missing_employee_count += 1
                        continue
                    
                    # Find device
                    device = ZkDevice.objects.filter(
                        ip_address=record['device_ip'], 
                        company=company
                    ).first()
                    
                    # Convert timestamp back to datetime
                    timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        timestamp = timezone.make_aware(timestamp)
                    
                    # Final duplicate check
                    existing = AttendanceLog.objects.filter(
                        employee=employee,
                        timestamp=timestamp,
                        device=device
                    ).exists()
                    
                    if existing:
                        duplicate_count += 1
                        continue
                    
                    # Create attendance log
                    AttendanceLog.objects.create(
                        employee=employee,
                        device=device,
                        timestamp=timestamp,
                        source_type=record.get('source_type', 'device')
                    )
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Error importing record {record}: {str(e)}")
                    error_count += 1
        
        # Clear session data after successful import
        if 'fetched_attendance_data' in request.session:
            del request.session['fetched_attendance_data']
        
        return JsonResponse({
            'success': True,
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'error_count': error_count,
            'missing_employee_count': missing_employee_count,
            'message': f'Import completed: {imported_count} imported, {duplicate_count} duplicates skipped, {missing_employee_count} missing employees, {error_count} errors.'
        })
        
    except Exception as e:
        logger.error(f"Error importing attendance data: {str(e)}")
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

@login_required
def attendance_logs(request):
    """Display imported attendance logs with enhanced filtering and pagination"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return render(request, 'zkteco/attendance_log_list.html', {
            'logs': [], 
            'devices': [], 
            'employees': [],
            'total_logs': 0
        })
    
    # Base queryset
    logs = AttendanceLog.objects.filter(
        employee__company=company
    ).select_related('employee', 'device').order_by('-timestamp')
    
    # Get filter parameters
    device_id = request.GET.get('device')
    employee_id = request.GET.get('employee')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search = request.GET.get('search')
    source_type = request.GET.get('source_type')
    date_range = request.GET.get('date_range')  # today, yesterday, this_week, last_week, this_month, last_month
    
    # Handle predefined date ranges
    today = timezone.now().date()
    if date_range:
        if date_range == 'today':
            start_date = end_date = today.isoformat()
        elif date_range == 'yesterday':
            yesterday = today - timedelta(days=1)
            start_date = end_date = yesterday.isoformat()
        elif date_range == 'this_week':
            start_of_week = today - timedelta(days=today.weekday())
            start_date = start_of_week.isoformat()
            end_date = today.isoformat()
        elif date_range == 'last_week':
            start_of_last_week = today - timedelta(days=today.weekday() + 7)
            end_of_last_week = start_of_last_week + timedelta(days=6)
            start_date = start_of_last_week.isoformat()
            end_date = end_of_last_week.isoformat()
        elif date_range == 'this_month':
            start_date = today.replace(day=1).isoformat()
            end_date = today.isoformat()
        elif date_range == 'last_month':
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            start_date = first_day_last_month.isoformat()
            end_date = last_day_last_month.isoformat()
    
    # Apply filters
    if device_id and device_id.isdigit():
        logs = logs.filter(device_id=int(device_id))
    
    if employee_id and employee_id.isdigit():
        logs = logs.filter(employee_id=int(employee_id))
    
    if start_date:
        try:
            parsed_start_date = parse_date(start_date)
            if parsed_start_date:
                logs = logs.filter(timestamp__date__gte=parsed_start_date)
        except ValueError:
            pass
    
    if end_date:
        try:
            parsed_end_date = parse_date(end_date)
            if parsed_end_date:
                logs = logs.filter(timestamp__date__lte=parsed_end_date)
        except ValueError:
            pass
    
    if search:
        logs = logs.filter(
            Q(employee__name__icontains=search) |
            Q(employee__employee_id__icontains=search) |
            Q(employee__zkteco_id__icontains=search)
        )
    
    if source_type:
        logs = logs.filter(source_type=source_type)
    
    # Get statistics for filtered results
    total_logs = logs.count()
    
    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get filter options
    devices = ZkDevice.objects.filter(company=company).order_by('name')
    employees = Employee.objects.filter(company=company, is_active=True).order_by('name')
    
    # Get date range statistics
    date_stats = logs.aggregate(
        earliest=Min('timestamp'),
        latest=Max('timestamp')
    )
    
    context = {
        'logs': page_obj,
        'devices': devices,
        'employees': employees,
        'total_logs': total_logs,
        'company': company,
        'date_stats': date_stats,
        # Current filter values
        'current_device': device_id,
        'current_employee': employee_id,
        'current_start_date': start_date,
        'current_end_date': end_date,
        'current_search': search,
        'current_source_type': source_type,
        'current_date_range': date_range,
    }
    return render(request, 'zkteco/attendance_log_list.html', context)

@login_required
def monthly_attendance_report(request):
    """
    Display a monthly attendance report for a selected employee.
    """
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return render(request, 'zkteco/monthly_attendance_report.html', {'error_message': 'No company access found'})

    employees = Employee.objects.filter(company=company, is_active=True).order_by('name')
    
    # Get selected employee, year, month, and holidays from request
    selected_employee_id = request.GET.get('employee')
    selected_year = request.GET.get('year', str(timezone.now().year))
    selected_month = request.GET.get('month', str(timezone.now().month))
    
    # Default weekly holidays to Friday, but allow multiple selections
    selected_holidays = request.GET.getlist('weekly_holidays', ['4']) # Friday is 4 (0=Mon, 6=Sun)
    weekly_holidays_int = [int(h) for h in selected_holidays]

    context = {
        'employees': employees,
        'selected_employee_id': selected_employee_id,
        'years': range(timezone.now().year, 2019, -1),
        'months': {i: calendar.month_name[i] for i in range(1, 13)},
        'selected_year': int(selected_year),
        'selected_month': int(selected_month),
        'weekly_holidays': selected_holidays,
        'company': company,
    }

    if selected_employee_id:
        try:
            employee = get_object_or_404(Employee, id=selected_employee_id, company=company)
            year = int(selected_year)
            month = int(selected_month)
            
            # Date range for the selected month
            start_date = date(year, month, 1)
            end_date = date(year, month, calendar.monthrange(year, month)[1])
            
            # Fetch relevant data in optimized queries
            attendance_records = Attendance.objects.filter(
                employee=employee, date__range=(start_date, end_date)
            ).order_by('date')
            
            holidays = Holiday.objects.filter(
                company=company, date__range=(start_date, end_date)
            ).values_list('date', flat=True)
            
            leave_applications = LeaveApplication.objects.filter(
                employee=employee,
                status='A',
                start_date__lte=end_date,
                end_date__gte=start_date
            )
            
            # Process data day by day
            report_data = []
            summary = defaultdict(int)
            total_work_hours = timedelta()
            
            for day in range(1, end_date.day + 1):
                current_date = date(year, month, day)
                day_data = {
                    'date': current_date,
                    'day_name': current_date.strftime("%A"),
                    'status': 'Absent',
                    'check_in': None,
                    'check_out': None,
                    'work_hours': '00:00'
                }

                # Check for Holiday
                if current_date in holidays:
                    day_data['status'] = 'Holiday'
                    summary['holidays'] += 1
                # Check for Weekly Off
                elif current_date.weekday() in weekly_holidays_int:
                    day_data['status'] = 'Weekly Off'
                    summary['weekly_offs'] += 1
                # Check for Leave
                elif any(app.start_date <= current_date <= app.end_date for app in leave_applications):
                    day_data['status'] = 'Leave'
                    summary['leave_days'] += 1
                else:
                    # Check for attendance record
                    record = next((r for r in attendance_records if r.date == current_date), None)
                    if record and record.status == 'P':
                        day_data.update({
                            'status': 'Present',
                            'check_in': record.check_in_time,
                            'check_out': record.check_out_time,
                        })
                        summary['present_days'] += 1
                        
                        if record.check_in_time and record.check_out_time:
                            work_duration = record.check_out_time - record.check_in_time
                            total_work_hours += work_duration
                            hours, remainder = divmod(work_duration.total_seconds(), 3600)
                            minutes, _ = divmod(remainder, 60)
                            day_data['work_hours'] = f"{int(hours):02d}:{int(minutes):02d}"

                        # Check for late arrival
                        shift = record.shift or employee.default_shift
                        if shift and record.check_in_time:
                            shift_start = datetime.combine(current_date, shift.start_time)
                            grace_period = shift_start + timedelta(minutes=shift.grace_time)
                            if record.check_in_time.time() > grace_period.time():
                                day_data['status'] = 'Late'
                                summary['late_days'] += 1
                    else:
                        summary['absent_days'] += 1

                report_data.append(day_data)

            # Finalize summary
            total_days_in_month = (end_date - start_date).days + 1
            summary['total_days'] = total_days_in_month
            total_hours, rem = divmod(total_work_hours.total_seconds(), 3600)
            total_minutes, _ = divmod(rem, 60)
            summary['total_work_hours'] = f"{int(total_hours):02d}:{int(total_minutes):02d}"

            context.update({
                'employee': employee,
                'report_data': report_data,
                'summary': dict(summary),
            })
        except (ValueError, Employee.DoesNotExist) as e:
            messages.error(request, f"Could not generate report: {e}")

    return render(request, 'zkteco/monthly_attendance_report.html', context)

    
@login_required
def attendance_generation(request):
    """Enhanced attendance generation page with comprehensive options and analytics"""
    company = get_company_from_request(request)
    if not company:
        messages.error(request, "No company access found.")
        return redirect('zkteco:device_list')
    
    # Get comprehensive statistics with optimized queries
    cache_key = f"attendance_gen_stats_{company.id}"
    stats = cache.get(cache_key)
    
    if not stats:
        # Raw logs statistics with date range
        logs_stats = AttendanceLog.objects.filter(
            employee__company=company
        ).aggregate(
            total_logs=Count('id'),
            earliest=Min('timestamp'),
            latest=Max('timestamp'),
            unique_employees=Count('employee', distinct=True),
            unique_devices=Count('device', distinct=True)
        )
        
        # Attendance records statistics
        attendance_stats = Attendance.objects.filter(
            employee__company=company
        ).aggregate(
            total_records=Count('id'),
            earliest=Min('date'),
            latest=Max('date'),
            present_days=Count('id', filter=Q(status='P')),
            absent_days=Count('id', filter=Q(status='A')),
            total_hours=Sum('overtime_hours'),
            avg_daily_hours=Avg('overtime_hours')
        )
        
        # Processing efficiency metrics
        if logs_stats['total_logs'] and attendance_stats['total_records']:
            processing_rate = (attendance_stats['total_records'] / logs_stats['total_logs']) * 100
        else:
            processing_rate = 0
        
        stats = {
            'logs_stats': logs_stats,
            'attendance_stats': attendance_stats,
            'processing_rate': round(processing_rate, 2)
        }
        
        cache.set(cache_key, stats, 300)  # Cache for 5 minutes
    
    # Get employees with attendance logs (optimized query)
    employees_with_logs = Employee.objects.filter(
        company=company,
        attendancelog__isnull=False,
        is_active=True
    ).distinct().select_related('department', 'designation').order_by('employee_id')
    
    # Get available resources
    departments = Department.objects.filter(company=company).order_by('name')
    shifts = Shift.objects.filter(company=company).order_by('name')
    devices = ZkDevice.objects.filter(company=company, is_active=True).order_by('name')
    
    # Get recent generation history
    recent_generations = get_recent_generation_history(company)
    
    # Check for data quality issues
    data_quality_issues = check_data_quality(company)
    
    context = {
        'company': company,
        'logs_stats': stats['logs_stats'],
        'attendance_stats': stats['attendance_stats'],
        'processing_rate': stats['processing_rate'],
        'employees_with_logs': employees_with_logs,
        'departments': departments,
        'shifts': shifts,
        'devices': devices,
        'recent_generations': recent_generations,
        'data_quality_issues': data_quality_issues,
        'today': timezone.now().date(),
        'max_date_range_days': getattr(settings, 'ATTENDANCE_MAX_DATE_RANGE', 90),
    }
    
    return render(request, 'zkteco/attendance_generation.html', context)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def attendance_generation_preview(request):
    """Enhanced preview with advanced analytics and data quality checks"""
    try:
        data = json.loads(request.body)
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Validate and extract parameters
        validation_result = validate_generation_parameters(data)
        if not validation_result['valid']:
            return JsonResponse({'success': False, 'error': validation_result['error']})
        
        params = validation_result['params']
        
        # Get processed attendance data with optimization
        processing_result = process_attendance_preview(company, params)
        
        if not processing_result['success']:
            return JsonResponse({'success': False, 'error': processing_result['error']})
        
        preview_data = processing_result['data']
        
        # Advanced analytics
        analytics = generate_preview_analytics(preview_data, params)
        
        # Data quality assessment
        quality_assessment = assess_preview_quality(preview_data, company, params)
        
        # Generate recommendations
        recommendations = generate_processing_recommendations(preview_data, quality_assessment)
        
        response_data = {
            'success': True,
            'preview_data': preview_data[:100],  # Limit for performance
            'summary': analytics['summary'],
            'analytics': analytics,
            'quality_assessment': quality_assessment,
            'recommendations': recommendations,
            'has_more': len(preview_data) > 100,
            'total_records': len(preview_data)
        }
        
        # Cache preview data for generation
        cache_key = f"preview_data_{request.user.id}_{company.id}"
        cache.set(cache_key, {
            'data': preview_data,
            'params': params,
            'timestamp': timezone.now().isoformat()
        }, 1800)  # 30 minutes
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in attendance generation preview: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def generate_attendance_records(request):
    """Enhanced generation with progress tracking and advanced processing"""
    try:
        data = json.loads(request.body)
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Check if using cached preview data
        use_cached_preview = data.get('use_cached_preview', False)
        
        if use_cached_preview:
            cache_key = f"preview_data_{request.user.id}_{company.id}"
            cached_data = cache.get(cache_key)
            
            if not cached_data:
                return JsonResponse({'success': False, 'error': 'Preview data expired. Please generate preview again.'})
            
            preview_data = cached_data['data']
            params = cached_data['params']
        else:
            # Validate parameters and process data
            validation_result = validate_generation_parameters(data)
            if not validation_result['valid']:
                return JsonResponse({'success': False, 'error': validation_result['error']})
            
            params = validation_result['params']
            processing_result = process_attendance_preview(company, params)
            
            if not processing_result['success']:
                return JsonResponse({'success': False, 'error': processing_result['error']})
            
            preview_data = processing_result['data']
        
        # Execute generation with transaction and progress tracking
        generation_result = execute_attendance_generation(company, preview_data, params, request.user)
        
        if generation_result['success']:
            # Clear cached preview data
            cache_key = f"preview_data_{request.user.id}_{company.id}"
            cache.delete(cache_key)
            
            # Log generation activity
            log_generation_activity(company, request.user, generation_result, params)
        
        return JsonResponse(generation_result)
        
    except Exception as e:
        logger.error(f"Error generating attendance records: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Generation failed: {str(e)}'})

def validate_generation_parameters(data):
    """Comprehensive parameter validation"""
    try:
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        if not start_date_str or not end_date_str:
            return {'valid': False, 'error': 'Start date and end date are required'}
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return {'valid': False, 'error': 'Invalid date format'}
        
        # Validate date range
        if end_date < start_date:
            return {'valid': False, 'error': 'End date must be after start date'}
        
        date_range_days = (end_date - start_date).days
        max_days = getattr(settings, 'ATTENDANCE_MAX_DATE_RANGE', 90)
        
        if date_range_days > max_days:
            return {'valid': False, 'error': f'Date range cannot exceed {max_days} days'}
        
        # Validate numeric parameters
        try:
            min_work_hours = float(data.get('min_work_hours', 0))
            break_time_minutes = int(data.get('break_time_minutes', 60))
            overtime_threshold_hours = float(data.get('overtime_threshold_hours', 8))
            
            if min_work_hours < 0 or min_work_hours > 24:
                return {'valid': False, 'error': 'Invalid minimum work hours'}
            
            if break_time_minutes < 0 or break_time_minutes > 480:
                return {'valid': False, 'error': 'Invalid break time'}
            
            if overtime_threshold_hours < 0 or overtime_threshold_hours > 24:
                return {'valid': False, 'error': 'Invalid overtime threshold'}
                
        except (ValueError, TypeError):
            return {'valid': False, 'error': 'Invalid numeric parameters'}
        
        # Validate strategy
        punch_matching_strategy = data.get('punch_matching_strategy', 'first_last')
        valid_strategies = ['first_last', 'first_two', 'smart_pairing']
        
        if punch_matching_strategy not in valid_strategies:
            return {'valid': False, 'error': 'Invalid punch matching strategy'}
        
        # Compile validated parameters
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'department_ids': data.get('departments', []),
            'employee_ids': data.get('employees', []),
            'device_ids': data.get('devices', []),
            'punch_matching_strategy': punch_matching_strategy,
            'min_work_hours': min_work_hours,
            'break_time_minutes': break_time_minutes,
            'overtime_threshold_hours': overtime_threshold_hours,
            'regenerate_existing': data.get('regenerate_existing', False),
            'consider_holidays': data.get('consider_holidays', True),
            'consider_leaves': data.get('consider_leaves', True),
            'auto_break_detection': data.get('auto_break_detection', False),
        }
        
        return {'valid': True, 'params': params}
        
    except Exception as e:
        return {'valid': False, 'error': f'Parameter validation failed: {str(e)}'}

def process_attendance_preview(company, params):
    """Advanced attendance processing with optimization"""
    try:
        # Build optimized employee query
        employees_query = Employee.objects.filter(
            company=company, 
            is_active=True
        ).select_related('department', 'designation', 'default_shift')
        
        if params['department_ids']:
            employees_query = employees_query.filter(department_id__in=params['department_ids'])
        
        if params['employee_ids']:
            employees_query = employees_query.filter(id__in=params['employee_ids'])
        
        employees = list(employees_query)
        
        if not employees:
            return {'success': False, 'error': 'No employees found matching the criteria'}
        
        # Build optimized logs query with prefetch
        logs_query = AttendanceLog.objects.filter(
            employee__company=company,
            employee__in=employees,
            timestamp__date__gte=params['start_date'],
            timestamp__date__lte=params['end_date']
        ).select_related('employee', 'device').order_by('employee', 'timestamp__date', 'timestamp')
        
        if params['device_ids']:
            logs_query = logs_query.filter(device_id__in=params['device_ids'])
        
        logs = list(logs_query)
        
        # Get holidays and leaves if needed
        holidays, employee_leaves = get_holidays_and_leaves(
            company, params['start_date'], params['end_date'], 
            employees, params['consider_holidays'], params['consider_leaves']
        )
        
        # Process logs into daily attendance records
        preview_data = []
        
        # Group logs by employee and date
        logs_by_employee_date = defaultdict(list)
        for log in logs:
            key = (log.employee.id, log.timestamp.date())
            logs_by_employee_date[key].append(log)
        
        # Generate attendance records for all employee-date combinations
        for employee in employees:
            current_date = params['start_date']
            while current_date <= params['end_date']:
                key = (employee.id, current_date)
                daily_logs = logs_by_employee_date.get(key, [])
                
                # Process daily attendance
                record = process_daily_attendance_enhanced(
                    employee, current_date, daily_logs,
                    params, holidays, employee_leaves.get(employee.id, set())
                )
                
                if record:
                    preview_data.append(record)
                
                current_date += timedelta(days=1)
        
        # Sort by date and employee
        preview_data.sort(key=lambda x: (x['date'], x['employee_name']))
        
        return {'success': True, 'data': preview_data}
        
    except Exception as e:
        logger.error(f"Error processing attendance preview: {str(e)}")
        return {'success': False, 'error': f'Processing failed: {str(e)}'}

def process_daily_attendance_enhanced(employee, date, logs, params, holidays, employee_leaves):
    """Enhanced daily attendance processing with smart algorithms"""
    try:
        # Check for existing record
        existing_attendance = Attendance.objects.filter(employee=employee, date=date).first()
        
        if existing_attendance and not params['regenerate_existing']:
            return None  # Skip existing records unless regenerating
        
        # Check special conditions
        is_holiday = date in holidays
        is_on_leave = date in employee_leaves
        is_weekend = date.weekday() >= 5  # Saturday = 5, Sunday = 6
        
        # Sort logs by timestamp
        logs = sorted(logs, key=lambda x: x.timestamp)
        
        # Apply punch matching strategy
        check_in_time, check_out_time = apply_punch_matching_strategy(
            logs, params['punch_matching_strategy'], params['auto_break_detection']
        )
        
        # Calculate work hours with break deduction
        work_hours = calculate_work_hours(
            check_in_time, check_out_time, params['break_time_minutes']
        )
        
        # Determine attendance status
        status = determine_attendance_status(
            work_hours, params['min_work_hours'], is_holiday, 
            is_on_leave, is_weekend, check_in_time
        )
        
        # Calculate overtime
        overtime_hours = calculate_overtime_hours(
            work_hours, params['overtime_threshold_hours'], status
        )
        
        # Determine action (create/update)
        action = 'update' if existing_attendance else 'create'
        
        return {
            'employee_id': employee.id,
            'employee_name': employee.name,
            'employee_code': employee.employee_id,
            'department': employee.department.name if employee.department else 'N/A',
            'date': date.isoformat(),
            'check_in_time': check_in_time.strftime('%H:%M:%S') if check_in_time else None,
            'check_out_time': check_out_time.strftime('%H:%M:%S') if check_out_time else None,
            'work_hours': round(work_hours, 2),
            'overtime_hours': round(overtime_hours, 2),
            'status': status,
            'punches_count': len(logs),
            'action': action,
            'existing_record': bool(existing_attendance),
            'is_holiday': is_holiday,
            'is_on_leave': is_on_leave,
            'is_weekend': is_weekend,
            'quality_score': calculate_record_quality_score(logs, check_in_time, check_out_time)
        }
        
    except Exception as e:
        logger.error(f"Error processing daily attendance for {employee.employee_id} on {date}: {str(e)}")
        return None

def apply_punch_matching_strategy(logs, strategy, auto_break_detection=False):
    """Enhanced punch matching with auto break detection"""
    if not logs:
        return None, None
    
    check_in_time = None
    check_out_time = potential_checkout or logs[-1].timestamp
    
    return check_in_time, check_out_time

def calculate_work_hours(check_in_time, check_out_time, break_time_minutes):
    """Calculate work hours with break deduction"""
    if not check_in_time or not check_out_time:
        return 0
    
    total_seconds = (check_out_time - check_in_time).total_seconds()
    total_hours = total_seconds / 3600
    
    # Deduct break time
    break_hours = break_time_minutes / 60
    work_hours = max(0, total_hours - break_hours)
    
    return work_hours

def determine_attendance_status(work_hours, min_work_hours, is_holiday, is_on_leave, is_weekend, check_in_time):
    """Determine attendance status based on multiple factors"""
    if is_holiday:
        return 'H'
    elif is_on_leave:
        return 'L'
    elif is_weekend:
        return 'W'
    elif work_hours >= min_work_hours:
        return 'P'
    elif check_in_time:
        return 'P'  # Present but insufficient hours
    else:
        return 'A'

def calculate_overtime_hours(work_hours, overtime_threshold, status):
    """Calculate overtime hours"""
    if status == 'P' and work_hours > overtime_threshold:
        return work_hours - overtime_threshold
    return 0

def calculate_record_quality_score(logs, check_in_time, check_out_time):
    """Calculate a quality score for the attendance record"""
    score = 0
    
    # Base score for having logs
    if logs:
        score += 30
    
    # Score for having both check-in and check-out
    if check_in_time and check_out_time:
        score += 40
    elif check_in_time:
        score += 20
    
    # Score based on number of punches (more punches can indicate better tracking)
    punch_score = min(len(logs) * 5, 20)
    score += punch_score
    
    # Score for reasonable time patterns
    if check_in_time and check_out_time:
        work_duration = (check_out_time - check_in_time).total_seconds() / 3600
        if 4 <= work_duration <= 12:  # Reasonable work duration
            score += 10
    
    return min(score, 100)

def get_holidays_and_leaves(company, start_date, end_date, employees, consider_holidays, consider_leaves):
    """Get holidays and employee leaves for the date range"""
    holidays = set()
    employee_leaves = defaultdict(set)
    
    if consider_holidays:
        company_holidays = Holiday.objects.filter(
            company=company,
            date__gte=start_date,
            date__lte=end_date
        ).values_list('date', flat=True)
        holidays = set(company_holidays)
    
    if consider_leaves:
        employee_ids = [emp.id for emp in employees]
        approved_leaves = LeaveApplication.objects.filter(
            employee__in=employee_ids,
            status='A',
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related('employee')
        
        for leave in approved_leaves:
            current_date = max(leave.start_date, start_date)
            end_leave_date = min(leave.end_date, end_date)
            
            while current_date <= end_leave_date:
                employee_leaves[leave.employee.id].add(current_date)
                current_date += timedelta(days=1)
    
    return holidays, employee_leaves

def generate_preview_analytics(preview_data, params):
    """Generate comprehensive analytics for preview data"""
    if not preview_data:
        return {'summary': {}, 'charts': []}
    
    # Basic summary
    total_records = len(preview_data)
    new_records = len([r for r in preview_data if r['action'] == 'create'])
    updated_records = len([r for r in preview_data if r['action'] == 'update'])
    
    # Status distribution
    status_counts = defaultdict(int)
    for record in preview_data:
        status_counts[record['status']] += 1
    
    # Department-wise distribution
    dept_stats = defaultdict(lambda: {'present': 0, 'absent': 0, 'total': 0})
    for record in preview_data:
        dept = record['department']
        dept_stats[dept]['total'] += 1
        if record['status'] == 'P':
            dept_stats[dept]['present'] += 1
        elif record['status'] == 'A':
            dept_stats[dept]['absent'] += 1
    
    # Work hours analysis
    work_hours = [r['work_hours'] for r in preview_data if r['work_hours'] > 0]
    avg_work_hours = sum(work_hours) / len(work_hours) if work_hours else 0
    
    # Quality analysis
    quality_scores = [r['quality_score'] for r in preview_data]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    summary = {
        'total_records': total_records,
        'new_records': new_records,
        'updated_records': updated_records,
        'employees_affected': len(set(r['employee_id'] for r in preview_data)),
        'date_range': f"{params['start_date']} to {params['end_date']}",
        'present_days': status_counts.get('P', 0),
        'absent_days': status_counts.get('A', 0),
        'holiday_days': status_counts.get('H', 0),
        'leave_days': status_counts.get('L', 0),
        'weekend_days': status_counts.get('W', 0),
        'total_work_hours': sum(r['work_hours'] for r in preview_data),
        'total_overtime_hours': sum(r['overtime_hours'] for r in preview_data),
        'avg_work_hours': round(avg_work_hours, 2),
        'avg_quality_score': round(avg_quality, 2)
    }
    
    return {
        'summary': summary,
        'status_distribution': dict(status_counts),
        'department_stats': dict(dept_stats),
        'quality_metrics': {
            'avg_score': avg_quality,
            'high_quality_records': len([r for r in preview_data if r['quality_score'] >= 80]),
            'low_quality_records': len([r for r in preview_data if r['quality_score'] < 50])
        }
    }

def assess_preview_quality(preview_data, company, params):
    """Assess data quality and identify potential issues"""
    issues = []
    warnings = []
    
    # Check for employees with no attendance data
    employees_with_no_data = []
    employee_record_counts = defaultdict(int)
    
    for record in preview_data:
        employee_record_counts[record['employee_id']] += 1
    
    expected_days = (params['end_date'] - params['start_date']).days + 1
    
    for employee_id, count in employee_record_counts.items():
        if count < expected_days * 0.5:  # Less than 50% coverage
            employee_name = next(r['employee_name'] for r in preview_data if r['employee_id'] == employee_id)
            warnings.append(f"Low attendance data coverage for {employee_name}")
    
    # Check for suspicious patterns
    suspicious_records = [r for r in preview_data if r['work_hours'] > 16]
    if suspicious_records:
        issues.append(f"{len(suspicious_records)} records show work hours > 16 hours")
    
    # Check quality scores
    low_quality_count = len([r for r in preview_data if r['quality_score'] < 50])
    if low_quality_count > 0:
        warnings.append(f"{low_quality_count} records have low quality scores")
    
    # Check for missing check-out times
    missing_checkout = len([r for r in preview_data if r['check_in_time'] and not r['check_out_time']])
    if missing_checkout > 0:
        warnings.append(f"{missing_checkout} records missing check-out times")
    
    return {
        'overall_score': calculate_overall_quality_score(preview_data),
        'issues': issues,
        'warnings': warnings,
        'total_issues': len(issues),
        'total_warnings': len(warnings)
    }

def calculate_overall_quality_score(preview_data):
    """Calculate overall data quality score"""
    if not preview_data:
        return 0
    
    scores = [r['quality_score'] for r in preview_data]
    return round(sum(scores) / len(scores), 2)

def generate_processing_recommendations(preview_data, quality_assessment):
    """Generate intelligent recommendations for processing"""
    recommendations = []
    
    if quality_assessment['overall_score'] < 70:
        recommendations.append({
            'type': 'warning',
            'title': 'Data Quality Concerns',
            'message': 'Consider reviewing raw attendance logs before proceeding with generation.',
            'priority': 'high'
        })
    
    # Check for high overtime
    high_overtime_records = [r for r in preview_data if r['overtime_hours'] > 4]
    if len(high_overtime_records) > len(preview_data) * 0.1:  # >10% have high overtime
        recommendations.append({
            'type': 'info',
            'title': 'High Overtime Detected',
            'message': 'Consider reviewing overtime threshold settings or break time calculations.',
            'priority': 'medium'
        })
    
    # Check for missing data patterns
    no_checkout_count = len([r for r in preview_data if r['check_in_time'] and not r['check_out_time']])
    if no_checkout_count > len(preview_data) * 0.2:  # >20% missing checkout
        recommendations.append({
            'type': 'warning',
            'title': 'Missing Check-out Times',
            'message': 'Consider using "Smart Pairing" strategy or reviewing device synchronization.',
            'priority': 'high'
        })
    
    return recommendations

def execute_attendance_generation(company, preview_data, params, user):
    """Execute the actual attendance generation with progress tracking"""
    try:
        generated_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        # Process in batches for better performance
        batch_size = 100
        total_batches = (len(preview_data) + batch_size - 1) // batch_size
        
        with transaction.atomic():
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(preview_data))
                batch_data = preview_data[start_idx:end_idx]
                
                for record in batch_data:
                    try:
                        employee = Employee.objects.get(id=record['employee_id'])
                        date_obj = datetime.strptime(record['date'], '%Y-%m-%d').date()
                        
                        # Parse times
                        check_in_time = None
                        check_out_time = None
                        
                        if record['check_in_time']:
                            check_in_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_in_time'], '%H:%M:%S').time()
                            )
                            check_in_time = timezone.make_aware(check_in_datetime)
                        
                        if record['check_out_time']:
                            check_out_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_out_time'], '%H:%M:%S').time()
                            )
                            check_out_time = timezone.make_aware(check_out_datetime)
                        
                        # Create or update attendance record
                        attendance_data = {
                            'employee': employee,
                            'shift': employee.default_shift,
                            'date': date_obj,
                            'check_in_time': check_in_time,
                            'check_out_time': check_out_time,
                            'status': record['status'],
                            'overtime_hours': Decimal(str(record['overtime_hours']))
                        }
                        
                        if record['action'] == 'update':
                            Attendance.objects.filter(
                                employee=employee, date=date_obj
                            ).update(**{k: v for k, v in attendance_data.items() if k != 'employee'})
                            updated_count += 1
                        else:
                            Attendance.objects.create(**attendance_data)
                            generated_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error processing record for employee {record.get('employee_code', 'unknown')}: {str(e)}")
                        error_count += 1
        
        # Clear relevant caches
        
        return {
            'success': True,
            'generated_count': generated_count,
            'updated_count': updated_count,
            'skipped_count': skipped_count,
            'error_count': error_count,
            'total_processed': generated_count + updated_count + skipped_count,
            'message': f'Processing completed: {generated_count} created, {updated_count} updated, {skipped_count} skipped, {error_count} errors.'
        }
        
    except Exception as e:
        logger.error(f"Error executing attendance generation: {str(e)}")
        return {
            'success': False,
            'error': f'Generation execution failed: {str(e)}',
            'generated_count': 0,
            'updated_count': 0,
            'skipped_count': 0,
            'error_count': 0
        }

def get_recent_generation_history(company, limit=5):
    """Get recent generation history for the company"""
    # This would typically come from a GenerationHistory model
    # For now, return empty list - implement based on your needs
    return []

def check_data_quality(company):
    """Check for common data quality issues"""
    issues = []
    
    # Check for employees without logs
    employees_without_logs = Employee.objects.filter(
        company=company,
        is_active=True,
        attendancelog__isnull=True
    ).count()
    
    if employees_without_logs > 0:
        issues.append(f"{employees_without_logs} active employees have no attendance logs")
    
    # Check for devices not syncing
    inactive_devices = ZkDevice.objects.filter(
        company=company,
        is_active=False
    ).count()
    
    if inactive_devices > 0:
        issues.append(f"{inactive_devices} devices are currently inactive")
    
    return issues

def log_generation_activity(company, user, result, params):
    """Log generation activity for audit purposes"""
    # Implement activity logging based on your audit requirements
    logger.info(f"Attendance generation completed by {user.username} for {company.name}: "
               f"{result['generated_count']} created, {result['updated_count']} updated")
# Export functionality
@login_required
@require_http_methods(["POST"])
def export_preview_data(request):
    """Export preview data to CSV"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get cached preview data
        cache_key = f"preview_data_{request.user.id}_{company.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'No preview data found'})
        
        preview_data = cached_data['data']
        
        # Create HTTP response with CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_preview_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee Code', 'Employee Name', 'Department', 'Date',
            'Check In', 'Check Out', 'Work Hours', 'Overtime Hours',
            'Status', 'Action', 'Quality Score'
        ])
        
        for record in preview_data:
            writer.writerow([
                record['employee_code'],
                record['employee_name'],
                record['department'],
                record['date'],
                record['check_in_time'] or '',
                record['check_out_time'] or '',
                record['work_hours'],
                record['overtime_hours'],
                record['status'],
                record['action'],
                record['quality_score']
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting preview data: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Export failed'})

def smart_punch_pairing(logs, auto_break_detection=False):
    """Intelligent punch pairing algorithm"""
    if not logs:
        return None, None
    
    if len(logs) == 1:
        return logs[0].timestamp, None
    
    # Simple case: 2 punches
    if len(logs) == 2:
        return logs[0].timestamp, logs[1].timestamp
    
    # Complex case: Multiple punches with potential breaks
    check_in_time = logs[0].timestamp
    potential_checkout = None
    
    # Find the last punch that's at least 4 hours after check-in
    for log in reversed(logs):
        time_diff = (log.timestamp - check_in_time).total_seconds() / 3600
        
        if time_diff >= 4:  # Minimum 4 hours for a valid work session
            potential_checkout = log.timestamp
            break
    
    # If auto break detection is enabled, analyze gaps
    if auto_break_detection and len(logs) > 2:
        # Look for large gaps that might indicate breaks
        gaps = []
        for i in range(len(logs) - 1):
            gap_minutes = (logs[i + 1].timestamp - logs[i].timestamp).total_seconds() / 60
            if gap_minutes > 30:  # Gaps longer than 30 minutes might be breaks
                gaps.append((gap_minutes, i))
        
        # If we detect significant breaks, use a more conservative approach
        if gaps:
            max_gap = max(gaps, key=lambda x: x[0])
            if max_gap[0] > 90:  # 90+ minute gap suggests lunch break
                # Find the punch after the longest break as potential check-out
                max_gap_index = max_gap[1]
                
                if max_gap_index + 1 < len(logs):
                    potential_checkout = logs[max_gap_index + 1].timestamp
    
    check_out_time = potential_checkout or logs[-1].timestamp
    
    return check_in_time, check_out_time

# Additional utility functions for enhanced functionality

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete_attendance_records(request):
    """Bulk delete attendance records for a date range"""
    try:
        data = json.loads(request.body)
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        employee_ids = data.get('employee_ids', [])
        
        if not start_date_str or not end_date_str:
            return JsonResponse({'success': False, 'error': 'Start date and end date are required'})
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Build query
        query = Q(
            employee__company=company,
            date__gte=start_date,
            date__lte=end_date
        )
        
        if employee_ids:
            query &= Q(employee_id__in=employee_ids)
        
        # Count records to be deleted
        records_to_delete = Attendance.objects.filter(query).count()
        
        # Perform deletion
        with transaction.atomic():
            deleted_count, _ = Attendance.objects.filter(query).delete()
        

        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} attendance records'
        })
        
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def get_attendance_analytics(request):
    """Get comprehensive attendance analytics for dashboard"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get date range from request
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        if not start_date_str or not end_date_str:
            # Default to last 30 days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Generate analytics
        analytics = {
            'overview': get_attendance_overview(company, start_date, end_date),
            'trends': get_attendance_trends(company, start_date, end_date),
            'department_stats': get_department_attendance_stats(company, start_date, end_date),
            'employee_performance': get_top_employee_performance(company, start_date, end_date),
            'quality_metrics': get_attendance_quality_metrics(company, start_date, end_date)
        }
        
        return JsonResponse({
            'success': True,
            'analytics': analytics,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting attendance analytics: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

def get_attendance_overview(company, start_date, end_date):
    """Get attendance overview statistics"""
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date
    )
    
    total_records = attendance_records.count()
    present_count = attendance_records.filter(status='P').count()
    absent_count = attendance_records.filter(status='A').count()
    leave_count = attendance_records.filter(status='L').count()
    holiday_count = attendance_records.filter(status='H').count()
    
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    return {
        'total_records': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'leave_count': leave_count,
        'holiday_count': holiday_count,
        'attendance_rate': round(attendance_rate, 2),
        'total_work_hours': float(attendance_records.aggregate(
            total=Sum('overtime_hours'))['total'] or 0)
    }

def get_attendance_trends(company, start_date, end_date):
    """Get daily attendance trends"""
    daily_stats = []
    current_date = start_date
    
    while current_date <= end_date:
        day_records = Attendance.objects.filter(
            employee__company=company,
            date=current_date
        )
        
        total = day_records.count()
        present = day_records.filter(status='P').count()
        
        daily_stats.append({
            'date': current_date.isoformat(),
            'total_employees': total,
            'present_count': present,
            'attendance_rate': (present / total * 100) if total > 0 else 0
        })
        
        current_date += timedelta(days=1)
    
    return daily_stats

def get_department_attendance_stats(company, start_date, end_date):
    """Get department-wise attendance statistics"""
    departments = Department.objects.filter(company=company)
    dept_stats = []
    
    for dept in departments:
        records = Attendance.objects.filter(
            employee__department=dept,
            date__gte=start_date,
            date__lte=end_date
        )
        
        total = records.count()
        present = records.filter(status='P').count()
        
        dept_stats.append({
            'department_name': dept.name,
            'total_records': total,
            'present_count': present,
            'attendance_rate': (present / total * 100) if total > 0 else 0,
            'avg_work_hours': float(records.aggregate(
                avg=Avg('overtime_hours'))['avg'] or 0)
        })
    
    return dept_stats

def get_top_employee_performance(company, start_date, end_date, limit=10):
    """Get top performing employees by attendance"""
    employee_stats = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date
    ).values(
        'employee__name',
        'employee__employee_id',
        'employee__department__name'
    ).annotate(
        total_days=Count('id'),
        present_days=Count('id', filter=Q(status='P')),
        total_hours=Sum('overtime_hours'),
        avg_hours=Avg('overtime_hours')
    ).order_by('-present_days', '-total_hours')[:limit]
    
    return list(employee_stats)

def get_attendance_quality_metrics(company, start_date, end_date):
    """Get attendance data quality metrics"""
    logs = AttendanceLog.objects.filter(
        employee__company=company,
        timestamp__date__gte=start_date,
        timestamp__date__lte=end_date
    )
    
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date
    )
    
    # Calculate metrics
    total_logs = logs.count()
    total_records = attendance_records.count()
    records_with_both_times = attendance_records.filter(
        check_in_time__isnull=False,
        check_out_time__isnull=False
    ).count()
    
    processing_rate = (total_records / total_logs * 100) if total_logs > 0 else 0
    completeness_rate = (records_with_both_times / total_records * 100) if total_records > 0 else 0
    
    return {
        'total_raw_logs': total_logs,
        'total_processed_records': total_records,
        'processing_rate': round(processing_rate, 2),
        'completeness_rate': round(completeness_rate, 2),
        'records_with_both_times': records_with_both_times,
        'incomplete_records': total_records - records_with_both_times
    }

@login_required
@csrf_exempt 
@require_http_methods(["POST"])
def validate_attendance_data(request):
    """Validate attendance data and identify issues"""
    try:
        data = json.loads(request.body)
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        if not start_date_str or not end_date_str:
            return JsonResponse({'success': False, 'error': 'Date range required'})
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        validation_results = perform_data_validation(company, start_date, end_date)
        
        return JsonResponse({
            'success': True,
            'validation_results': validation_results
        })
        
    except Exception as e:
        logger.error(f"Error validating attendance data: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

def perform_data_validation(company, start_date, end_date):
    """Perform comprehensive data validation"""
    issues = []
    warnings = []
    stats = {}
    
    # Check for missing attendance records
    employees = Employee.objects.filter(company=company, is_active=True)
    expected_days = (end_date - start_date).days + 1
    
    for employee in employees:
        actual_records = Attendance.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date
        ).count()
        
        if actual_records < expected_days * 0.8:  # Less than 80% coverage
            warnings.append({
                'type': 'missing_records',
                'employee': employee.name,
                'employee_id': employee.employee_id,
                'expected': expected_days,
                'actual': actual_records,
                'coverage_percent': round((actual_records / expected_days) * 100, 2)
            })
    
    # Check for suspicious work hours
    suspicious_records = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date
    ).extra(
        where=["TIMESTAMPDIFF(HOUR, check_in_time, check_out_time) > 16"]
    )
    
    if suspicious_records.exists():
        for record in suspicious_records:
            work_hours = (record.check_out_time - record.check_in_time).total_seconds() / 3600 if record.check_in_time and record.check_out_time else 0
            issues.append({
                'type': 'excessive_hours',
                'employee': record.employee.name,
                'date': record.date.isoformat(),
                'hours': round(work_hours, 2)
            })
    
    # Check for missing punch times
    missing_checkout = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date,
        check_in_time__isnull=False,
        check_out_time__isnull=True
    ).count()
    
    missing_checkin = Attendance.objects.filter(
        employee__company=company,
        date__gte=start_date,
        date__lte=end_date,
        check_in_time__isnull=True,
        check_out_time__isnull=False
    ).count()
    
    stats = {
        'total_validation_issues': len(issues),
        'total_warnings': len(warnings),
        'missing_checkout_count': missing_checkout,
        'missing_checkin_count': missing_checkin,
        'employees_checked': employees.count(),
        'date_range_days': expected_days
    }
    
    return {
        'issues': issues,
        'warnings': warnings,
        'stats': stats,
        'overall_health_score': calculate_data_health_score(issues, warnings, stats)
    }

def calculate_data_health_score(issues, warnings, stats):
    """Calculate overall data health score (0-100)"""
    base_score = 100
    
    # Deduct points for issues
    base_score -= len(issues) * 10  # 10 points per critical issue
    base_score -= len(warnings) * 2  # 2 points per warning
    
    # Additional deductions for missing data
    if stats['missing_checkout_count'] > 0:
        base_score -= min(stats['missing_checkout_count'] * 0.5, 20)
    
    if stats['missing_checkin_count'] > 0:
        base_score -= min(stats['missing_checkin_count'] * 0.5, 20)
    
    return max(0, min(100, base_score))

# Background task simulation (would typically use Celery in production)
def simulate_background_generation(company_id, params, user_id):
    """Simulate background generation process"""
    try:
        # This would be implemented with Celery or similar
        # For now, just log the operation
        logger.info(f"Background generation started for company {company_id} by user {user_id}")
        
        # Simulate processing
        import time
        time.sleep(2)
        
        # Update progress (would use Redis/database in production)
        logger.info(f"Background generation completed for company {company_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Background generation failed: {str(e)}")
        return False