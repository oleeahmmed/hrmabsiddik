# attendance_generation_views_enhanced.py - Fixed version with comprehensive error handling
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
from decimal import Decimal, InvalidOperation

from .models import (
    ZkDevice, AttendanceLog, Employee, Attendance, Shift, 
    Department, Designation, Holiday, LeaveApplication
)
from .attendance_processor import EnhancedAttendanceProcessor
from core.models import Company

logger = logging.getLogger(__name__)

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
def attendance_generation(request):
    """Enhanced attendance generation page with modal-based configuration"""
    try:
        company = get_company_from_request(request)
        if not company:
            messages.error(request, "No company access found.")
            return redirect('zkteco:device_list')
        
        # Get comprehensive statistics with error handling
        cache_key = f"attendance_gen_stats_{company.id}"
        stats = cache.get(cache_key)
        
        if not stats:
            try:
                # Raw logs statistics
                logs_stats = AttendanceLog.objects.filter(
                    employee__company=company
                ).aggregate(
                    total_logs=Count('id'),
                    earliest=Min('timestamp'),
                    latest=Max('timestamp'),
                    unique_employees=Count('employee', distinct=True),
                    unique_devices=Count('device', distinct=True)
                )
                
                # Handle None values
                logs_stats = {k: v or 0 for k, v in logs_stats.items()}
                
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
                
                # Handle None values
                attendance_stats = {k: v or 0 for k, v in attendance_stats.items()}
                
                # Processing efficiency metrics - Fixed division by zero
                if logs_stats['total_logs'] and logs_stats['total_logs'] > 0 and attendance_stats['total_records'] > 0:
                    processing_rate = (attendance_stats['total_records'] / logs_stats['total_logs']) * 100
                else:
                    processing_rate = 0.0
                
                stats = {
                    'logs_stats': logs_stats,
                    'attendance_stats': attendance_stats,
                    'processing_rate': round(processing_rate, 2)
                }
                
                cache.set(cache_key, stats, 300)  # Cache for 5 minutes
                
            except Exception as e:
                logger.error(f"Error calculating statistics: {str(e)}")
                # Provide default stats if calculation fails
                stats = {
                    'logs_stats': {
                        'total_logs': 0,
                        'earliest': None,
                        'latest': None,
                        'unique_employees': 0,
                        'unique_devices': 0
                    },
                    'attendance_stats': {
                        'total_records': 0,
                        'earliest': None,
                        'latest': None,
                        'present_days': 0,
                        'absent_days': 0,
                        'total_hours': 0,
                        'avg_daily_hours': 0
                    },
                    'processing_rate': 0.0
                }
        
        # Get data with error handling
        try:
            # Get employees with attendance logs
            employees_with_logs = Employee.objects.filter(
                company=company,
                attendancelog__isnull=False,
                is_active=True
            ).distinct().select_related('department', 'designation', 'default_shift').order_by('employee_id')
            
            # Get all active employees for selection
            all_employees = Employee.objects.filter(
                company=company,
                is_active=True
            ).select_related('department', 'designation', 'default_shift').order_by('employee_id')
            
            # Get available resources
            departments = Department.objects.filter(company=company).order_by('name')
            shifts = Shift.objects.filter(company=company).order_by('name')
            devices = ZkDevice.objects.filter(company=company, is_active=True).order_by('name')
            
        except Exception as e:
            logger.error(f"Error fetching data for attendance generation: {str(e)}")
            messages.error(request, f"Error loading data: {str(e)}")
            return redirect('zkteco:device_list')
        
        # Check for data quality issues
        try:
            data_quality_issues = check_data_quality(company)
        except Exception as e:
            logger.error(f"Error checking data quality: {str(e)}")
            data_quality_issues = [f"Error checking data quality: {str(e)}"]
        
        # Get processor configuration options
        processor_config = get_default_processor_config()
        
        context = {
            'company': company,
            'logs_stats': stats['logs_stats'],
            'attendance_stats': stats['attendance_stats'],
            'processing_rate': stats['processing_rate'],
            'employees_with_logs': employees_with_logs,
            'all_employees': all_employees,
            'departments': departments,
            'shifts': shifts,
            'devices': devices,
            'data_quality_issues': data_quality_issues,
            'processor_config': processor_config,
            'today': timezone.now().date(),
            'max_date_range_days': getattr(settings, 'ATTENDANCE_MAX_DATE_RANGE', 90),
        }
        
        return render(request, 'zkteco/attendance_generation.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in attendance_generation view: {str(e)}")
        messages.error(request, f"System error: {str(e)}")
        return redirect('zkteco:device_list')

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def attendance_generation_preview(request):
    """Enhanced preview with comprehensive error handling"""
    try:
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in preview request: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Invalid request format'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Validate and extract parameters
        validation_result = validate_generation_parameters(data)
        if not validation_result['valid']:
            return JsonResponse({'success': False, 'error': validation_result['error']})
        
        params = validation_result['params']
        
        # Initialize processor with configuration
        try:
            processor_config = extract_processor_config(data)
            processor = EnhancedAttendanceProcessor(processor_config)
        except Exception as e:
            logger.error(f"Error initializing processor: {str(e)}")
            return JsonResponse({'success': False, 'error': f'Configuration error: {str(e)}'})
        
        # Get processed attendance data
        processing_result = process_attendance_with_enhanced_processor(
            company, params, processor
        )
        
        if not processing_result['success']:
            return JsonResponse({'success': False, 'error': processing_result['error']})
        
        preview_data = processing_result.get('data', [])
        processor_summary = processing_result.get('summary', {})
        
        # Generate analytics from processed data
        try:
            analytics = generate_preview_analytics_from_processor(preview_data, processor_summary, params)
        except Exception as e:
            logger.error(f"Error generating analytics: {str(e)}")
            analytics = {'summary': {}, 'rule_stats': {}, 'processor_metrics': {}}
        
        # Data quality assessment
        try:
            quality_assessment = assess_processor_preview_quality(preview_data, processor_summary)
        except Exception as e:
            logger.error(f"Error assessing quality: {str(e)}")
            quality_assessment = {'overall_score': 0, 'issues': [], 'warnings': [], 'total_issues': 0, 'total_warnings': 0, 'processor_health_score': 0}
        
        # Generate recommendations
        try:
            recommendations = generate_processor_recommendations(preview_data, quality_assessment, processor_summary)
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            recommendations = []
        
        response_data = {
            'success': True,
            'preview_data': preview_data[:100] if preview_data else [],  # Limit for performance
            'summary': analytics.get('summary', {}),
            'analytics': analytics,
            'quality_assessment': quality_assessment,
            'recommendations': recommendations,
            'processor_summary': processor_summary,
            'has_more': len(preview_data) > 100 if preview_data else False,
            'total_records': len(preview_data) if preview_data else 0,
            'processor_config_summary': processor.get_config_summary() if processor else {}
        }
        
        # Cache preview data for generation
        try:
            cache_key = f"preview_data_{request.user.id}_{company.id}"
            cache.set(cache_key, {
                'data': preview_data,
                'params': params,
                'processor_config': processor_config,
                'summary': processor_summary,
                'timestamp': timezone.now().isoformat()
            }, 1800)  # 30 minutes
        except Exception as e:
            logger.error(f"Error caching preview data: {str(e)}")
            # Continue without caching
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Critical error in attendance generation preview: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})

