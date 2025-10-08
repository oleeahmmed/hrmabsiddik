# improved_attendance_generation_views.py
"""
সম্পূর্ণ সংশোধিত Attendance Generation System
সকল Configuration Settings সহ সঠিক Implementation
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date, timedelta, time
from django.core.cache import cache
from decimal import Decimal
import json
import logging
import csv
from collections import defaultdict

from .models import (
    Employee, Attendance, AttendanceProcessorConfiguration,
    Shift, Holiday, LeaveApplication, AttendanceLog,
    RosterAssignment, RosterDay
)
from core.models import Company

logger = logging.getLogger(__name__)


# ==================== HELPER CLASSES ====================

def ensure_timezone_aware(dt):
    """Ensure datetime is timezone aware"""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def safe_datetime_comparison(dt1, dt2):
    """Safely compare two datetimes by ensuring both are aware"""
    dt1 = ensure_timezone_aware(dt1)
    dt2 = ensure_timezone_aware(dt2)
    if dt1 is None or dt2 is None:
        return False
    return dt1 > dt2


class ShiftMatcher:
    """Dynamic Shift Detection Helper"""
    
    def __init__(self, config):
        self.config = config
        self.tolerance_minutes = config.get('dynamic_shift_tolerance_minutes', 30)
        self.priority = config.get('multiple_shift_priority', 'least_break')
    
    def find_matching_shifts(self, company, check_in_time):
        """Find all shifts that match the check-in time"""
        if not check_in_time:
            return []
        
        # Ensure timezone aware
        check_in_time = ensure_timezone_aware(check_in_time)
        
        shifts = Shift.objects.filter(company=company)
        matching_shifts = []
        
        for shift in shifts:
            # Use the actual check-in date for comparison
            check_in_date = check_in_time.date()
            
            # Calculate time difference
            shift_start = timezone.make_aware(
                datetime.combine(check_in_date, shift.start_time)
            )
            
            # Calculate difference in minutes
            diff_minutes = abs((check_in_time - shift_start).total_seconds() / 60)
            
            if diff_minutes <= self.tolerance_minutes:
                score = self.tolerance_minutes - diff_minutes
                matching_shifts.append({
                    'shift': shift,
                    'score': score,
                    'diff_minutes': diff_minutes
                })
        
        return matching_shifts
    
    def select_best_shift(self, matching_shifts):
        """Select best shift based on priority"""
        if not matching_shifts:
            return None
        
        if self.priority == 'least_break':
            return min(matching_shifts, key=lambda x: x['shift'].break_time)['shift']
        elif self.priority == 'shortest_duration':
            return min(matching_shifts, key=lambda x: x['shift'].duration_minutes)['shift']
        elif self.priority == 'highest_score':
            return max(matching_shifts, key=lambda x: x['score'])['shift']
        else:  # alphabetical
            return sorted(matching_shifts, key=lambda x: x['shift'].name)[0]['shift']


class AttendanceCalculator:
    """Attendance Calculation Helper"""
    
    def __init__(self, config):
        self.config = config
    
    def calculate_working_hours(self, check_in, check_out, shift):
        """Calculate actual working hours with break deduction"""
        if not check_in or not check_out:
            return 0.0
        
        # Ensure both are timezone aware
        check_in = ensure_timezone_aware(check_in)
        check_out = ensure_timezone_aware(check_out)
        
        # Total time
        total_seconds = (check_out - check_in).total_seconds()
        total_hours = total_seconds / 3600
        
        # Deduct break time
        if self.config.get('use_shift_break_time') and shift:
            break_minutes = shift.break_time
        else:
            break_minutes = self.config.get('default_break_minutes', 60)
        
        # Apply break deduction method
        method = self.config.get('break_deduction_method', 'fixed')
        
        if method == 'fixed':
            # Fixed break deduction
            break_hours = break_minutes / 60
            working_hours = max(0, total_hours - break_hours)
        else:  # proportional
            # Proportional break based on working hours
            if total_hours > 4:
                break_hours = break_minutes / 60
                working_hours = max(0, total_hours - break_hours)
            else:
                working_hours = total_hours
        
        return round(working_hours, 2)
    
    def calculate_overtime(self, working_hours, shift, employee, is_weekend, is_holiday):
        """Calculate overtime hours"""
        config = self.config
        
        # Weekend/Holiday full day overtime
        if is_holiday and config.get('holiday_overtime_full_day'):
            return working_hours
        if is_weekend and config.get('weekend_overtime_full_day'):
            return working_hours
        
        # Determine expected hours
        method = config.get('overtime_calculation_method', 'employee_based')
        
        if method == 'shift_based' and shift:
            expected_hours = shift.duration_hours
        elif method == 'employee_based':
            expected_hours = employee.expected_working_hours
        else:  # fixed_hours
            expected_hours = 8.0
        
        # Calculate overtime
        overtime_start_threshold = config.get('overtime_start_after_minutes', 15) / 60
        overtime_hours = max(0, working_hours - expected_hours - overtime_start_threshold)
        
        # Check minimum overtime
        minimum_ot_hours = config.get('minimum_overtime_minutes', 60) / 60
        if overtime_hours < minimum_ot_hours:
            overtime_hours = 0
        
        # Deduct separate OT break
        ot_break_minutes = config.get('separate_ot_break_time', 0)
        if ot_break_minutes > 0 and overtime_hours > 0:
            overtime_hours = max(0, overtime_hours - (ot_break_minutes / 60))
        
        return round(overtime_hours, 2)
    
    def is_late(self, check_in_time, shift, employee):
        """Check if employee is late"""
        if not check_in_time or not shift:
            return False
        
        # Ensure timezone aware
        check_in_time = ensure_timezone_aware(check_in_time)
        
        # Get grace time
        if self.config.get('use_shift_grace_time') and shift:
            grace_minutes = shift.grace_time
        elif self.config.get('use_employee_specific_grace') and employee.overtime_grace_minutes:
            grace_minutes = employee.overtime_grace_minutes
        else:
            grace_minutes = self.config.get('grace_minutes', 15)
        
        # Calculate late - use check_in date
        shift_start = timezone.make_aware(
            datetime.combine(check_in_time.date(), shift.start_time)
        )
        grace_end = shift_start + timedelta(minutes=grace_minutes)
        
        return check_in_time > grace_end
    
    def is_early_out(self, check_out_time, shift):
        """Check if employee left early"""
        if not check_out_time or not shift:
            return False
        
        # Ensure timezone aware
        check_out_time = ensure_timezone_aware(check_out_time)
        
        threshold_minutes = self.config.get('early_out_threshold_minutes', 30)
        
        # Use check_out date
        shift_end = timezone.make_aware(
            datetime.combine(check_out_time.date(), shift.end_time)
        )
        
        # Handle overnight shifts
        if shift.end_time < shift.start_time:
            shift_end += timedelta(days=1)
        
        early_threshold = shift_end - timedelta(minutes=threshold_minutes)
        
        return check_out_time < early_threshold
    
    def determine_status(self, check_in, check_out, working_hours, shift, is_weekend, is_holiday, has_leave):
        """Determine attendance status based on rules"""
        config = self.config
        
        # Weekend
        if is_weekend:
            return 'W'
        
        # Holiday
        if is_holiday:
            return 'H'
        
        # Leave
        if has_leave:
            return 'L'
        
        # No attendance logs
        if not check_in and not check_out:
            return 'A'
        
        # Both in and out required
        if config.get('require_both_in_and_out'):
            if not check_in or not check_out:
                return 'A'
        
        # Minimum working hours rule
        if config.get('enable_minimum_working_hours_rule'):
            min_hours = config.get('minimum_working_hours_for_present', 4.0)
            if working_hours < min_hours:
                return 'A'
        
        # Maximum working hours rule (flag for review)
        if config.get('enable_maximum_working_hours_rule'):
            max_hours = config.get('maximum_allowable_working_hours', 16.0)
            if working_hours > max_hours:
                logger.warning(f"Excessive working hours: {working_hours}")
        
        # Working hours half day rule
        if config.get('enable_working_hours_half_day_rule'):
            min_half = config.get('half_day_minimum_hours', 4.0)
            max_half = config.get('half_day_maximum_hours', 6.0)
            if min_half <= working_hours <= max_half:
                return 'HD'  # Half Day
        
        # Present
        return 'P'


class AttendancePreprocessor:
    """Preprocess data for efficient generation"""
    
    def __init__(self, company, start_date, end_date):
        self.company = company
        self.start_date = start_date
        self.end_date = end_date
        self._load_data()
    
    def _load_data(self):
        """Load all required data in bulk"""
        # Holidays
        self.holidays = set(
            Holiday.objects.filter(
                company=self.company,
                date__range=[self.start_date, self.end_date]
            ).values_list('date', flat=True)
        )
        
        # Leave Applications
        self.leaves = defaultdict(set)
        leave_apps = LeaveApplication.objects.filter(
            employee__company=self.company,
            status='A',
            start_date__lte=self.end_date,
            end_date__gte=self.start_date
        ).select_related('employee')
        
        for leave in leave_apps:
            current = max(leave.start_date, self.start_date)
            end = min(leave.end_date, self.end_date)
            while current <= end:
                self.leaves[leave.employee_id].add(current)
                current += timedelta(days=1)
        
        # Attendance Logs (bulk load)
        self.attendance_logs = defaultdict(list)
        logs = AttendanceLog.objects.filter(
            employee__company=self.company,
            timestamp__date__range=[self.start_date, self.end_date]
        ).select_related('employee').order_by('timestamp')
        
        for log in logs:
            key = (log.employee_id, log.timestamp.date())
            self.attendance_logs[key].append(log)
        
        # Roster Assignments
        self.roster_shifts = {}
        roster_days = RosterDay.objects.filter(
            roster_assignment__roster__company=self.company,
            date__range=[self.start_date, self.end_date]
        ).select_related('roster_assignment__employee', 'shift')
        
        for rd in roster_days:
            key = (rd.roster_assignment.employee_id, rd.date)
            self.roster_shifts[key] = rd.shift
        
        # Existing Attendance (for adjacent day checks)
        buffer_start = self.start_date - timedelta(days=2)
        buffer_end = self.end_date + timedelta(days=2)
        
        self.existing_attendance = {}
        existing = Attendance.objects.filter(
            employee__company=self.company,
            date__range=[buffer_start, buffer_end]
        ).values('employee_id', 'date', 'status')
        
        for att in existing:
            key = (att['employee_id'], att['date'])
            self.existing_attendance[key] = att['status']
    
    def get_logs_for_day(self, employee_id, date):
        """Get attendance logs for specific employee and date"""
        return self.attendance_logs.get((employee_id, date), [])
    
    def has_leave(self, employee_id, date):
        """Check if employee has leave on date"""
        return date in self.leaves.get(employee_id, set())
    
    def is_holiday(self, date):
        """Check if date is holiday"""
        return date in self.holidays
    
    def get_roster_shift(self, employee_id, date):
        """Get shift from roster"""
        return self.roster_shifts.get((employee_id, date))
    
    def get_adjacent_status(self, employee_id, date):
        """Get status of previous and next day"""
        prev_day = date - timedelta(days=1)
        next_day = date + timedelta(days=1)
        
        prev_status = self.existing_attendance.get((employee_id, prev_day))
        next_status = self.existing_attendance.get((employee_id, next_day))
        
        return prev_status, next_status


# ==================== MAIN VIEW FUNCTIONS ====================

def get_company_from_request(request):
    """Helper to get company"""
    try:
        return Company.objects.first()
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
        
        # Get or create active configuration
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
        employees = Employee.objects.filter(company=company, is_active=True)
        today = timezone.now().date()
        first_day = today.replace(day=1)
        
        stats = {
            'total_employees': employees.count(),
            'total_attendance': Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day
            ).count(),
            'present_count': Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day,
                status='P'
            ).count(),
            'absent_count': Attendance.objects.filter(
                employee__company=company,
                date__gte=first_day,
                status='A'
            ).count(),
        }
        
        # Get filters
        from .models import Department
        departments = Department.objects.filter(company=company)
        shifts = Shift.objects.filter(company=company)
        
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
    """Generate attendance preview with full configuration support"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        company = get_company_from_request(request)
        
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Validate and parse dates
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        except (KeyError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'Invalid date format: {str(e)}'})
        
        if end_date < start_date:
            return JsonResponse({'success': False, 'error': 'End date must be after start date'})
        
        # Get configuration
        config = AttendanceProcessorConfiguration.get_active_config(company)
        if not config:
            return JsonResponse({'success': False, 'error': 'No active configuration found'})
        
        config_dict = config.get_config_dict()
        weekend_days = config.weekend_days
        
        # Get employees with filters
        employees_query = Employee.objects.filter(company=company, is_active=True)
        
        if data.get('employee_ids'):
            employees_query = employees_query.filter(id__in=data['employee_ids'])
        if data.get('department_ids'):
            employees_query = employees_query.filter(department_id__in=data['department_ids'])
        
        employees = employees_query.select_related('department', 'default_shift')
        
        if not employees.exists():
            return JsonResponse({'success': False, 'error': 'No employees found'})
        
        # Initialize helpers
        preprocessor = AttendancePreprocessor(company, start_date, end_date)
        shift_matcher = ShiftMatcher(config_dict)
        calculator = AttendanceCalculator(config_dict)
        
        # Generate preview data
        preview_data = []
        summary = {
            'total_records': 0,
            'present_count': 0,
            'absent_count': 0,
            'leave_count': 0,
            'weekend_count': 0,
            'holiday_count': 0,
            'half_day_count': 0,
            'late_count': 0,
            'early_out_count': 0,
            'total_overtime_hours': 0,
            'total_overtime_amount': 0,
        }
        
        current_date = start_date
        while current_date <= end_date:
            is_weekend = current_date.weekday() in weekend_days
            is_holiday = preprocessor.is_holiday(current_date)
            
            for employee in employees:
                # Skip if already exists and not regenerating
                if not data.get('regenerate_existing'):
                    existing = preprocessor.existing_attendance.get((employee.id, current_date))
                    if existing:
                        continue
                
                # Get logs for the day
                logs = preprocessor.get_logs_for_day(employee.id, current_date)
                
                check_in = logs[0].timestamp if logs else None
                check_out = logs[-1].timestamp if len(logs) > 1 else None
                
                # Determine shift
                shift = None
                
                # 1. First check roster
                shift = preprocessor.get_roster_shift(employee.id, current_date)
                
                # 2. If no roster, check default shift
                if not shift:
                    shift = employee.default_shift
                
                # 3. If no default shift and dynamic detection enabled
                if not shift and config_dict.get('enable_dynamic_shift_detection') and check_in:
                    matching_shifts = shift_matcher.find_matching_shifts(company, check_in)
                    if matching_shifts:
                        shift = shift_matcher.select_best_shift(matching_shifts)
                    elif config_dict.get('dynamic_shift_fallback_to_default'):
                        shift = employee.default_shift
                    elif config_dict.get('dynamic_shift_fallback_shift_id'):
                        try:
                            shift = Shift.objects.get(id=config_dict['dynamic_shift_fallback_shift_id'])
                        except Shift.DoesNotExist:
                            pass
                
                # Check leave
                has_leave = preprocessor.has_leave(employee.id, current_date)
                
                # Calculate working hours
                working_hours = calculator.calculate_working_hours(check_in, check_out, shift)
                
                # Calculate overtime
                overtime_hours = calculator.calculate_overtime(
                    working_hours, shift, employee, is_weekend, is_holiday
                )
                
                # Determine status
                status = calculator.determine_status(
                    check_in, check_out, working_hours, shift,
                    is_weekend, is_holiday, has_leave
                )
                
                # Check late and early out
                is_late = calculator.is_late(check_in, shift, employee)
                is_early = calculator.is_early_out(check_out, shift)
                
                # Calculate overtime amount
                if config_dict.get('use_employee_specific_overtime'):
                    ot_rate = employee.get_overtime_rate()
                else:
                    ot_rate = float(employee.get_hourly_rate() * 1.5)
                
                overtime_amount = round(overtime_hours * ot_rate, 2)
                
                # Update summary
                summary['total_records'] += 1
                if status == 'P':
                    summary['present_count'] += 1
                elif status == 'A':
                    summary['absent_count'] += 1
                elif status == 'L':
                    summary['leave_count'] += 1
                elif status == 'W':
                    summary['weekend_count'] += 1
                elif status == 'H':
                    summary['holiday_count'] += 1
                elif status == 'HD':
                    summary['half_day_count'] += 1
                
                if is_late:
                    summary['late_count'] += 1
                if is_early:
                    summary['early_out_count'] += 1
                
                summary['total_overtime_hours'] += overtime_hours
                summary['total_overtime_amount'] += overtime_amount
                
                # Create preview record
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
                    'shift_name': shift.name if shift else 'No Shift',
                    'is_late': is_late,
                    'is_early_out': is_early,
                }
                
                preview_data.append(preview_record)
            
            current_date += timedelta(days=1)
        
        # Round summary values
        summary['total_overtime_hours'] = round(summary['total_overtime_hours'], 2)
        summary['total_overtime_amount'] = round(summary['total_overtime_amount'], 2)
        
        # Cache preview data
        cache_key = f"simple_preview_{request.user.id}"
        cache.set(cache_key, {
            'data': preview_data,
            'params': data,
            'timestamp': timezone.now().isoformat()
        }, 1800)
        
        return JsonResponse({
            'success': True,
            'preview_data': preview_data,
            'summary': summary,
            'message': f'Successfully generated {len(preview_data)} preview records'
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({'success': False, 'error': f'Invalid JSON: {str(e)}'})
    except Exception as e:
        logger.error(f"Preview error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def simple_generate_records(request):
    """Generate attendance records from cached preview"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company access found'})
        
        # Get cached data
        cache_key = f"simple_preview_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'Preview data expired'})
        
        preview_data = cached_data.get('data', [])
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data available'})
        
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
                        check_in_time = timezone.make_aware(check_in_time)
                    
                    if record.get('check_out_time'):
                        check_out_time = datetime.strptime(
                            f"{record['date']} {record['check_out_time']}", 
                            '%Y-%m-%d %H:%M:%S'
                        )
                        check_out_time = timezone.make_aware(check_out_time)
                    
                    # Get shift
                    shift = None
                    if record.get('shift_name') and record['shift_name'] != 'No Shift':
                        try:
                            shift = Shift.objects.get(
                                company=company,
                                name=record['shift_name']
                            )
                        except Shift.DoesNotExist:
                            shift = employee.default_shift
                    else:
                        shift = employee.default_shift
                    
                    # Create or update attendance
                    attendance, created = Attendance.objects.update_or_create(
                        employee=employee,
                        date=date_obj,
                        defaults={
                            'check_in_time': check_in_time,
                            'check_out_time': check_out_time,
                            'status': record['status'],
                            'overtime_hours': Decimal(str(record.get('overtime_hours', 0))),
                            'shift': shift,
                        }
                    )
                    
                    if created:
                        generated_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing record: {e}", exc_info=True)
        
        # Clear cache
        cache.delete(cache_key)
        
        message = f'Generated {generated_count}, Updated {updated_count}'
        if error_count > 0:
            message += f', Errors {error_count}'
        
        return JsonResponse({
            'success': True,
            'records_created': generated_count,
            'records_updated': updated_count,
            'error_count': error_count,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Generate records error: {str(e)}", exc_info=True)
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
            return JsonResponse({'success': False, 'error': 'No preview data found'})
        
        preview_data = cached_data.get('data', [])
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'No data to export'})
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="attendance_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Employee Code', 'Employee Name', 'Department', 'Date',
            'Check In', 'Check Out', 'Working Hours', 'Overtime Hours',
            'Overtime Amount', 'Status', 'Shift', 'Late', 'Early Out'
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
                record.get('shift_name', ''),
                'Yes' if record.get('is_late') else 'No',
                'Yes' if record.get('is_early_out') else 'No'
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})


# ==================== VALIDATION & ANALYSIS ====================

@login_required
def validate_attendance_config(request):
    """Validate attendance configuration"""
    try:
        company = get_company_from_request(request)
        if not company:
            return JsonResponse({'success': False, 'error': 'No company found'})
        
        config = AttendanceProcessorConfiguration.get_active_config(company)
        if not config:
            return JsonResponse({'success': False, 'error': 'No active configuration'})
        
        issues = []
        warnings = []
        
        # Check shifts
        shifts = Shift.objects.filter(company=company)
        if not shifts.exists():
            issues.append('No shifts defined')
        
        # Check employees without default shift
        employees_no_shift = Employee.objects.filter(
            company=company,
            is_active=True,
            default_shift__isnull=True
        ).count()
        
        if employees_no_shift > 0:
            if not config.enable_dynamic_shift_detection:
                warnings.append(f'{employees_no_shift} employees without default shift and dynamic detection disabled')
            else:
                warnings.append(f'{employees_no_shift} employees will use dynamic shift detection')
        
        # Check roster coverage
        from django.db.models import Count
        roster_coverage = RosterAssignment.objects.filter(
            roster__company=company,
            roster__start_date__lte=timezone.now().date(),
            roster__end_date__gte=timezone.now().date()
        ).values('employee').annotate(count=Count('id'))
        
        if roster_coverage.count() == 0:
            warnings.append('No active roster assignments found')
        
        # Check conflicting settings
        if config.require_both_in_and_out and config.enable_minimum_working_hours_rule:
            warnings.append('Both "Require In/Out" and "Minimum Hours" rules active - may conflict')
        
        return JsonResponse({
            'success': True,
            'config_name': config.name,
            'issues': issues,
            'warnings': warnings,
            'message': 'Configuration validated'
        })
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})