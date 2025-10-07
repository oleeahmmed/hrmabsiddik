# views.py
"""
Attendance Log Reports - Enhanced with Employee Monthly Details and Payroll Summary
Based on active AttendanceProcessorConfiguration settings
"""

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.db.models import Count, Q, Avg, Sum, F, Min, Max, Case, When
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
import csv
import logging
import calendar

from ..models import (
    AttendanceLog, Employee, Department, Shift, 
    Company, AttendanceProcessorConfiguration, Location, Holiday,
    LeaveApplication
)

logger = logging.getLogger(__name__)


class BaseAttendanceLogReportView(LoginRequiredMixin, View):
    """Base view for all attendance log reports"""
    
    def get_company(self, request):
        """Get company from request"""
        try:
            return Company.objects.first()
        except Exception as e:
            logger.error(f"Error getting company: {str(e)}")
            return None
    
    def get_active_config(self, company):
        """Get active attendance processor configuration"""
        if not company:
            return None
        return AttendanceProcessorConfiguration.get_active_config(company)
    
    def get_date_range(self, request):
        """Parse and validate date range from request"""
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        today = timezone.now().date()
        
        if not start_date_str or not end_date_str:
            start_date = today.replace(day=1)
            end_date = today
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                start_date = today.replace(day=1)
                end_date = today
        
        return start_date, end_date
    
    def get_filters(self, request):
        """Get common filters from request"""
        return {
            'department_id': request.GET.get('department', ''),
            'employee_id': request.GET.get('employee', ''),
            'source_type': request.GET.get('source_type', ''),
        }
    
    def is_weekend(self, date_obj, config):
        """Check if date is weekend based on config"""
        if not config:
            return date_obj.weekday() == 4  # Default Friday
        
        weekday = date_obj.weekday()
        return weekday in config.weekend_days
    
    def is_holiday(self, date_obj, company):
        """Check if date is a holiday"""
        return Holiday.objects.filter(company=company, date=date_obj).exists()
    
    def get_holiday_name(self, date_obj, company):
        """Get holiday name if exists"""
        try:
            holiday = Holiday.objects.get(company=company, date=date_obj)
            return holiday.name
        except Holiday.DoesNotExist:
            return None
    
    def is_on_leave(self, date_obj, employee):
        """Check if employee is on leave"""
        return LeaveApplication.objects.filter(
            employee=employee,
            start_date__lte=date_obj,
            end_date__gte=date_obj,
            status='A'  # Approved
        ).exists()
    
    def get_leave_type(self, date_obj, employee):
        """Get leave type if employee is on leave"""
        try:
            leave = LeaveApplication.objects.get(
                employee=employee,
                start_date__lte=date_obj,
                end_date__gte=date_obj,
                status='A'
            )
            return leave.leave_type.name
        except LeaveApplication.DoesNotExist:
            return None
    
    def calculate_work_hours(self, first_punch, last_punch, config):
        """Calculate work hours with break deduction"""
        if not first_punch or not last_punch or first_punch == last_punch:
            return 0.0
        
        duration = last_punch - first_punch
        work_hours = duration.total_seconds() / 3600
        
        # Deduct break time
        if config:
            break_minutes = config.default_break_minutes
            work_hours -= (break_minutes / 60)
        
        return max(work_hours, 0.0)
    
    def calculate_overtime(self, work_hours, expected_hours, config, is_weekend=False, is_holiday=False):
        """Calculate overtime hours based on config"""
        if not config:
            if work_hours <= expected_hours:
                return 0.0
            return work_hours - expected_hours
        
        # Weekend/Holiday full day overtime
        if is_weekend and config.weekend_overtime_full_day:
            return work_hours
        
        if is_holiday and config.holiday_overtime_full_day:
            return work_hours
        
        # Regular overtime calculation
        if work_hours <= expected_hours:
            return 0.0
        
        overtime = work_hours - expected_hours
        
        # Apply minimum overtime rule
        if overtime * 60 < config.minimum_overtime_minutes:
            return 0.0
        
        return overtime
    
    def determine_status(self, date_obj, employee, day_logs, config, company):
        """Determine attendance status based on logs and config"""
        # Check leave first
        if self.is_on_leave(date_obj, employee):
            leave_type = self.get_leave_type(date_obj, employee)
            return 'L', f'Leave ({leave_type})'
        
        # Check weekend
        if self.is_weekend(date_obj, config):
            if day_logs.exists():
                return 'W', 'Weekly Off (Worked)'
            return 'W', 'Weekly Off'
        
        # Check holiday
        if self.is_holiday(date_obj, company):
            holiday_name = self.get_holiday_name(date_obj, company)
            if day_logs.exists():
                return 'H', f'Holiday (Worked) - {holiday_name}'
            return 'H', f'Holiday - {holiday_name}'
        
        # No logs - Absent
        if not day_logs.exists():
            return 'A', 'Absent'
        
        first_punch = day_logs.first().timestamp
        last_punch = day_logs.last().timestamp
        
        # Calculate work hours
        work_hours = self.calculate_work_hours(first_punch, last_punch, config)
        
        # Apply config rules
        if config:
            # Rule: Require both in and out
            if config.require_both_in_and_out and day_logs.count() == 1:
                return 'A', 'Absent (Missing Punch)'
            
            # Rule: Minimum working hours
            if config.enable_minimum_working_hours_rule:
                if work_hours < config.minimum_working_hours_for_present:
                    return 'A', f'Absent (Insufficient Hours: {work_hours:.2f}h)'
            
            # Rule: Half day
            if config.enable_working_hours_half_day_rule:
                if config.half_day_minimum_hours <= work_hours <= config.half_day_maximum_hours:
                    return 'HD', 'Half Day'
        
        # Default: Present
        return 'P', 'Present'
    
    def check_late_arrival(self, check_in_time, shift, date_obj, config):
        """Check if employee arrived late"""
        if not shift or not check_in_time:
            return False, 0
        
        shift_start = timezone.datetime.combine(date_obj, shift.start_time)
        shift_start = timezone.make_aware(shift_start)
        
        grace_minutes = config.grace_minutes if config else 15
        grace_time = shift_start + timedelta(minutes=grace_minutes)
        
        if check_in_time > grace_time:
            late_minutes = int((check_in_time - shift_start).total_seconds() / 60)
            return True, late_minutes
        
        return False, 0
    
    def check_early_departure(self, check_out_time, shift, date_obj, config):
        """Check if employee left early"""
        if not shift or not check_out_time:
            return False, 0
        
        shift_end = timezone.datetime.combine(date_obj, shift.end_time)
        shift_end = timezone.make_aware(shift_end)
        
        # Handle overnight shifts
        if shift.end_time < shift.start_time:
            shift_end += timedelta(days=1)
        
        threshold_minutes = config.early_out_threshold_minutes if config else 30
        early_threshold = shift_end - timedelta(minutes=threshold_minutes)
        
        if check_out_time < early_threshold:
            early_minutes = int((shift_end - check_out_time).total_seconds() / 60)
            return True, early_minutes
        
        return False, 0