def validate_generation_parameters(data):
    """Comprehensive parameter validation with error handling"""
    try:
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        if not start_date_str or not end_date_str:
            return {'valid': False, 'error': 'Start date and end date are required'}
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return {'valid': False, 'error': f'Invalid date format: {str(e)}'}
        
        # Validate date range
        if end_date < start_date:
            return {'valid': False, 'error': 'End date must be after start date'}
        
        # Check for reasonable date range
        today = date.today()
        if start_date > today + timedelta(days=30):
            return {'valid': False, 'error': 'Start date cannot be more than 30 days in the future'}
        
        if end_date > today + timedelta(days=30):
            return {'valid': False, 'error': 'End date cannot be more than 30 days in the future'}
        
        date_range_days = (end_date - start_date).days
        max_days = getattr(settings, 'ATTENDANCE_MAX_DATE_RANGE', 90)
        
        if date_range_days > max_days:
            return {'valid': False, 'error': f'Date range cannot exceed {max_days} days'}
        
        if date_range_days < 0:
            return {'valid': False, 'error': 'Invalid date range'}
        
        # Validate employee and department IDs
        employee_ids = data.get('employee_ids', [])
        department_ids = data.get('department_ids', [])
        device_ids = data.get('device_ids', [])
        
        # Ensure they are lists
        if not isinstance(employee_ids, list):
            employee_ids = []
        if not isinstance(department_ids, list):
            department_ids = []
        if not isinstance(device_ids, list):
            device_ids = []
        
        # Compile validated parameters
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'department_ids': department_ids,
            'employee_ids': employee_ids,
            'device_ids': device_ids,
            'regenerate_existing': bool(data.get('regenerate_existing', False)),
        }
        
        return {'valid': True, 'params': params}
        
    except Exception as e:
        logger.error(f"Error in parameter validation: {str(e)}")
        return {'valid': False, 'error': f'Parameter validation failed: {str(e)}'}

