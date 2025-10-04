# simple_attendance_generation_views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.core.cache import cache
import json
import logging
import csv

from .models import (
    Employee, Attendance, AttendanceProcessorConfiguration,
    Shift, Holiday, LeaveApplication
)
from core.models import Company

logger = logging.getLogger(__name__)

def get_company_from_request(request):
    """Helper to get company"""
    try:
        company = Company.objects.first()
        return company
    except Exception as e:
        logger.error(f"Error getting company: {str(e)}")
        return None

@login_required
def simple_attendance_generation(request):
    """Simple attendance generation page"""
    try:
        company = get_company_from_request(request)
        if not company:
            messages.error(request, "No company access found.")
            return redirect('/')
        
        # Get active configuration
        active_config = AttendanceProcessorConfiguration.get_active_config(company)
        
        if not active_config:
            active_config = AttendanceProcessorConfiguration.objects.create(
                company=company,
                name="Default Configuration",
                is_active=True,
                created_by=request.user
            )
            messages.info(request, "Default configuration created successfully.")
        
        # Get statistics
        try:
            employees = Employee.objects.filter(company=company, is_active=True)
            employees_count = employees.count()
            
            today = timezone.now().date()
            first_day = today.replace(day=1)
            
            attendance_count = Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day
            ).count()
            
            present_count = Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day,
                status='P'
            ).count()
            
            absent_count = Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day,
                status='A'
            ).count()
            
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            employees_count = attendance_count = present_count = absent_count = 0
            employees = Employee.objects.none()
        
        # Get departments and shifts
        from .models import Department
        departments = Department.objects.filter(company=company)
        shifts = Shift.objects.filter(company=company)
        
        stats = {
            'total_employees': employees_count,
            'total_attendance': attendance_count,
            'present_count': present_count,
            'absent_count': absent_count,
        }
        
        context = {
            'company': company,
            'config': active_config,
            'stats': stats,
            'today': today,
            'all_employees': employees,
            'departments': departments,
            'shifts': shifts,
        }
        
        return render(request, 'zkteco/simple_attendance_generation.html', context)
        
    except Exception as e:
        logger.error(f"Error in simple_attendance_generation view: {str(e)}")
        messages.error(request, f"System error: {str(e)}")
        return redirect('/')

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def simple_attendance_preview(request):
    """Generate attendance preview"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        company = get_company_from_request(request)
        
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Validate dates
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        if not start_date_str or not end_date_str:
            return JsonResponse({'success': False, 'error': 'Start date and end date are required'})
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return JsonResponse({'success': False, 'error': f'Invalid date format: {str(e)}'})
        
        if end_date < start_date:
            return JsonResponse({'success': False, 'error': 'End date must be after start date'})
        
        # Get filter parameters
        employee_ids = data.get('employee_ids', [])
        department_ids = data.get('department_ids', [])
        
        # Get employees
        employees_query = Employee.objects.filter(company=company, is_active=True)
        
        if employee_ids:
            employees_query = employees_query.filter(id__in=employee_ids)
        
        if department_ids:
            employees_query = employees_query.filter(department_id__in=department_ids)
        
        employees = employees_query.select_related('department', 'default_shift')
        
        if not employees.exists():
            return JsonResponse({'success': False, 'error': 'No employees found matching the criteria'})
        
        # Generate preview data
        preview_data = []
        config = AttendanceProcessorConfiguration.get_active_config(company)
        weekend_days = config.weekend_days if config else [4, 5]  # Friday, Saturday
        
        # Get holidays
        holidays = set(Holiday.objects.filter(
            company=company,
            date__range=[start_date, end_date]
        ).values_list('date', flat=True))
        
        # Get all attendance records for the period for checking adjacent days
        all_attendance_records = {}
        for employee in employees:
            employee_attendance = Attendance.objects.filter(
                employee=employee,
                date__range=[start_date - timedelta(days=1), end_date + timedelta(days=1)]
            ).values('date', 'status')
            all_attendance_records[employee.id] = {
                record['date']: record['status'] for record in employee_attendance
            }
        
        current_date = start_date
        present_count = 0
        absent_count = 0
        late_count = 0
        total_overtime = 0
        
        while current_date <= end_date:
            is_weekend = current_date.weekday() in weekend_days
            is_holiday = current_date in holidays
            
            for employee in employees:
                # Check if attendance already exists
                existing = Attendance.objects.filter(
                    employee=employee,
                    date=current_date
                ).first()
                
                if existing and not data.get('regenerate_existing', False):
                    continue
                
                # Determine status
                if is_weekend or is_holiday:
                    # Check adjacent days for holiday/weekend eligibility
                    prev_day = current_date - timedelta(days=1)
                    next_day = current_date + timedelta(days=1)
                    
                    # Get status of previous and next day
                    prev_day_status = all_attendance_records.get(employee.id, {}).get(prev_day, None)
                    next_day_status = all_attendance_records.get(employee.id, {}).get(next_day, None)
                    
                    # If both adjacent days are absent, mark as absent
                    if prev_day_status == 'A' and next_day_status == 'A':
                        status = 'A'
                        check_in = check_out = None
                        working_hours = overtime_hours = 0
                        absent_count += 1
                    else:
                        # Otherwise, mark as weekend or holiday
                        if is_weekend:
                            status = 'W'
                        else:
                            status = 'H'
                        check_in = check_out = None
                        working_hours = overtime_hours = 0
                else:
                    # Check for leave
                    has_leave = LeaveApplication.objects.filter(
                        employee=employee,
                        start_date__lte=current_date,
                        end_date__gte=current_date,
                        status='A'
                    ).exists()
                    
                    if has_leave:
                        # Check adjacent days for leave eligibility
                        prev_day = current_date - timedelta(days=1)
                        next_day = current_date + timedelta(days=1)
                        
                        # Get status of previous and next day
                        prev_day_status = all_attendance_records.get(employee.id, {}).get(prev_day, None)
                        next_day_status = all_attendance_records.get(employee.id, {}).get(next_day, None)
                        
                        # If both adjacent days are absent, mark as absent instead of leave
                        if prev_day_status == 'A' and next_day_status == 'A':
                            status = 'A'
                            check_in = check_out = None
                            working_hours = overtime_hours = 0
                            absent_count += 1
                        else:
                            status = 'L'
                            check_in = check_out = None
                            working_hours = overtime_hours = 0
                    else:
                        # Get from attendance logs
                        from .models import AttendanceLog
                        logs = AttendanceLog.objects.filter(
                            employee=employee,
                            timestamp__date=current_date
                        ).order_by('timestamp')
                        
                        if logs.exists():
                            check_in = logs.first().timestamp
                            check_out = logs.last().timestamp if logs.count() > 1 else None
                            
                            if check_out:
                                delta = check_out - check_in
                                working_hours = round(delta.total_seconds() / 3600, 2)
                                
                                # Calculate overtime
                                expected_hours = employee.expected_working_hours
                                if working_hours > expected_hours:
                                    overtime_hours = round(working_hours - expected_hours, 2)
                                    total_overtime += overtime_hours
                                else:
                                    overtime_hours = 0
                                
                                status = 'P'
                                present_count += 1
                            else:
                                working_hours = overtime_hours = 0
                                status = 'A'
                                absent_count += 1
                        else:
                            status = 'A'
                            check_in = check_out = None
                            working_hours = overtime_hours = 0
                            absent_count += 1
                
                shift_name = employee.default_shift.name if employee.default_shift else 'No Shift'
                
                overtime_amount = round(overtime_hours * float(employee.get_overtime_rate()), 2) if overtime_hours > 0 else 0
                
                preview_record = {
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'employee_code': employee.employee_id,
                    'department': employee.department.name if employee.department else 'General',
                    'date': current_date.isoformat(),
                    'check_in_time': check_in.strftime('%H:%M:%S') if check_in else None,
                    'check_out_time': check_out.strftime('%H:%M:%S') if check_out else None,
                    'working_hours': working_hours,
                    'overtime_hours': overtime_hours,
                    'overtime_amount': overtime_amount,
                    'status': status,
                    'shift_name': shift_name,
                }
                
                preview_data.append(preview_record)
            
            current_date += timedelta(days=1)
        
        # Calculate summary
        summary = {
            'total_records': len(preview_data),
            'present_count': present_count,
            'absent_count': absent_count,
            'late_count': late_count,
            'total_overtime_hours': round(total_overtime, 2),
            'total_overtime_amount': round(sum([r.get('overtime_amount', 0) for r in preview_data]), 2)
        }
        
        # Cache preview data
        cache_key = f"simple_preview_{request.user.id}"
        cache.set(cache_key, {
            'data': preview_data,
            'params': data,
            'timestamp': timezone.now().isoformat()
        }, 1800)  # 30 minutes
        
        return JsonResponse({
            'success': True,
            'preview_data': preview_data,
            'summary': summary,
            'message': f'Successfully generated {len(preview_data)} preview records'
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({'success': False, 'error': f'Invalid JSON format: {str(e)}'})
    except Exception as e:
        logger.error(f"Error in preview: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def simple_generate_records(request):
    """Generate attendance records"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        company = get_company_from_request(request)
        
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get cached preview data
        cache_key = f"simple_preview_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'Preview data expired. Please generate preview again.'})
        
        preview_data = cached_data.get('data', [])
        
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data available to generate'})
        
        generated_count = 0
        updated_count = 0
        error_count = 0
        
        with transaction.atomic():
            for record in preview_data:
                try:
                    employee = Employee.objects.get(id=record['employee_id'])
                    date_obj = datetime.strptime(record['date'], '%Y-%m-%d').date()
                    
                    # Parse times
                    check_in_time = None
                    check_out_time = None
                    
                    if record.get('check_in_time'):
                        check_in_time = datetime.strptime(
                            f"{record['date']} {record['check_in_time']}", 
                            '%Y-%m-%d %H:%M:%S'
                        )
                    
                    if record.get('check_out_time'):
                        check_out_time = datetime.strptime(
                            f"{record['date']} {record['check_out_time']}", 
                            '%Y-%m-%d %H:%M:%S'
                        )
                    
                    # Create or update attendance
                    attendance, created = Attendance.objects.update_or_create(
                        employee=employee,
                        date=date_obj,
                        defaults={
                            'check_in_time': check_in_time,
                            'check_out_time': check_out_time,
                            'status': record['status'],
                            'overtime_hours': record.get('overtime_hours', 0),
                            'shift': employee.default_shift,
                        }
                    )
                    
                    if created:
                        generated_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing record: {e}")
        
        # Clear cache after generation
        cache.delete(cache_key)
        
        message = f'Successfully generated {generated_count} and updated {updated_count} attendance records'
        if error_count > 0:
            message += f' with {error_count} errors'
        
        return JsonResponse({
            'success': True,
            'records_created': generated_count,
            'records_updated': updated_count,
            'error_count': error_count,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error in generate records: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Generation failed: {str(e)}'})

@login_required
@require_http_methods(["GET"])
def simple_export_csv(request):
    """Export preview data to CSV"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        cache_key = f"simple_preview_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'No preview data found. Please generate preview first.'})
        
        preview_data = cached_data.get('data', [])
        
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data to export'})
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Employee Code', 'Employee Name', 'Department', 'Date',
            'Check In', 'Check Out', 'Working Hours', 'Overtime Hours',
            'Overtime Amount', 'Status', 'Shift'
        ])
        
        # Write data
        for record in preview_data:
            writer.writerow([
                record.get('employee_code', ''),
                record.get('employee_name', ''),
                record.get('department', ''),
                record.get('date', ''),
                record.get('check_in_time', ''),
                record.get('check_out_time', ''),
                record.get('working_hours', 0),
                record.get('overtime_hours', 0),
                record.get('overtime_amount', 0),
                record.get('status', ''),
                record.get('shift_name', '')
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})