class AttendanceLogDashboardView(BaseAttendanceLogReportView):
    """Main dashboard for attendance log reports"""
    
    def get(self, request):
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        if not company:
            context = {'error_message': 'No company found'}
            return render(request, 'zkteco/attendance_logs/dashboard.html', context)
        
        # Get summary statistics
        today = timezone.now().date()
        
        # Today's statistics
        logs_today = AttendanceLog.objects.filter(
            timestamp__date=today
        ).count()
        
        employees_present_today = AttendanceLog.objects.filter(
            timestamp__date=today
        ).values('employee').distinct().count()
        
        # This month statistics
        logs_this_month = AttendanceLog.objects.filter(
            timestamp__year=today.year,
            timestamp__month=today.month
        ).count()
        
        # Source type distribution (this month)
        source_distribution = AttendanceLog.objects.filter(
            timestamp__year=today.year,
            timestamp__month=today.month
        ).values('source_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Department-wise attendance (today)
        dept_attendance = AttendanceLog.objects.filter(
            timestamp__date=today
        ).values('employee__department__name').annotate(
            count=Count('employee', distinct=True)
        ).order_by('-count')
        
        # Total active employees
        total_employees = Employee.objects.filter(is_active=True).count()
        
        context = {
            'company': company,
            'active_config': active_config,
            'today': today,
            'logs_today': logs_today,
            'employees_present_today': employees_present_today,
            'total_employees': total_employees,
            'logs_this_month': logs_this_month,
            'source_distribution': source_distribution,
            'dept_attendance': dept_attendance,
        }
        
        return render(request, 'zkteco/attendance_logs/dashboard.html', context)


class DailyAttendanceLogReportView(BaseAttendanceLogReportView):
    """Daily attendance report from AttendanceLog"""
    
    def get(self, request):
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        if not company:
            context = {'error_message': 'No company found'}
            return render(request, 'zkteco/attendance_logs/daily_report.html', context)
        
        # Get parameters
        report_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
        filters = self.get_filters(request)
        
        # Parse date
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except ValueError:
            report_date = timezone.now().date()
        
        # Get all attendance logs for the date
        logs = AttendanceLog.objects.filter(
            timestamp__date=report_date
        ).select_related('employee', 'employee__department', 'employee__designation')
        
        # Apply filters
        if filters['department_id']:
            logs = logs.filter(employee__department_id=filters['department_id'])
        
        if filters['employee_id']:
            logs = logs.filter(employee_id=filters['employee_id'])
        
        # Get employees to process
        if filters['employee_id']:
            employees = Employee.objects.filter(id=filters['employee_id'], is_active=True)
        elif filters['department_id']:
            employees = Employee.objects.filter(
                department_id=filters['department_id'], 
                is_active=True
            )
        else:
            # Get all employees who have logs OR all active employees
            employee_ids = logs.values_list('employee_id', flat=True).distinct()
            employees = Employee.objects.filter(
                Q(id__in=employee_ids) | Q(is_active=True)
            ).distinct()
        
        # Process attendance data
        report_data = []
        present_count = 0
        absent_count = 0
        weekly_off_count = 0
        holiday_count = 0
        leave_count = 0
        total_work_hours = 0.0
        total_overtime_hours = 0.0
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee).order_by('timestamp')
            
            # Determine status
            status_code, status_display = self.determine_status(
                report_date, employee, employee_logs, active_config, company
            )
            
            # Get first and last punch
            if employee_logs.exists():
                first_punch = employee_logs.first().timestamp
                last_punch = employee_logs.last().timestamp
                check_in = first_punch.strftime('%I:%M %p')
                check_out = last_punch.strftime('%I:%M %p')
                total_punches = employee_logs.count()
                
                # Calculate work hours
                work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                
                # Check late/early
                is_late, late_minutes = self.check_late_arrival(
                    first_punch, employee.default_shift, report_date, active_config
                )
                is_early, early_minutes = self.check_early_departure(
                    last_punch, employee.default_shift, report_date, active_config
                )
                
                # Calculate overtime
                expected_hours = employee.expected_working_hours or 8.0
                is_weekend = self.is_weekend(report_date, active_config)
                is_holiday = self.is_holiday(report_date, company)
                overtime_hours = self.calculate_overtime(
                    work_hours, expected_hours, active_config, is_weekend, is_holiday
                )
            else:
                check_in = '-'
                check_out = '-'
                total_punches = 0
                work_hours = 0.0
                overtime_hours = 0.0
                is_late = False
                late_minutes = 0
                is_early = False
                early_minutes = 0
            
            # Count statuses
            if status_code == 'P':
                present_count += 1
                total_work_hours += work_hours
                total_overtime_hours += overtime_hours
            elif status_code == 'A':
                absent_count += 1
            elif status_code == 'W':
                weekly_off_count += 1
                if employee_logs.exists():
                    total_overtime_hours += work_hours
            elif status_code == 'H':
                holiday_count += 1
                if employee_logs.exists():
                    total_overtime_hours += work_hours
            elif status_code == 'L':
                leave_count += 1
            
            # Get shift
            shift_name = employee.default_shift.name if employee.default_shift else 'No Shift'
            
            report_data.append({
                'employee_id': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'No Department',
                'designation': employee.designation.name if employee.designation else 'No Designation',
                'shift': shift_name,
                'check_in': check_in,
                'check_out': check_out,
                'total_punches': total_punches,
                'status': status_display,
                'status_code': status_code,
                'work_hours': round(work_hours, 2),
                'overtime_hours': round(overtime_hours, 2),
                'is_late': is_late,
                'late_minutes': late_minutes,
                'is_early': is_early,
                'early_minutes': early_minutes,
            })
        
        # Summary
        summary = {
            'total_employees': len(report_data),
            'present_count': present_count,
            'absent_count': absent_count,
            'leave_count': leave_count,
            'weekly_off_count': weekly_off_count,
            'holiday_count': holiday_count,
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime_hours, 2),
        }
        
        # Get filter options
        departments = Department.objects.filter(company=company).order_by('name')
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        
        context = {
            'company': company,
            'active_config': active_config,
            'report_data': report_data,
            'summary': summary,
            'selected_date': report_date,
            'departments': departments,
            'employees': employees_list,
            'filters': filters,
            'report_title': f'Daily Attendance Report - {report_date.strftime("%B %d, %Y")}'
        }
        
        return render(request, 'zkteco/attendance_logs/daily_report.html', context)