def extract_processor_config(data):
    """Extract processor configuration with proper error handling and defaults"""
    config = {}
    
    try:
        # Basic settings with safe conversion
        config['grace_minutes'] = safe_int_conversion(data.get('grace_minutes', 15), 15, 0, 120)
        config['early_out_threshold_minutes'] = safe_int_conversion(data.get('early_out_threshold_minutes', 30), 30, 0, 240)
        config['overtime_start_after_minutes'] = safe_int_conversion(data.get('overtime_start_after_minutes', 15), 15, 0, 120)
        config['minimum_overtime_minutes'] = safe_int_conversion(data.get('minimum_overtime_minutes', 60), 60, 0, 480)
        
        # Enhanced rules with safe conversion
        config['minimum_working_hours_for_present'] = safe_float_conversion(data.get('minimum_working_hours_for_present', 4), 4.0, 0.0, 24.0)
        config['enable_minimum_working_hours_rule'] = bool(data.get('enable_minimum_working_hours_rule', False))
        config['half_day_minimum_hours'] = safe_float_conversion(data.get('half_day_minimum_hours', 4), 4.0, 0.0, 12.0)
        config['half_day_maximum_hours'] = safe_float_conversion(data.get('half_day_maximum_hours', 6), 6.0, 0.0, 12.0)
        config['enable_working_hours_half_day_rule'] = bool(data.get('enable_working_hours_half_day_rule', False))
        config['require_both_in_and_out'] = bool(data.get('require_both_in_and_out', False))
        config['maximum_allowable_working_hours'] = safe_float_conversion(data.get('maximum_allowable_working_hours', 16), 16.0, 1.0, 24.0)
        config['enable_maximum_working_hours_rule'] = bool(data.get('enable_maximum_working_hours_rule', False))
        
        # Dynamic shift detection
        config['enable_dynamic_shift_detection'] = bool(data.get('enable_dynamic_shift_detection', False))
        config['dynamic_shift_tolerance_minutes'] = safe_int_conversion(data.get('dynamic_shift_tolerance_minutes', 30), 30, 0, 120)
        config['multiple_shift_priority'] = data.get('multiple_shift_priority', 'least_break')
        config['dynamic_shift_fallback_to_default'] = bool(data.get('dynamic_shift_fallback_to_default', True))
        
        # Employee-based overtime calculation
        config['use_employee_expected_hours'] = bool(data.get('use_employee_expected_hours', True))
        config['overtime_calculation_method'] = data.get('overtime_calculation_method', 'employee_based')
        
        # Other settings
        config['use_shift_grace_time'] = bool(data.get('use_shift_grace_time', False))
        config['consecutive_absence_termination_risk_days'] = safe_int_conversion(data.get('consecutive_absence_termination_risk_days', 5), 5, 1, 30)
        config['enable_consecutive_absence_flagging'] = bool(data.get('enable_consecutive_absence_flagging', False))
        
        # Weekend days with proper validation
        weekend_days = data.get('weekend_days', [4])
        if isinstance(weekend_days, list):
            config['weekend_days'] = [safe_int_conversion(d, 4, 0, 6) for d in weekend_days if str(d).isdigit()]
        else:
            config['weekend_days'] = [4]  # Default to Friday
        
        config['default_break_minutes'] = safe_int_conversion(data.get('default_break_minutes', 60), 60, 0, 240)
        config['use_shift_break_time'] = bool(data.get('use_shift_break_time', True))
        
        return config
        
    except Exception as e:
        logger.error(f"Error extracting processor config: {str(e)}")
        # Return default configuration if extraction fails
        return get_default_processor_config()

def safe_int_conversion(value, default, min_val=None, max_val=None):
    """Safely convert value to integer with bounds checking"""
    try:
        result = int(float(value))  # Handle string numbers
        if min_val is not None and result < min_val:
            return min_val
        if max_val is not None and result > max_val:
            return max_val
        return result
    except (ValueError, TypeError):
        return default

def safe_float_conversion(value, default, min_val=None, max_val=None):
    """Safely convert value to float with bounds checking"""
    try:
        result = float(value)
        if min_val is not None and result < min_val:
            return min_val
        if max_val is not None and result > max_val:
            return max_val
        return result
    except (ValueError, TypeError):
        return default

def generate_preview_analytics_from_processor(preview_data, processor_summary, params):
    """Generate analytics from processor results with error handling"""
    try:
        if not preview_data:
            return {'summary': {}, 'rule_stats': {}, 'processor_metrics': {}}
        
        # Basic summary from processor - safe calculations
        total_records = len(preview_data) if preview_data else 0
        new_records = len([r for r in preview_data if r.get('action') == 'create']) if preview_data else 0
        updated_records = len([r for r in preview_data if r.get('action') == 'update']) if preview_data else 0
        
        # Enhanced analytics with overtime amounts - safe summation
        total_overtime_amount = 0.0
        try:
            total_overtime_amount = sum(safe_float_conversion(r.get('overtime_amount', 0), 0.0) for r in preview_data)
        except Exception:
            total_overtime_amount = 0.0
        
        summary = {
            'total_records': total_records,
            'new_records': new_records,
            'updated_records': updated_records,
            'employees_affected': len(set(r.get('employee_id') for r in preview_data if r.get('employee_id'))) if preview_data else 0,
            'date_range': f"{params.get('start_date', 'N/A')} to {params.get('end_date', 'N/A')}",
            'present_days': processor_summary.get('present_count', 0),
            'absent_days': processor_summary.get('absent_count', 0),
            'late_days': processor_summary.get('late_count', 0),
            'holiday_days': processor_summary.get('holiday_count', 0),
            'leave_days': processor_summary.get('leave_count', 0),
            'half_day_count': processor_summary.get('half_day_count', 0),
            'total_working_hours': processor_summary.get('total_working_hours', 0),
            'total_overtime_hours': processor_summary.get('total_overtime_hours', 0),
            'total_overtime_amount': round(total_overtime_amount, 2),
            'avg_working_hours': processor_summary.get('avg_working_hours', 0),
            'attendance_percentage': processor_summary.get('attendance_percentage', 0),
            'punctuality_percentage': processor_summary.get('punctuality_percentage', 0),
        }
        
        # Rule application statistics - safe counting
        rule_stats = {
            'minimum_hours_conversions': len([r for r in preview_data if r.get('converted_from_minimum_hours')]) if preview_data else 0,
            'half_day_conversions': len([r for r in preview_data if r.get('converted_to_half_day')]) if preview_data else 0,
            'incomplete_punch_conversions': len([r for r in preview_data if r.get('converted_from_incomplete_punch')]) if preview_data else 0,
            'excessive_hours_flags': len([r for r in preview_data if r.get('excessive_working_hours_flag')]) if preview_data else 0,
        }
        
        return {
            'summary': summary,
            'rule_stats': rule_stats,
            'processor_metrics': processor_summary
        }
        
    except Exception as e:
        logger.error(f"Error generating analytics: {str(e)}")
        return {'summary': {}, 'rule_stats': {}, 'processor_metrics': {}}

