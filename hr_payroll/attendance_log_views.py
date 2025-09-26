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

from .models import ZkDevice, AttendanceLog, Employee, Attendance, Shift, Department, Designation, Holiday, LeaveApplication
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