class MonthlyAttendanceLogReportView(BaseAttendanceLogReportView):
    """Monthly attendance summary from AttendanceLog"""
    
    def get(self, request):
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        if not company:
            context = {'error_message': 'No company found'}
            return render(request, 'zkteco/attendance_logs/monthly_report.html', context)
        
        # Get parameters
        start_date, end_date = self.get_date_range(request)
        filters = self.get_filters(request)
        
        # Get all logs for the period
        logs = AttendanceLog.objects.filter(
            timestamp__date__range=[start_date, end_date]
        ).select_related('employee', 'employee__department')
        
        # Apply filters
        if filters['department_id']:
            logs = logs.filter(employee__department_id=filters['department_id'])
        
        if filters['employee_id']:
            logs = logs.filter(employee_id=filters['employee_id'])
        
        # Get employees
        if filters['employee_id']:
            employees = Employee.objects.filter(id=filters['employee_id'], is_active=True)
        elif filters['department_id']:
            employees = Employee.objects.filter(
                department_id=filters['department_id'], 
                is_active=True
            )
        else:
            employee_ids = logs.values_list('employee_id', flat=True).distinct()
            employees = Employee.objects.filter(
                Q(id__in=employee_ids) | Q(is_active=True)
            ).distinct()
        
        # Process monthly data
        report_data = []
        total_days = (end_date - start_date).days + 1
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee)
            
            # Initialize counters
            present_days = 0
            absent_days = 0
            weekly_off_days = 0
            holiday_days = 0
            leave_days = 0
            half_days = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            late_arrivals = 0
            early_departures = 0
            
            # Process each day
            current_date = start_date
            while current_date <= end_date:
                day_logs = employee_logs.filter(
                    timestamp__date=current_date
                ).order_by('timestamp')
                
                # Determine status
                status_code, status_display = self.determine_status(
                    current_date, employee, day_logs, active_config, company
                )
                
                # Count statuses
                if status_code == 'P':
                    present_days += 1
                    
                    # Calculate work hours
                    if day_logs.exists():
                        first_punch = day_logs.first().timestamp
                        last_punch = day_logs.last().timestamp
                        work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                        total_work_hours += work_hours
                        
                        # Calculate overtime
                        expected_hours = employee.expected_working_hours or 8.0
                        overtime = self.calculate_overtime(
                            work_hours, expected_hours, active_config, False, False
                        )
                        total_overtime_hours += overtime
                        
                        # Check late/early
                        is_late, _ = self.check_late_arrival(
                            first_punch, employee.default_shift, current_date, active_config
                        )
                        is_early, _ = self.check_early_departure(
                            last_punch, employee.default_shift, current_date, active_config
                        )
                        
                        if is_late:
                            late_arrivals += 1
                        if is_early:
                            early_departures += 1
                        
                elif status_code == 'A':
                    absent_days += 1
                elif status_code == 'W':
                    weekly_off_days += 1
                    # If worked on weekend, count as overtime
                    if day_logs.exists():
                        first_punch = day_logs.first().timestamp
                        last_punch = day_logs.last().timestamp
                        work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                        overtime = self.calculate_overtime(
                            work_hours, employee.expected_working_hours or 8.0, 
                            active_config, True, False
                        )
                        total_overtime_hours += overtime
                elif status_code == 'H':
                    holiday_days += 1
                    # If worked on holiday, count as overtime
                    if day_logs.exists():
                        first_punch = day_logs.first().timestamp
                        last_punch = day_logs.last().timestamp
                        work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                        overtime = self.calculate_overtime(
                            work_hours, employee.expected_working_hours or 8.0, 
                            active_config, False, True
                        )
                        total_overtime_hours += overtime
                elif status_code == 'L':
                    leave_days += 1
                elif status_code == 'HD':
                    half_days += 1
                    present_days += 0.5
                    
                    if day_logs.exists():
                        first_punch = day_logs.first().timestamp
                        last_punch = day_logs.last().timestamp
                        work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                        total_work_hours += work_hours
                
                current_date += timedelta(days=1)
            
            # Calculate attendance percentage
            working_days = total_days - weekly_off_days - holiday_days
            attendance_percentage = (present_days / max(working_days, 1)) * 100 if working_days > 0 else 0
            
            report_data.append({
                'employee_id': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'No Department',
                'total_days': total_days,
                'working_days': working_days,
                'present_days': round(present_days, 1),
                'absent_days': absent_days,
                'leave_days': leave_days,
                'weekly_off_days': weekly_off_days,
                'holiday_days': holiday_days,
                'half_days': half_days,
                'late_arrivals': late_arrivals,
                'early_departures': early_departures,
                'total_work_hours': round(total_work_hours, 2),
                'total_overtime_hours': round(total_overtime_hours, 2),
                'avg_daily_hours': round(total_work_hours / max(present_days, 1), 2),
                'attendance_percentage': round(attendance_percentage, 1),
            })
        
        # Summary
        summary = {
            'total_employees': len(report_data),
            'date_range_days': total_days,
            'total_present_days': sum([emp['present_days'] for emp in report_data]),
            'total_absent_days': sum([emp['absent_days'] for emp in report_data]),
            'total_leave_days': sum([emp['leave_days'] for emp in report_data]),
            'total_work_hours': sum([emp['total_work_hours'] for emp in report_data]),
            'total_overtime_hours': sum([emp['total_overtime_hours'] for emp in report_data]),
            'avg_attendance_percentage': round(
                sum([emp['attendance_percentage'] for emp in report_data]) / max(len(report_data), 1), 1
            ),
        }
        
        # Get filter options
        departments = Department.objects.filter(company=company).order_by('name')
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        
        context = {
            'company': company,
            'active_config': active_config,
            'report_data': report_data,
            'summary': summary,
            'start_date': start_date,
            'end_date': end_date,
            'departments': departments,
            'employees': employees_list,
            'filters': filters,
            'report_title': f'Monthly Attendance Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
        }
        
        return render(request, 'zkteco/attendance_logs/monthly_report.html', context)