def assess_processor_preview_quality(preview_data, processor_summary):
    """Assess quality from processor results with safe calculations"""
    try:
        issues = []
        warnings = []
        
        if not preview_data:
            issues.append("No preview data available for quality assessment")
            return {
                'overall_score': 0,
                'issues': issues,
                'warnings': warnings,
                'total_issues': len(issues),
                'total_warnings': len(warnings),
                'processor_health_score': 0
            }
        
        # Check rule application patterns - safe division
        total_records = len(preview_data)
        if total_records > 0:
            # High conversion rate from minimum hours rule
            min_hours_conversions = len([r for r in preview_data if r.get('converted_from_minimum_hours')])
            min_hours_rate = min_hours_conversions / total_records if total_records > 0 else 0
            if min_hours_rate > 0.3:  # More than 30%
                warnings.append(f"High conversion rate ({min_hours_rate:.1%}) due to minimum hours rule")
            
            # High incomplete punch rate
            incomplete_conversions = len([r for r in preview_data if r.get('converted_from_incomplete_punch')])
            incomplete_rate = incomplete_conversions / total_records if total_records > 0 else 0
            if incomplete_rate > 0.2:  # More than 20%
                issues.append(f"High incomplete punch rate ({incomplete_rate:.1%}) - check device synchronization")
            
            # Excessive working hours flags
            excessive_hours_count = len([r for r in preview_data if r.get('excessive_working_hours_flag')])
            if excessive_hours_count > 0:
                warnings.append(f"{excessive_hours_count} records flagged for excessive working hours")
        
        # Overall quality score from processor - safe calculation
        avg_quality = 0
        try:
            quality_scores = [r.get('quality_score', 0) for r in preview_data if r.get('quality_score') is not None]
            if quality_scores:
                avg_quality = sum(quality_scores) / len(quality_scores)
        except Exception:
            avg_quality = 0
        
        return {
            'overall_score': round(avg_quality, 2),
            'issues': issues,
            'warnings': warnings,
            'total_issues': len(issues),
            'total_warnings': len(warnings),
            'processor_health_score': processor_summary.get('attendance_percentage', 0)
        }
        
    except Exception as e:
        logger.error(f"Error assessing quality: {str(e)}")
        return {
            'overall_score': 0,
            'issues': [f"Error assessing quality: {str(e)}"],
            'warnings': [],
            'total_issues': 1,
            'total_warnings': 0,
            'processor_health_score': 0
        }

