# simple_attendance_generation_views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q, Min, Max
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.core.cache import cache

import json
import logging
import csv
from decimal import Decimal, InvalidOperation

from .models import (
    AttendanceLog, Employee, Attendance, 
    Department, AttendanceProcessorConfiguration
)
from .attendance_processor import EnhancedAttendanceProcessor
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
    """Simple attendance generation page using active configuration"""
    try:
        company = get_company_from_request(request)
        if not company:
            messages.error(request, "No company access found.")
            return redirect('/')
        
        # Get active configuration
        active_config = AttendanceProcessorConfiguration.get_active_config(company)
        
        if not active_config:
            messages.warning(request, "No active attendance configuration found. Please create one first.")
            return redirect('/')
        
        # Get basic statistics
        try:
            logs_count = AttendanceLog.objects.filter(employee__company=company).count()
            employees_count = Employee.objects.filter(company=company, is_active=True).count()
            attendance_count = Attendance.objects.filter(employee__company=company).count()
        except Exception:
            logs_count = employees_count = attendance_count = 0
        
        stats = {
            'total_logs': logs_count,
            'total_employees': employees_count,
            'total_attendance': attendance_count,
        }
        
        context = {
            'company': company,
            'config': active_config,
            'stats': stats,
            'today': timezone.now().date(),
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
    """Generate attendance preview using active configuration"""
    try:
        data = json.loads(request.body)
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
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid date format'})
        
        if end_date < start_date:
            return JsonResponse({'success': False, 'error': 'End date must be after start date'})
        
        # Check date range (max 31 days)
        if (end_date - start_date).days > 31:
            return JsonResponse({'success': False, 'error': 'Date range cannot exceed 31 days'})
        
        # Get active configuration
        active_config = AttendanceProcessorConfiguration.get_active_config(company)
        
        if not active_config:
            return JsonResponse({'success': False, 'error': 'No active attendance configuration found'})
        
        config_dict = active_config.get_config_dict()
        
        # Initialize processor with configuration
        try:
            processor = EnhancedAttendanceProcessor(config_dict)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Configuration error: {str(e)}'})
        
        # Get all active employees
        try:
            employees = list(Employee.objects.filter(
                company=company, is_active=True
            ).select_related('department', 'designation', 'default_shift'))
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error fetching employees: {str(e)}'})
        
        if not employees:
            return JsonResponse({'success': False, 'error': 'No active employees found'})
        
        # Process attendance using configuration
        try:
            attendance_records = processor.process_bulk_attendance(
                employees, start_date, end_date, company
            )
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Processing error: {str(e)}'})
        
        # Convert to preview format
        preview_data = []
        summary = {
            'total_records': 0,
            'present_count': 0,
            'absent_count': 0,
            'late_count': 0,
            'half_day_count': 0,
            'holiday_count': 0,
            'leave_count': 0,
            'total_working_hours': 0,
            'total_overtime_hours': 0,
            'total_overtime_amount': 0
        }
        
        for record in attendance_records:
            try:
                employee = record.get('employee')
                if not employee:
                    continue
                
                # Check existing record
                existing = Attendance.objects.filter(
                    employee=employee,
                    date=record.get('date')
                ).exists()
                
                # Calculate overtime amount
                overtime_hours = float(record.get('overtime_hours', 0))
                overtime_amount = 0.0
                if overtime_hours > 0:
                    try:
                        overtime_rate = employee.get_overtime_rate()
                        overtime_amount = overtime_hours * overtime_rate
                    except:
                        overtime_amount = overtime_hours * float(employee.per_hour_rate)
                
                preview_record = {
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'employee_code': employee.employee_id,
                    'department': employee.department.name if employee.department else 'N/A',
                    'date': record.get('date').isoformat(),
                    'check_in_time': record.get('in_time').strftime('%H:%M:%S') if record.get('in_time') else None,
                    'check_out_time': record.get('out_time').strftime('%H:%M:%S') if record.get('out_time') else None,
                    'working_hours': round(float(record.get('working_hours', 0)), 2),
                    'overtime_hours': round(overtime_hours, 2),
                    'overtime_amount': round(overtime_amount, 2),
                    'status': record.get('status', 'A'),
                    'shift_name': record.get('shift_name', 'Default'),
                    'action': 'update' if existing else 'create',
                    'existing_record': existing
                }
                
                preview_data.append(preview_record)
                
                # Update summary
                summary['total_records'] += 1
                status = record.get('status', 'A')
                
                if status == 'P':
                    summary['present_count'] += 1
                elif status == 'A':
                    summary['absent_count'] += 1
                elif status == 'LAT':
                    summary['late_count'] += 1
                elif status == 'HAL':
                    summary['half_day_count'] += 1
                elif status == 'H':
                    summary['holiday_count'] += 1
                elif status == 'L':
                    summary['leave_count'] += 1
                
                summary['total_working_hours'] += float(record.get('working_hours', 0))
                summary['total_overtime_hours'] += overtime_hours
                summary['total_overtime_amount'] += overtime_amount
                
            except Exception as e:
                logger.warning(f"Error processing record: {str(e)}")
                continue
        
        # Cache preview data
        cache_key = f"simple_preview_{request.user.id}_{company.id}"
        cache.set(cache_key, {
            'data': preview_data,
            'params': data,
            'timestamp': timezone.now().isoformat()
        }, 1800)  # 30 minutes
        
        return JsonResponse({
            'success': True,
            'preview_data': preview_data,
            'summary': summary,
            'config_name': active_config.name
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request format'})
    except Exception as e:
        logger.error(f"Error in preview: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def simple_generate_records(request):
    """Generate attendance records from cached preview data"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get cached preview data
        cache_key = f"simple_preview_{request.user.id}_{company.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'Preview data expired. Please generate preview again.'})
        
        preview_data = cached_data.get('data', [])
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data available'})
        
        # Generate records
        generated_count = 0
        updated_count = 0
        error_count = 0
        
        try:
            with transaction.atomic():
                for record in preview_data:
                    try:
                        employee = Employee.objects.get(id=record['employee_id'])
                        date_obj = datetime.strptime(record['date'], '%Y-%m-%d').date()
                        
                        # Parse times
                        check_in_time = None
                        check_out_time = None
                        
                        if record.get('check_in_time'):
                            check_in_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_in_time'], '%H:%M:%S').time()
                            )
                            check_in_time = timezone.make_aware(check_in_datetime)
                        
                        if record.get('check_out_time'):
                            check_out_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_out_time'], '%H:%M:%S').time()
                            )
                            check_out_time = timezone.make_aware(check_out_datetime)
                        
                        overtime_hours = Decimal(str(record.get('overtime_hours', 0)))
                        
                        # Create or update
                        attendance_data = {
                            'employee': employee,
                            'shift': employee.default_shift,
                            'date': date_obj,
                            'check_in_time': check_in_time,
                            'check_out_time': check_out_time,
                            'status': record.get('status', 'A'),
                            'overtime_hours': overtime_hours
                        }
                        
                        existing = Attendance.objects.filter(
                            employee=employee, date=date_obj
                        ).first()
                        
                        if existing:
                            for key, value in attendance_data.items():
                                if key != 'employee':
                                    setattr(existing, key, value)
                            existing.save()
                            updated_count += 1
                        else:
                            Attendance.objects.create(**attendance_data)
                            generated_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing record: {str(e)}")
                        
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Generation failed: {str(e)}'})
        
        # Clear cache
        cache.delete(cache_key)
        
        message = f'{generated_count} created, {updated_count} updated'
        if error_count > 0:
            message += f', {error_count} errors'
        
        return JsonResponse({
            'success': True,
            'generated_count': generated_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error generating records: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Generation failed: {str(e)}'})

@login_required
@require_http_methods(["POST"])
def simple_export_csv(request):
    """Export preview data to CSV"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        cache_key = f"simple_preview_{request.user.id}_{company.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'No preview data found'})
        
        preview_data = cached_data.get('data', [])
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data to export'})
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee Code', 'Employee Name', 'Department', 'Date',
            'Check In', 'Check Out', 'Working Hours', 'Overtime Hours',
            'Overtime Amount', 'Status', 'Shift', 'Action'
        ])
        
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
                record.get('shift_name', ''),
                record.get('action', '')
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Export failed'})