class EmployeeMonthlyDetailReportView(BaseAttendanceLogReportView):
    """Detailed monthly report for a single employee with daily breakdown"""
    
    def get(self, request):
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        if not company:
            context = {'error_message': 'No company found'}
            return render(request, 'zkteco/attendance_logs/employee_detail_report.html', context)
        
        # Get parameters
        employee_id = request.GET.get('employee')
        month_str = request.GET.get('month')  # Format: YYYY-MM
        
        # Validate employee
        if not employee_id:
            employees = Employee.objects.filter(is_active=True).order_by('name')
            context = {
                'company': company,
                'employees': employees,
                'error_message': 'Please select an employee'
            }
            return render(request, 'zkteco/attendance_logs/employee_detail_report.html', context)
        
        try:
            employee = Employee.objects.select_related(
                'department', 'designation', 'default_shift'
            ).get(id=employee_id)
        except Employee.DoesNotExist:
            context = {'error_message': 'Employee not found'}
            return render(request, 'zkteco/attendance_logs/employee_detail_report.html', context)
        
        # Parse month
        if month_str:
            try:
                year, month = map(int, month_str.split('-'))
                start_date = date(year, month, 1)
            except ValueError:
                today = timezone.now().date()
                start_date = today.replace(day=1)
        else:
            today = timezone.now().date()
            start_date = today.replace(day=1)
        
        # Calculate end date (last day of month)
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        end_date = date(start_date.year, start_date.month, last_day)
        
        # Get all logs for the employee in this month
        logs = AttendanceLog.objects.filter(
            employee=employee,
            timestamp__date__range=[start_date, end_date]
        ).order_by('timestamp')
        
        # Process daily attendance
        daily_records = []
        total_present = 0
        total_absent = 0
        total_leave = 0
        total_weekend = 0
        total_holiday = 0
        total_half_day = 0
        total_work_hours = 0.0
        total_overtime_hours = 0.0
        total_late = 0
        total_early = 0
        late_minutes_sum = 0
        early_minutes_sum = 0
        
        current_date = start_date
        while current_date <= end_date:
            day_logs = logs.filter(timestamp__date=current_date).order_by('timestamp')
            
            # Determine status
            status_code, status_display = self.determine_status(
                current_date, employee, day_logs, active_config, company
            )
            
            # Get punch details
            if day_logs.exists():
                first_punch = day_logs.first().timestamp
                last_punch = day_logs.last().timestamp
                check_in = first_punch.strftime('%I:%M %p')
                check_out = last_punch.strftime('%I:%M %p')
                punch_count = day_logs.count()
                
                # Get all punch times
                punch_times = [log.timestamp.strftime('%I:%M %p') for log in day_logs]
                
                # Calculate work hours
                work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                
                # Check late/early
                is_late, late_minutes = self.check_late_arrival(
                    first_punch, employee.default_shift, current_date, active_config
                )
                is_early, early_minutes = self.check_early_departure(
                    last_punch, employee.default_shift, current_date, active_config
                )
                
                # Calculate overtime
                expected_hours = employee.expected_working_hours or 8.0
                is_weekend = self.is_weekend(current_date, active_config)
                is_holiday = self.is_holiday(current_date, company)
                overtime_hours = self.calculate_overtime(
                    work_hours, expected_hours, active_config, is_weekend, is_holiday
                )
                
                if is_late:
                    total_late += 1
                    late_minutes_sum += late_minutes
                
                if is_early:
                    total_early += 1
                    early_minutes_sum += early_minutes
            else:
                check_in = '-'
                check_out = '-'
                punch_count = 0
                punch_times = []
                work_hours = 0.0
                overtime_hours = 0.0
                is_late = False
                late_minutes = 0
                is_early = False
                early_minutes = 0
            
            # Count status
            if status_code == 'P':
                total_present += 1
                total_work_hours += work_hours
                total_overtime_hours += overtime_hours
            elif status_code == 'A':
                total_absent += 1
            elif status_code == 'L':
                total_leave += 1
            elif status_code == 'W':
                total_weekend += 1
                if day_logs.exists():
                    total_overtime_hours += overtime_hours
            elif status_code == 'H':
                total_holiday += 1
                if day_logs.exists():
                    total_overtime_hours += overtime_hours
            elif status_code == 'HD':
                total_half_day += 1
                total_present += 0.5
                total_work_hours += work_hours
            
            # Get day name
            day_name = current_date.strftime('%A')
            
            daily_records.append({
                'date': current_date,
                'day_name': day_name,
                'check_in': check_in,
                'check_out': check_out,
                'punch_count': punch_count,
                'punch_times': ', '.join(punch_times) if punch_times else '-',
                'work_hours': round(work_hours, 2),
                'overtime_hours': round(overtime_hours, 2),
                'status_code': status_code,
                'status_display': status_display,
                'is_late': is_late,
                'late_minutes': late_minutes,
                'is_early': is_early,
                'early_minutes': early_minutes,
            })
            
            current_date += timedelta(days=1)
        
        # Calculate attendance percentage
        total_days_count = len(daily_records)
        working_days = total_days_count - total_weekend - total_holiday
        attendance_percentage = (total_present / max(working_days, 1)) * 100 if working_days > 0 else 0
        
        # Summary
        summary = {
            'total_days': total_days_count,
            'working_days': working_days,
            'present_days': round(total_present, 1),
            'absent_days': total_absent,
            'leave_days': total_leave,
            'weekend_days': total_weekend,
            'holiday_days': total_holiday,
            'half_days': total_half_day,
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime_hours, 2),
            'avg_daily_hours': round(total_work_hours / max(total_present, 1), 2),
            'attendance_percentage': round(attendance_percentage, 1),
            'late_count': total_late,
            'early_departure_count': total_early,
            'avg_late_minutes': round(late_minutes_sum / max(total_late, 1), 1),
            'avg_early_minutes': round(early_minutes_sum / max(total_early, 1), 1),
        }
        
        # Employee details
        employees = Employee.objects.filter(is_active=True).order_by('name')
        
        context = {
            'company': company,
            'active_config': active_config,
            'employee': employee,
            'employees': employees,
            'daily_records': daily_records,
            'summary': summary,
            'selected_month': start_date.strftime('%Y-%m'),
            'month_name': start_date.strftime('%B %Y'),
            'report_title': f'Employee Monthly Detail Report - {employee.name} - {start_date.strftime("%B %Y")}'
        }
        
        return render(request, 'zkteco/attendance_logs/employee_detail_report.html', context)