def process_attendance_with_enhanced_processor(company, params, processor):
    """Process attendance using EnhancedAttendanceProcessor with comprehensive error handling"""
    try:
        # Build optimized employee query
        employees_query = Employee.objects.filter(
            company=company, 
            is_active=True
        ).select_related('department', 'designation', 'default_shift')
        
        if params.get('department_ids'):
            employees_query = employees_query.filter(department_id__in=params['department_ids'])
        
        if params.get('employee_ids'):
            employees_query = employees_query.filter(id__in=params['employee_ids'])
        
        try:
            employees = list(employees_query)
        except Exception as e:
            logger.error(f"Error fetching employees: {str(e)}")
            return {'success': False, 'error': f'Error fetching employees: {str(e)}'}
        
        if not employees:
            return {'success': False, 'error': 'No employees found matching the criteria'}
        
        # Use processor's bulk attendance processing
        try:
            attendance_records = processor.process_bulk_attendance(
                employees, params['start_date'], params['end_date'], company
            )
        except Exception as e:
            logger.error(f"Error processing attendance records: {str(e)}")
            return {'success': False, 'error': f'Error processing attendance: {str(e)}'}
        
        if not attendance_records:
            return {'success': False, 'error': 'No attendance records could be processed'}
        
        # Convert processor records to preview format
        preview_data = []
        try:
            for record in attendance_records:
                try:
                    # Determine action (create/update)
                    existing_attendance = None
                    try:
                        existing_attendance = Attendance.objects.filter(
                            employee=record.get('employee'), 
                            date=record.get('date')
                        ).first()
                    except Exception as e:
                        logger.warning(f"Error checking existing attendance: {str(e)}")
                    
                    action = 'update' if existing_attendance and params.get('regenerate_existing') else 'create'
                    if existing_attendance and not params.get('regenerate_existing'):
                        continue  # Skip existing records
                    
                    # Calculate overtime amount based on employee rate - safe calculation
                    overtime_amount = 0.0
                    try:
                        overtime_hours = safe_float_conversion(record.get('overtime_hours', 0), 0.0)
                        if overtime_hours > 0 and record.get('employee') and hasattr(record['employee'], 'get_overtime_rate'):
                            overtime_rate = record['employee'].get_overtime_rate()
                            overtime_amount = overtime_hours * overtime_rate if overtime_rate else 0.0
                    except Exception as e:
                        logger.warning(f"Error calculating overtime amount: {str(e)}")
                        overtime_amount = 0.0
                    
                    preview_record = {
                        'employee_id': record.get('employee').id if record.get('employee') else None,
                        'employee_name': record.get('employee_name', 'Unknown'),
                        'employee_code': record.get('employee_id', 'Unknown'),
                        'department': record.get('department', 'N/A'),
                        'designation': record.get('designation', 'N/A'),
                        'date': record.get('date').isoformat() if record.get('date') else None,
                        'check_in_time': record.get('in_time').strftime('%H:%M:%S') if record.get('in_time') else None,
                        'check_out_time': record.get('out_time').strftime('%H:%M:%S') if record.get('out_time') else None,
                        'working_hours': safe_float_conversion(record.get('working_hours', 0), 0.0),
                        'overtime_hours': safe_float_conversion(record.get('overtime_hours', 0), 0.0),
                        'overtime_amount': round(overtime_amount, 2),
                        'expected_hours': safe_float_conversion(record.get('expected_hours', 8), 8.0),
                        'status': record.get('status', 'A'),
                        'shift_name': record.get('shift_name', 'No Shift'),
                        'punches_count': safe_int_conversion(record.get('total_logs', 0), 0),
                        'action': action,
                        'existing_record': bool(existing_attendance),
                        'is_holiday': bool(record.get('is_holiday', False)),
                        'is_leave': bool(record.get('is_leave', False)),
                        'is_weekend': record.get('day_name', '') in ['Saturday', 'Sunday'],
                        'quality_score': safe_float_conversion(record.get('quality_score', 0), 0.0),
                        'late_minutes': safe_int_conversion(record.get('late_minutes', 0), 0),
                        'early_out_minutes': safe_int_conversion(record.get('early_out_minutes', 0), 0),
                        'converted_from_minimum_hours': bool(record.get('converted_from_minimum_hours', False)),
                        'converted_to_half_day': bool(record.get('converted_to_half_day', False)),
                        'converted_from_incomplete_punch': bool(record.get('converted_from_incomplete_punch', False)),
                        'excessive_working_hours_flag': bool(record.get('excessive_working_hours_flag', False)),
                        'flag_reason': record.get('flag_reason', ''),
                        'conversion_reason': record.get('conversion_reason', ''),
                    }
                    preview_data.append(preview_record)
                    
                except Exception as e:
                    logger.warning(f"Error processing individual record: {str(e)}")
                    continue  # Skip problematic records
                    
        except Exception as e:
            logger.error(f"Error converting records to preview format: {str(e)}")
            return {'success': False, 'error': f'Error formatting preview data: {str(e)}'}
        
        # Generate summary from processor
        try:
            processor_summary = processor.generate_attendance_summary(attendance_records)
        except Exception as e:
            logger.error(f"Error generating processor summary: {str(e)}")
            processor_summary = {}
        
        return {
            'success': True, 
            'data': preview_data,
            'summary': processor_summary
        }
        
    except Exception as e:
        logger.error(f"Critical error processing attendance with enhanced processor: {str(e)}")
        return {'success': False, 'error': f'Processing failed: {str(e)}'}