class EmployeePayrollSummaryReportView(BaseAttendanceLogReportView):
    """Comprehensive payroll summary report with salary calculations"""
    
    def get(self, request):
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        if not company:
            context = {'error_message': 'No company found'}
            return render(request, 'zkteco/attendance_logs/payroll_summary.html', context)
        
        # Get parameters
        start_date, end_date = self.get_date_range(request)
        filters = self.get_filters(request)
        
        # Get all logs for the period
        logs = AttendanceLog.objects.filter(
            timestamp__date__range=[start_date, end_date]
        ).select_related('employee', 'employee__department')
        
        # Apply filters
        if filters['department_id']:
            logs = logs.filter(employee__department_id=filters['department_id'])
        
        if filters['employee_id']:
            logs = logs.filter(employee_id=filters['employee_id'])
        
        # Get employees
        if filters['employee_id']:
            employees = Employee.objects.filter(id=filters['employee_id'], is_active=True)
        elif filters['department_id']:
            employees = Employee.objects.filter(
                department_id=filters['department_id'], 
                is_active=True
            )
        else:
            employee_ids = logs.values_list('employee_id', flat=True).distinct()
            employees = Employee.objects.filter(
                Q(id__in=employee_ids) | Q(is_active=True)
            ).distinct()
        
        # Process payroll data
        payroll_data = []
        total_basic_salary = Decimal('0.00')
        total_allowances = Decimal('0.00')
        total_deductions = Decimal('0.00')
        total_overtime_pay = Decimal('0.00')
        total_hourly_wage = Decimal('0.00')
        total_gross_pay = Decimal('0.00')
        total_net_pay = Decimal('0.00')
        
        total_days = (end_date - start_date).days + 1
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee)
            
            # Initialize counters
            present_days = 0
            absent_days = 0
            leave_days = 0
            half_days = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            
            # Process each day
            current_date = start_date
            while current_date <= end_date:
                day_logs = employee_logs.filter(
                    timestamp__date=current_date
                ).order_by('timestamp')
                
                # Determine status
                status_code, status_display = self.determine_status(
                    current_date, employee, day_logs, active_config, company
                )
                
                # Calculate hours
                if day_logs.exists():
                    first_punch = day_logs.first().timestamp
                    last_punch = day_logs.last().timestamp
                    work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                    
                    expected_hours = employee.expected_working_hours or 8.0
                    is_weekend = self.is_weekend(current_date, active_config)
                    is_holiday = self.is_holiday(current_date, company)
                    overtime = self.calculate_overtime(
                        work_hours, expected_hours, active_config, is_weekend, is_holiday
                    )
                    
                    if status_code == 'P':
                        total_work_hours += work_hours
                        total_overtime_hours += overtime
                    elif status_code in ['W', 'H']:
                        # Weekend/Holiday work counts as overtime
                        total_overtime_hours += overtime
                    elif status_code == 'HD':
                        total_work_hours += work_hours
                
                # Count status
                if status_code == 'P':
                    present_days += 1
                elif status_code == 'A':
                    absent_days += 1
                elif status_code == 'L':
                    leave_days += 1
                elif status_code == 'HD':
                    half_days += 1
                    present_days += 0.5
                
                current_date += timedelta(days=1)
            
            # Calculate salary components
            basic_salary = employee.basic_salary or Decimal('0.00')
            
            # Allowances
            house_rent = employee.house_rent_allowance or Decimal('0.00')
            medical = employee.medical_allowance or Decimal('0.00')
            conveyance = employee.conveyance_allowance or Decimal('0.00')
            food = employee.food_allowance or Decimal('0.00')
            attendance_bonus = employee.attendance_bonus or Decimal('0.00')
            festival_bonus = employee.festival_bonus or Decimal('0.00')
            
            total_allowance = house_rent + medical + conveyance + food + attendance_bonus + festival_bonus
            
            # Deductions
            provident_fund = employee.provident_fund or Decimal('0.00')
            tax = employee.tax_deduction or Decimal('0.00')
            loan = employee.loan_deduction or Decimal('0.00')
            
            total_deduction = provident_fund + tax + loan
            
            # Calculate overtime pay
            overtime_rate = employee.get_overtime_rate()
            overtime_pay = Decimal(str(total_overtime_hours)) * Decimal(str(overtime_rate))
            
            # Calculate hourly wage based on actual work hours
            per_hour_rate = employee.get_per_hour_rate()
            hourly_wage = Decimal(str(total_work_hours)) * Decimal(str(per_hour_rate))
            
            # Gross pay = Basic + Allowances + Overtime Pay
            gross_pay = basic_salary + total_allowance + overtime_pay
            
            # Net pay = Gross - Deductions
            net_pay = gross_pay - total_deduction
            
            # Absence deduction (if applicable)
            working_days = total_days - sum([
                1 for d in range(total_days) 
                if self.is_weekend(start_date + timedelta(days=d), active_config) or 
                   self.is_holiday(start_date + timedelta(days=d), company)
            ])
            
            if working_days > 0:
                per_day_salary = basic_salary / Decimal(str(working_days))
                absence_deduction = per_day_salary * Decimal(str(absent_days))
            else:
                absence_deduction = Decimal('0.00')
            
            # Adjust net pay for absences
            net_pay_adjusted = net_pay - absence_deduction
            
            payroll_data.append({
                'employee_id': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'No Department',
                'designation': employee.designation.name if employee.designation else 'No Designation',
                'present_days': round(present_days, 1),
                'absent_days': absent_days,
                'leave_days': leave_days,
                'half_days': half_days,
                'total_work_hours': round(total_work_hours, 2),
                'total_overtime_hours': round(total_overtime_hours, 2),
                'basic_salary': float(basic_salary),
                'house_rent': float(house_rent),
                'medical': float(medical),
                'conveyance': float(conveyance),
                'food': float(food),
                'attendance_bonus': float(attendance_bonus),
                'festival_bonus': float(festival_bonus),
                'total_allowance': float(total_allowance),
                'provident_fund': float(provident_fund),
                'tax': float(tax),
                'loan': float(loan),
                'total_deduction': float(total_deduction),
                'overtime_pay': float(overtime_pay),
                'hourly_wage': float(hourly_wage),
                'absence_deduction': float(absence_deduction),
                'gross_pay': float(gross_pay),
                'net_pay': float(net_pay_adjusted),
                'per_hour_rate': float(per_hour_rate),
                'overtime_rate': float(overtime_rate),
            })
            
            # Add to totals
            total_basic_salary += basic_salary
            total_allowances += total_allowance
            total_deductions += total_deduction
            total_overtime_pay += overtime_pay
            total_hourly_wage += hourly_wage
            total_gross_pay += gross_pay
            total_net_pay += net_pay_adjusted
        
        # Summary
        summary = {
            'total_employees': len(payroll_data),
            'date_range_days': total_days,
            'total_basic_salary': float(total_basic_salary),
            'total_allowances': float(total_allowances),
            'total_deductions': float(total_deductions),
            'total_overtime_pay': float(total_overtime_pay),
            'total_hourly_wage': float(total_hourly_wage),
            'total_gross_pay': float(total_gross_pay),
            'total_net_pay': float(total_net_pay),
        }
        
        # Get filter options
        departments = Department.objects.filter(company=company).order_by('name')
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        
        context = {
            'company': company,
            'active_config': active_config,
            'payroll_data': payroll_data,
            'summary': summary,
            'start_date': start_date,
            'end_date': end_date,
            'departments': departments,
            'employees': employees_list,
            'filters': filters,
            'report_title': f'Payroll Summary Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
        }
        
        return render(request, 'zkteco/attendance_logs/payroll_summary.html', context)


class ExportAttendanceReportView(BaseAttendanceLogReportView):
    """Export attendance reports to CSV"""
    
    def get(self, request):
        report_type = request.GET.get('type', 'daily')
        
        if report_type == 'daily':
            return self.export_daily_report(request)
        elif report_type == 'monthly':
            return self.export_monthly_report(request)
        elif report_type == 'employee_detail':
            return self.export_employee_detail_report(request)
        elif report_type == 'payroll':
            return self.export_payroll_report(request)
        else:
            return HttpResponse("Invalid report type", status=400)
    
    def export_daily_report(self, request):
        """Export daily attendance report to CSV"""
        company = self.get_company(request)
        active_config = self.get_active_config(company)
        
        report_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="daily_attendance_{report_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee ID', 'Employee Name', 'Department', 'Designation', 
            'Shift', 'Check In', 'Check Out', 'Total Punches', 
            'Work Hours', 'Overtime Hours', 'Status', 'Late', 'Early Departure'
        ])
        
        # Get data
        logs = AttendanceLog.objects.filter(
            timestamp__date=report_date
        ).select_related('employee', 'employee__department', 'employee__designation')
        
        employees = Employee.objects.filter(is_active=True)
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee).order_by('timestamp')
            status_code, status_display = self.determine_status(
                report_date, employee, employee_logs, active_config, company
            )
            
            if employee_logs.exists():
                first_punch = employee_logs.first().timestamp
                last_punch = employee_logs.last().timestamp
                check_in = first_punch.strftime('%I:%M %p')
                check_out = last_punch.strftime('%I:%M %p')
                work_hours = self.calculate_work_hours(first_punch, last_punch, active_config)
                
                is_late, late_min = self.check_late_arrival(
                    first_punch, employee.default_shift, report_date, active_config
                )
                is_early, early_min = self.check_early_departure(
                    last_punch, employee.default_shift, report_date, active_config
                )
                
                expected_hours = employee.expected_working_hours or 8.0
                overtime = self.calculate_overtime(work_hours, expected_hours, active_config)
            else:
                check_in = '-'
                check_out = '-'
                work_hours = 0
                overtime = 0
                is_late = False
                is_early = False
                late_min = 0
                early_min = 0
            
            writer.writerow([
                employee.employee_id,
                employee.name,
                employee.department.name if employee.department else 'N/A',
                employee.designation.name if employee.designation else 'N/A',
                employee.default_shift.name if employee.default_shift else 'N/A',
                check_in,
                check_out,
                employee_logs.count(),
                round(work_hours, 2),
                round(overtime, 2),
                status_display,
                f'Yes ({late_min} min)' if is_late else 'No',
                f'Yes ({early_min} min)' if is_early else 'No',
            ])
        
        return response
    
    def export_monthly_report(self, request):
        """Export monthly attendance report to CSV"""
        company = self.get_company(request)
        start_date, end_date = self.get_date_range(request)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="monthly_attendance_{start_date}_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee ID', 'Employee Name', 'Department', 'Total Days', 
            'Working Days', 'Present Days', 'Absent Days', 'Leave Days',
            'Weekend Days', 'Holiday Days', 'Half Days', 'Late Arrivals',
            'Early Departures', 'Total Work Hours', 'Total Overtime Hours',
            'Avg Daily Hours', 'Attendance %'
        ])
        
        # Get data
        logs = AttendanceLog.objects.filter(
            timestamp__date__range=[start_date, end_date]
        ).select_related('employee', 'employee__department')
        
        employees = Employee.objects.filter(is_active=True)
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee)
            
            # Initialize counters
            present_days = 0
            absent_days = 0
            weekly_off_days = 0
            holiday_days = 0
            leave_days = 0
            half_days = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            late_arrivals = 0
            early_departures = 0
            
            # Process each day
            current_date = start_date
            while current_date <= end_date:
                day_logs = employee_logs.filter(
                    timestamp__date=current_date
                ).order_by('timestamp')
                
                status_code, _ = self.determine_status(
                    current_date, employee, day_logs, None, company
                )
                
                if status_code == 'P':
                    present_days += 1
                    if day_logs.exists():
                        first_punch = day_logs.first().timestamp
                        last_punch = day_logs.last().timestamp
                        work_hours = self.calculate_work_hours(first_punch, last_punch, None)
                        total_work_hours += work_hours
                elif status_code == 'A':
                    absent_days += 1
                elif status_code == 'W':
                    weekly_off_days += 1
                elif status_code == 'H':
                    holiday_days += 1
                elif status_code == 'L':
                    leave_days += 1
                elif status_code == 'HD':
                    half_days += 1
                    present_days += 0.5
                
                current_date += timedelta(days=1)
            
            # Calculate attendance percentage
            total_days_count = (end_date - start_date).days + 1
            working_days = total_days_count - weekly_off_days - holiday_days
            attendance_percentage = (present_days / max(working_days, 1)) * 100 if working_days > 0 else 0
            
            writer.writerow([
                employee.employee_id,
                employee.name,
                employee.department.name if employee.department else 'N/A',
                total_days_count,
                working_days,
                round(present_days, 1),
                absent_days,
                leave_days,
                weekly_off_days,
                holiday_days,
                half_days,
                late_arrivals,
                early_departures,
                round(total_work_hours, 2),
                round(total_overtime_hours, 2),
                round(total_work_hours / max(present_days, 1), 2),
                round(attendance_percentage, 1),
            ])
        
        return response
    
    def export_employee_detail_report(self, request):
        """Export employee detail report to CSV"""
        employee_id = request.GET.get('employee')
        month_str = request.GET.get('month')
        
        if not employee_id or not month_str:
            return HttpResponse("Employee ID and Month are required", status=400)
        
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return HttpResponse("Employee not found", status=404)
        
        try:
            year, month = map(int, month_str.split('-'))
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)
        except ValueError:
            return HttpResponse("Invalid month format. Use YYYY-MM", status=400)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="employee_detail_{employee_id}_{month_str}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Day', 'Check In', 'Check Out', 'Punch Count',
            'Work Hours', 'Overtime Hours', 'Status', 'Late', 'Early Departure'
        ])
        
        # Get data
        logs = AttendanceLog.objects.filter(
            employee=employee,
            timestamp__date__range=[start_date, end_date]
        ).order_by('timestamp')
        
        current_date = start_date
        while current_date <= end_date:
            day_logs = logs.filter(timestamp__date=current_date).order_by('timestamp')
            
            if day_logs.exists():
                first_punch = day_logs.first().timestamp
                last_punch = day_logs.last().timestamp
                check_in = first_punch.strftime('%I:%M %p')
                check_out = last_punch.strftime('%I:%M %p')
                work_hours = self.calculate_work_hours(first_punch, last_punch, None)
                
                is_late, late_min = self.check_late_arrival(
                    first_punch, employee.default_shift, current_date, None
                )
                is_early, early_min = self.check_early_departure(
                    last_punch, employee.default_shift, current_date, None
                )
                
                expected_hours = employee.expected_working_hours or 8.0
                overtime = self.calculate_overtime(work_hours, expected_hours, None)
            else:
                check_in = '-'
                check_out = '-'
                work_hours = 0
                overtime = 0
                is_late = False
                is_early = False
                late_min = 0
                early_min = 0
            
            status_code, status_display = self.determine_status(
                current_date, employee, day_logs, None, None
            )
            
            writer.writerow([
                current_date.strftime('%Y-%m-%d'),
                current_date.strftime('%A'),
                check_in,
                check_out,
                day_logs.count(),
                round(work_hours, 2),
                round(overtime, 2),
                status_display,
                f'Yes ({late_min} min)' if is_late else 'No',
                f'Yes ({early_min} min)' if is_early else 'No',
            ])
            
            current_date += timedelta(days=1)
        
        return response
    
    def export_payroll_report(self, request):
        """Export payroll summary report to CSV"""
        company = self.get_company(request)
        start_date, end_date = self.get_date_range(request)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="payroll_summary_{start_date}_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee ID', 'Employee Name', 'Department', 'Designation',
            'Present Days', 'Absent Days', 'Leave Days', 'Work Hours', 'Overtime Hours',
            'Basic Salary', 'Allowances', 'Overtime Pay', 'Hourly Wage',
            'Gross Pay', 'Deductions', 'Net Pay'
        ])
        
        # Get data
        logs = AttendanceLog.objects.filter(
            timestamp__date__range=[start_date, end_date]
        ).select_related('employee', 'employee__department')
        
        employees = Employee.objects.filter(is_active=True)
        
        for employee in employees:
            employee_logs = logs.filter(employee=employee)
            
            # Initialize counters
            present_days = 0
            absent_days = 0
            leave_days = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            
            # Process each day
            current_date = start_date
            while current_date <= end_date:
                day_logs = employee_logs.filter(
                    timestamp__date=current_date
                ).order_by('timestamp')
                
                status_code, _ = self.determine_status(
                    current_date, employee, day_logs, None, company
                )
                
                if day_logs.exists():
                    first_punch = day_logs.first().timestamp
                    last_punch = day_logs.last().timestamp
                    work_hours = self.calculate_work_hours(first_punch, last_punch, None)
                    
                    if status_code == 'P':
                        total_work_hours += work_hours
                
                if status_code == 'P':
                    present_days += 1
                elif status_code == 'A':
                    absent_days += 1
                elif status_code == 'L':
                    leave_days += 1
                elif status_code == 'HD':
                    present_days += 0.5
                    total_work_hours += work_hours
                
                current_date += timedelta(days=1)
            
            # Calculate salary components
            basic_salary = employee.basic_salary or Decimal('0.00')
            
            # Allowances
            house_rent = employee.house_rent_allowance or Decimal('0.00')
            medical = employee.medical_allowance or Decimal('0.00')
            conveyance = employee.conveyance_allowance or Decimal('0.00')
            food = employee.food_allowance or Decimal('0.00')
            attendance_bonus = employee.attendance_bonus or Decimal('0.00')
            festival_bonus = employee.festival_bonus or Decimal('0.00')
            
            total_allowance = house_rent + medical + conveyance + food + attendance_bonus + festival_bonus
            
            # Deductions
            provident_fund = employee.provident_fund or Decimal('0.00')
            tax = employee.tax_deduction or Decimal('0.00')
            loan = employee.loan_deduction or Decimal('0.00')
            
            total_deduction = provident_fund + tax + loan
            
            # Calculate overtime pay
            overtime_rate = employee.get_overtime_rate()
            overtime_pay = Decimal(str(total_overtime_hours)) * Decimal(str(overtime_rate))
            
            # Calculate hourly wage
            per_hour_rate = employee.get_per_hour_rate()
            hourly_wage = Decimal(str(total_work_hours)) * Decimal(str(per_hour_rate))
            
            # Gross pay = Basic + Allowances + Overtime Pay
            gross_pay = basic_salary + total_allowance + overtime_pay
            
            # Net pay = Gross - Deductions
            net_pay = gross_pay - total_deduction
            
            writer.writerow([
                employee.employee_id,
                employee.name,
                employee.department.name if employee.department else 'N/A',
                employee.designation.name if employee.designation else 'N/A',
                round(present_days, 1),
                absent_days,
                leave_days,
                round(total_work_hours, 2),
                round(total_overtime_hours, 2),
                float(basic_salary),
                float(total_allowance),
                float(overtime_pay),
                float(hourly_wage),
                float(gross_pay),
                float(total_deduction),
                float(net_pay),
            ])
        
        return response