def execute_attendance_generation_with_processor(company, preview_data, params, user):
    """Execute attendance generation from processed data with comprehensive error handling"""
    try:
        generated_count = 0
        updated_count = 0
        error_count = 0
        error_details = []
        
        if not preview_data:
            return {
                'success': False,
                'error': 'No preview data available for generation',
                'generated_count': 0,
                'updated_count': 0,
                'error_count': 0
            }
        
        with transaction.atomic():
            for record in preview_data:
                try:
                    employee_id = record.get('employee_id')
                    if not employee_id:
                        error_count += 1
                        error_details.append(f"Missing employee ID in record")
                        continue
                    
                    try:
                        employee = Employee.objects.get(id=employee_id)
                    except Employee.DoesNotExist:
                        error_count += 1
                        error_details.append(f"Employee with ID {employee_id} not found")
                        continue
                    
                    date_str = record.get('date')
                    if not date_str:
                        error_count += 1
                        error_details.append(f"Missing date for employee {employee.employee_id}")
                        continue
                    
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        error_count += 1
                        error_details.append(f"Invalid date format {date_str} for employee {employee.employee_id}")
                        continue
                    
                    # Parse times safely
                    check_in_time = None
                    check_out_time = None
                    
                    try:
                        if record.get('check_in_time'):
                            check_in_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_in_time'], '%H:%M:%S').time()
                            )
                            check_in_time = timezone.make_aware(check_in_datetime)
                    except ValueError:
                        logger.warning(f"Invalid check-in time format for employee {employee.employee_id}")
                    
                    try:
                        if record.get('check_out_time'):
                            check_out_datetime = datetime.combine(
                                date_obj, 
                                datetime.strptime(record['check_out_time'], '%H:%M:%S').time()
                            )
                            check_out_time = timezone.make_aware(check_out_datetime)
                    except ValueError:
                        logger.warning(f"Invalid check-out time format for employee {employee.employee_id}")
                    
                    # Safe decimal conversion for overtime hours
                    try:
                        overtime_hours = Decimal(str(record.get('overtime_hours', 0)))
                        if overtime_hours < 0:
                            overtime_hours = Decimal('0')
                    except (InvalidOperation, TypeError):
                        overtime_hours = Decimal('0')
                    
                    # Create or update attendance record
                    attendance_data = {
                        'employee': employee,
                        'shift': employee.default_shift,
                        'date': date_obj,
                        'check_in_time': check_in_time,
                        'check_out_time': check_out_time,
                        'status': record.get('status', 'A'),
                        'overtime_hours': overtime_hours
                    }
                    
                    if record.get('action') == 'update':
                        updated = Attendance.objects.filter(
                            employee=employee, date=date_obj
                        ).update(**{k: v for k, v in attendance_data.items() if k != 'employee'})
                        if updated:
                            updated_count += 1
                        else:
                            # Record didn't exist, create it instead
                            Attendance.objects.create(**attendance_data)
                            generated_count += 1
                    else:
                        # Check if record already exists to avoid duplicates
                        existing = Attendance.objects.filter(employee=employee, date=date_obj).exists()
                        if not existing:
                            Attendance.objects.create(**attendance_data)
                            generated_count += 1
                        else:
                            # Update existing record instead
                            Attendance.objects.filter(
                                employee=employee, date=date_obj
                            ).update(**{k: v for k, v in attendance_data.items() if k != 'employee'})
                            updated_count += 1
                        
                except Exception as e:
                    error_count += 1
                    employee_code = record.get('employee_code', 'unknown')
                    error_msg = f"Error processing employee {employee_code}: {str(e)}"
                    error_details.append(error_msg)
                    logger.error(error_msg)
        
        # Prepare result message
        total_processed = generated_count + updated_count
        if total_processed == 0 and error_count > 0:
            success = False
            message = f'Generation failed: {error_count} errors occurred. No records were processed.'
        elif error_count > 0:
            success = True  # Partial success
            message = f'Processing completed with warnings: {generated_count} created, {updated_count} updated, {error_count} errors.'
        else:
            success = True
            message = f'Processing completed successfully: {generated_count} created, {updated_count} updated.'
        
        result = {
            'success': success,
            'generated_count': generated_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'total_processed': total_processed,
            'message': message
        }
        
        # Add error details if there were errors
        if error_details:
            result['error_details'] = error_details[:10]  # Limit to first 10 errors
            if len(error_details) > 10:
                result['additional_errors'] = len(error_details) - 10
        
        return result
        
    except Exception as e:
        logger.error(f"Critical error executing attendance generation: {str(e)}")
        return {
            'success': False,
            'error': f'Generation execution failed: {str(e)}',
            'generated_count': 0,
            'updated_count': 0,
            'error_count': 0
        }

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def generate_attendance_records(request):
    """Generate attendance records with enhanced error handling"""
    try:
        # Parse request data safely
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in generation request: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Invalid request format'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Check if using cached preview data
        use_cached_preview = data.get('use_cached_preview', False)
        
        if use_cached_preview:
            try:
                cache_key = f"preview_data_{request.user.id}_{company.id}"
                cached_data = cache.get(cache_key)
                
                if not cached_data:
                    return JsonResponse({'success': False, 'error': 'Preview data expired. Please generate preview again.'})
                
                preview_data = cached_data.get('data', [])
                params = cached_data.get('params', {})
                processor_config = cached_data.get('processor_config', {})
            except Exception as e:
                logger.error(f"Error retrieving cached preview data: {str(e)}")
                return JsonResponse({'success': False, 'error': 'Error retrieving preview data. Please generate preview again.'})
        else:
            # Validate parameters and process data
            validation_result = validate_generation_parameters(data)
            if not validation_result['valid']:
                return JsonResponse({'success': False, 'error': validation_result['error']})
            
            params = validation_result['params']
            
            try:
                processor_config = extract_processor_config(data)
                processor = EnhancedAttendanceProcessor(processor_config)
            except Exception as e:
                logger.error(f"Error initializing processor for generation: {str(e)}")
                return JsonResponse({'success': False, 'error': f'Configuration error: {str(e)}'})
            
            # Process with EnhancedAttendanceProcessor
            processing_result = process_attendance_with_enhanced_processor(
                company, params, processor
            )
            
            if not processing_result['success']:
                return JsonResponse({'success': False, 'error': processing_result['error']})
            
            preview_data = processing_result.get('data', [])
        
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data available for generation'})
        
        # Execute generation with transaction
        generation_result = execute_attendance_generation_with_processor(
            company, preview_data, params, request.user
        )
        
        if generation_result['success']:
            try:
                # Clear cached preview data
                cache_key = f"preview_data_{request.user.id}_{company.id}"
                cache.delete(cache_key)
                
                # Clear company stats cache
                cache.delete(f"attendance_gen_stats_{company.id}")
            except Exception as e:
                logger.warning(f"Error clearing cache: {str(e)}")
            
            # Log generation activity
            try:
                log_generation_activity(company, request.user, generation_result, params)
            except Exception as e:
                logger.warning(f"Error logging generation activity: {str(e)}")
        
        return JsonResponse(generation_result)
        
    except Exception as e:
        logger.error(f"Critical error generating attendance records: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Generation failed: {str(e)}'})

def get_default_processor_config():
    """Get default processor configuration for UI"""
    return {
        'grace_minutes': 15,
        'early_out_threshold_minutes': 30,
        'overtime_start_after_minutes': 15,
        'minimum_overtime_minutes': 60,
        'minimum_working_hours_for_present': 4.0,
        'half_day_minimum_hours': 4.0,
        'half_day_maximum_hours': 6.0,
        'maximum_allowable_working_hours': 16.0,
        'dynamic_shift_tolerance_minutes': 30,
        'consecutive_absence_termination_risk_days': 5,
        'weekend_days': [4],  # Friday
        'default_break_minutes': 60,
        'use_employee_expected_hours': True,
        'overtime_calculation_method': 'employee_based',
    }

def generate_processor_recommendations(preview_data, quality_assessment, processor_summary):
    """Generate recommendations based on processor results with error handling"""
    try:
        recommendations = []
        
        if not preview_data:
            recommendations.append({
                'type': 'warning',
                'title': 'No Data Available',
                'message': 'No attendance data available for analysis.',
                'priority': 'high'
            })
            return recommendations
        
        if quality_assessment.get('overall_score', 0) < 70:
            recommendations.append({
                'type': 'warning',
                'title': 'Data Quality Issues',
                'message': 'Consider reviewing attendance logs and processor configuration.',
                'priority': 'high'
            })
        
        # Rule-specific recommendations
        if len([r for r in preview_data if r.get('converted_from_minimum_hours')]) > 0:
            recommendations.append({
                'type': 'info',
                'title': 'Minimum Hours Rule Active',
                'message': 'Some attendance records converted to absent due to insufficient working hours.',
                'priority': 'medium'
            })
        
        if len([r for r in preview_data if r.get('excessive_working_hours_flag')]) > 0:
            recommendations.append({
                'type': 'warning',
                'title': 'Excessive Working Hours Detected',
                'message': 'Review flagged records for data accuracy or adjust maximum hours threshold.',
                'priority': 'high'
            })
        
        # Attendance pattern recommendations
        attendance_percentage = processor_summary.get('attendance_percentage', 0)
        if attendance_percentage < 80:
            recommendations.append({
                'type': 'info',
                'title': 'Low Attendance Rate',
                'message': f"Overall attendance rate is {attendance_percentage:.1f}%. Consider reviewing attendance policies.",
                'priority': 'medium'
            })
        
        # Overtime analysis - safe calculation
        try:
            total_overtime_amount = sum(r.get('overtime_amount', 0) for r in preview_data if r.get('overtime_amount'))
            if total_overtime_amount > 10000:  # Threshold can be adjusted
                recommendations.append({
                    'type': 'info',
                    'title': 'High Overtime Costs',
                    'message': f"Total overtime amount: {total_overtime_amount:.2f}. Consider reviewing overtime policies.",
                    'priority': 'medium'
                })
        except Exception as e:
            logger.warning(f"Error calculating overtime recommendations: {str(e)}")
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        return [{
            'type': 'warning',
            'title': 'Recommendation Error',
            'message': f'Unable to generate recommendations: {str(e)}',
            'priority': 'low'
        }]

def check_data_quality(company):
    """Check for common data quality issues with error handling"""
    try:
        issues = []
        
        # Check for employees without logs
        try:
            employees_without_logs = Employee.objects.filter(
                company=company,
                is_active=True,
                attendancelog__isnull=True
            ).count()
            
            if employees_without_logs > 0:
                issues.append(f"{employees_without_logs} active employees have no attendance logs")
        except Exception as e:
            issues.append(f"Error checking employees without logs: {str(e)}")
        
        # Check for devices not syncing
        try:
            inactive_devices = ZkDevice.objects.filter(
                company=company,
                is_active=False
            ).count()
            
            if inactive_devices > 0:
                issues.append(f"{inactive_devices} devices are currently inactive")
        except Exception as e:
            issues.append(f"Error checking inactive devices: {str(e)}")
        
        # Check for employees without expected working hours set
        try:
            employees_without_hours = Employee.objects.filter(
                company=company,
                is_active=True,
                expected_working_hours__isnull=True
            ).count()
            
            if employees_without_hours > 0:
                issues.append(f"{employees_without_hours} employees don't have expected working hours set")
        except Exception as e:
            issues.append(f"Error checking employees without working hours: {str(e)}")
        
        # Check for employees without overtime rate
        try:
            employees_without_ot_rate = Employee.objects.filter(
                company=company,
                is_active=True,
                overtime_rate__lte=0
            ).count()
            
            if employees_without_ot_rate > 0:
                issues.append(f"{employees_without_ot_rate} employees don't have overtime rate configured")
        except Exception as e:
            issues.append(f"Error checking employees without overtime rate: {str(e)}")
        
        return issues
        
    except Exception as e:
        logger.error(f"Error in data quality check: {str(e)}")
        return [f"Error checking data quality: {str(e)}"]

def log_generation_activity(company, user, result, params):
    """Log generation activity for audit purposes with error handling"""
    try:
        logger.info(f"Attendance generation completed by {user.username} for {company.name}: "
                   f"{result.get('generated_count', 0)} created, {result.get('updated_count', 0)} updated, "
                   f"{result.get('error_count', 0)} errors")
    except Exception as e:
        logger.warning(f"Error logging generation activity: {str(e)}")

# Bulk operations with enhanced error handling
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete_attendance_records(request):
    """Bulk delete attendance records for a date range with comprehensive error handling"""
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in bulk delete request: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Invalid request format'})
        
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        employee_ids = data.get('employee_ids', [])
        
        if not start_date_str or not end_date_str:
            return JsonResponse({'success': False, 'error': 'Start date and end date are required'})
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return JsonResponse({'success': False, 'error': f'Invalid date format: {str(e)}'})
        
        if end_date < start_date:
            return JsonResponse({'success': False, 'error': 'End date must be after start date'})
        
        # Build query
        query = Q(
            employee__company=company,
            date__gte=start_date,
            date__lte=end_date
        )
        
        if employee_ids:
            # Validate employee IDs
            if not isinstance(employee_ids, list):
                return JsonResponse({'success': False, 'error': 'Employee IDs must be a list'})
            query &= Q(employee_id__in=employee_ids)
        
        # Perform deletion with transaction
        try:
            with transaction.atomic():
                deleted_count, _ = Attendance.objects.filter(query).delete()
        except Exception as e:
            logger.error(f"Error deleting attendance records: {str(e)}")
            return JsonResponse({'success': False, 'error': f'Deletion failed: {str(e)}'})
        
        # Clear cache
        try:
            cache.delete(f"attendance_gen_stats_{company.id}")
        except Exception as e:
            logger.warning(f"Error clearing cache after deletion: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} attendance records'
        })
        
    except Exception as e:
        logger.error(f"Critical error in bulk delete: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Bulk delete failed: {str(e)}'})

@login_required
@require_http_methods(["POST"])
def export_preview_data(request):
    """Export preview data to CSV with comprehensive error handling"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get cached preview data
        cache_key = f"preview_data_{request.user.id}_{company.id}"
        try:
            cached_data = cache.get(cache_key)
        except Exception as e:
            logger.error(f"Error retrieving cached data for export: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Error retrieving preview data'})
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'No preview data found'})
        
        preview_data = cached_data.get('data', [])
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No preview data available for export'})
        
        try:
            # Create HTTP response with CSV
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="attendance_preview_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
            
            writer = csv.writer(response)
            writer.writerow([
                'Employee Code', 'Employee Name', 'Department', 'Date',
                'Check In', 'Check Out', 'Working Hours', 'Overtime Hours',
                'Overtime Amount', 'Status', 'Shift', 'Action', 'Quality Score',
                'Expected Hours', 'Late Minutes', 'Early Out Minutes'
            ])
            
            for record in preview_data:
                try:
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
                        record.get('action', ''),
                        record.get('quality_score', 0),
                        record.get('expected_hours', 8),
                        record.get('late_minutes', 0),
                        record.get('early_out_minutes', 0)
                    ])
                except Exception as e:
                    logger.warning(f"Error writing CSV row: {str(e)}")
                    continue  # Skip problematic rows
        
        except Exception as e:
            logger.error(f"Error creating CSV response: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Error creating export file'})
        
        return response
        
    except Exception as e:
        logger.error(f"Critical error exporting preview data: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Export failed'})