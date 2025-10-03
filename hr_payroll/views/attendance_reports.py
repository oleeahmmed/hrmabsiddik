from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg, Sum, F, Case, When, IntegerField
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
import logging

from ..models import (
    Attendance, Employee, Department, LeaveApplication, 
    Shift, Holiday, AttendanceLog, Company
)

logger = logging.getLogger(__name__)

def get_company_from_request(request):
    """Helper to get company"""
    try:
        company = Company.objects.first()
        return company
    except Exception as e:
        logger.error(f"Error getting company: {str(e)}")
        return None

# ==================== Report 1: Daily Attendance Report ====================
@login_required
def daily_attendance_report(request):
    """
    Simplified Daily Attendance Report without company filter
    Allows selecting date, department, or employee
    """
    # Get company
    company = get_company_from_request(request)
    
    # Get parameters from request
    report_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    department_id = request.GET.get('department', '')
    employee_id = request.GET.get('employee', '')
    selected_status = request.GET.get('status', '')

    # Parse date
    try:
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
    except ValueError:
        report_date = timezone.now().date()

    # Base queryset for employees
    employees_filter = Q(is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    if employee_id:
        employees_filter &= Q(id=employee_id)

    # Get attendance records for the date
    attendance_records = Attendance.objects.filter(
        date=report_date
    ).select_related('employee', 'shift', 'employee__department', 'employee__designation')

    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    if employee_id:
        attendance_records = attendance_records.filter(employee_id=employee_id)
    if selected_status:
        attendance_records = attendance_records.filter(status=selected_status)

    # Get all active employees matching filters
    all_employees = Employee.objects.filter(employees_filter).select_related('department', 'designation', 'default_shift')

    # Create report data
    report_data = []
    present_count = 0
    absent_count = 0
    total_work_hours = 0
    total_overtime_hours = 0

    # Create attendance lookup dictionary
    attendance_lookup = {record.employee_id: record for record in attendance_records}

    for employee in all_employees:
        attendance = attendance_lookup.get(employee.id)

        if attendance:
            # Employee has attendance record
            status = attendance.get_status_display()
            status_code = attendance.status
            check_in = attendance.check_in_time.strftime('%I:%M %p') if attendance.check_in_time else '-'
            check_out = attendance.check_out_time.strftime('%I:%M %p') if attendance.check_out_time else '-'
            work_hours = attendance.work_hours
            overtime_hours = float(attendance.overtime_hours) if attendance.overtime_hours else 0
            shift_name = attendance.shift.name if attendance.shift else (employee.default_shift.name if employee.default_shift else 'No Shift')

            # Count statuses
            if status_code == 'P':
                present_count += 1
                total_work_hours += work_hours
                total_overtime_hours += overtime_hours
            elif status_code == 'A':
                absent_count += 1

        else:
            # No attendance record - mark as absent
            status = 'Absent'
            status_code = 'A'
            check_in = '-'
            check_out = '-'
            work_hours = 0
            overtime_hours = 0
            shift_name = employee.default_shift.name if employee.default_shift else 'No Shift'
            absent_count += 1

        # Apply status filter if selected
        if selected_status and status_code != selected_status:
            continue

        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'designation': employee.designation.name if employee.designation else 'No Designation',
            'shift': shift_name,
            'check_in': check_in,
            'check_out': check_out,
            'status': status,
            'work_hours': round(work_hours, 2),
            'overtime_hours': round(overtime_hours, 2),
        })

    # Summary data
    summary = {
        'total_employees': len(report_data) if selected_status else all_employees.count(),
        'present_count': present_count,
        'absent_count': absent_count,
        'total_work_hours': round(total_work_hours, 2),
        'total_overtime_hours': round(total_overtime_hours, 2),
    }

    # Get departments and employees for filtering
    departments = Department.objects.all().order_by('name')
    employees = Employee.objects.filter(is_active=True).order_by('name')

    context = {
        'company': company,  # Added company to context
        'report_data': report_data,
        'summary': summary,
        'selected_date': report_date,
        'departments': departments,
        'employees': employees,
        'selected_department': department_id,
        'selected_employee': employee_id,
        'selected_status': selected_status,
        'report_title': f'দৈনিক উপস্থিতি প্রতিবেদন - {report_date.strftime("%B %d, %Y")}'
    }

    return render(request, 'zkteco/reports/daily_attendance.html', context)

# ==================== Report 2: Monthly Attendance Summary Report ====================
@login_required
def monthly_attendance_summary(request):
    """
    Monthly Attendance Summary Report
    মাসিক অ্যাটেনডেন্স পার্সেন্টেজ, প্রেজেন্ট/অ্যাবসেন্ট/লিভ ডেজ, টোটাল ওয়ার্ক আওয়ারস
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/monthly_summary.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month if not provided
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset for employees
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records for the date range
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date]
    ).select_related('employee', 'employee__department')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all active employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process data by employee
    report_data = []
    total_days = (end_date - start_date).days + 1
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        
        # Count different statuses
        present_days = employee_attendance.filter(status='P').count()
        absent_days = employee_attendance.filter(status='A').count()
        leave_days = employee_attendance.filter(status='L').count()
        holiday_days = employee_attendance.filter(status='H').count()
        
        # Calculate working statistics
        total_work_hours = sum([record.work_hours for record in employee_attendance])
        total_overtime_hours = sum([float(record.overtime_hours) for record in employee_attendance if record.overtime_hours])
        
        # Calculate attendance percentage
        working_days = total_days - holiday_days
        attendance_percentage = (present_days / max(working_days, 1)) * 100 if working_days > 0 else 0
        
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'total_days': total_days,
            'present_days': present_days,
            'absent_days': absent_days,
            'leave_days': leave_days,
            'holiday_days': holiday_days,
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime_hours, 2),
            'avg_daily_hours': round(total_work_hours / max(present_days, 1), 2),
            'attendance_percentage': round(attendance_percentage, 1),
        })
    
    # Summary data
    summary = {
        'total_employees': len(report_data),
        'date_range_days': total_days,
        'total_present_days': sum([emp['present_days'] for emp in report_data]),
        'total_absent_days': sum([emp['absent_days'] for emp in report_data]),
        'total_leave_days': sum([emp['leave_days'] for emp in report_data]),
        'total_work_hours': sum([emp['total_work_hours'] for emp in report_data]),
        'total_overtime_hours': sum([emp['total_overtime_hours'] for emp in report_data]),
        'avg_attendance_percentage': round(sum([emp['attendance_percentage'] for emp in report_data]) / max(len(report_data), 1), 1),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Monthly Attendance Summary - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/monthly_summary.html', context)

# ==================== Report 3: Overtime Hours and Payment Report ====================
@login_required
def overtime_payment_report(request):
    """
    Overtime Hours and Payment Report
    ওভারটাইম আওয়ারস, রেট-ভিত্তিক পেমেন্ট ক্যালকুলেশন, ডিপার্টমেন্ট-ওয়াইজ সামারি
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/overtime_payment.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance with overtime
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date],
        overtime_hours__gt=0
    ).select_related('employee', 'employee__department')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process overtime data
    report_data = []
    total_overtime_hours = 0
    total_overtime_payment = 0
    
    for employee in all_employees:
        employee_overtime = attendance_records.filter(employee=employee)
        
        if employee_overtime.exists():
            overtime_hours = sum([float(record.overtime_hours) for record in employee_overtime])
            overtime_rate = float(employee.overtime_rate) if employee.overtime_rate else 0
            overtime_payment = overtime_hours * overtime_rate
            
            total_overtime_hours += overtime_hours
            total_overtime_payment += overtime_payment
            
            report_data.append({
                'employee_id': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'No Department',
                'overtime_hours': round(overtime_hours, 2),
                'overtime_rate': overtime_rate,
                'overtime_payment': round(overtime_payment, 2),
                'days_with_overtime': employee_overtime.count(),
            })
    
    # Department-wise summary
    department_summary = []
    departments = Department.objects.filter(company=company)
    if department_id:
        departments = departments.filter(id=department_id)
    
    for dept in departments:
        dept_data = [emp for emp in report_data if emp['department'] == dept.name]
        if dept_data:
            department_summary.append({
                'department': dept.name,
                'total_employees': len(dept_data),
                'total_overtime_hours': round(sum([emp['overtime_hours'] for emp in dept_data]), 2),
                'total_overtime_payment': round(sum([emp['overtime_payment'] for emp in dept_data]), 2),
            })
    
    # Summary
    summary = {
        'total_employees': len(report_data),
        'total_overtime_hours': round(total_overtime_hours, 2),
        'total_overtime_payment': round(total_overtime_payment, 2),
        'avg_overtime_per_employee': round(total_overtime_hours / max(len(report_data), 1), 2),
    }
    
    # Get departments for filtering
    all_departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'department_summary': department_summary,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': all_departments,
        'selected_department': department_id,
        'report_title': f'Overtime Payment Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/overtime_payment.html', context)

# ==================== Report 4: Hourly Wage Calculation Report ====================
@login_required
def hourly_wage_report(request):
    """
    Hourly Wage Calculation Report
    ঘন্টা-ভিত্তিক চুক্তির জন্য ডেলি/মান্থলি ওয়ার্ক আওয়ারস, টোটাল অ্যামাউন্ট
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/hourly_wage.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date],
        status='P'
    ).select_related('employee', 'employee__department')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process wage data
    report_data = []
    total_work_hours = 0
    total_amount = 0
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        
        if employee_attendance.exists():
            work_hours = sum([record.work_hours for record in employee_attendance])
            per_hour_rate = float(employee.per_hour_rate) if employee.per_hour_rate else 0
            total_wage = work_hours * per_hour_rate
            
            total_work_hours += work_hours
            total_amount += total_wage
            
            report_data.append({
                'employee_id': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'No Department',
                'total_work_hours': round(work_hours, 2),
                'per_hour_rate': per_hour_rate,
                'total_amount': round(total_wage, 2),
                'working_days': employee_attendance.count(),
                'avg_daily_hours': round(work_hours / max(employee_attendance.count(), 1), 2),
            })
    
    # Summary
    summary = {
        'total_employees': len(report_data),
        'total_work_hours': round(total_work_hours, 2),
        'total_amount': round(total_amount, 2),
        'avg_hours_per_employee': round(total_work_hours / max(len(report_data), 1), 2),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Hourly Wage Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/hourly_wage.html', context)

# ==================== Report 5: Leave and Absence Report ====================
@login_required
def leave_absence_report(request):
    """
    Leave and Absence Report
    লিভ অ্যাপ্লিকেশন, অ্যাবসেন্স কাউন্ট, কনসিকিউটিভ অ্যাবসেন্স ফ্ল্যাগিং
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/leave_absence.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date]
    ).select_related('employee', 'employee__department').order_by('employee', 'date')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get leave applications
    leave_applications = LeaveApplication.objects.filter(
        employee__company=company,
        start_date__lte=end_date,
        end_date__gte=start_date
    ).select_related('employee', 'leave_type')
    
    if department_id:
        leave_applications = leave_applications.filter(employee__department_id=department_id)
    
    # Get all employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process leave and absence data
    report_data = []
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        employee_leaves = leave_applications.filter(employee=employee)
        
        # Count absences and leaves
        absent_days = employee_attendance.filter(status='A').count()
        leave_days = employee_attendance.filter(status='L').count()
        
        # Check for consecutive absences
        consecutive_absences = 0
        max_consecutive = 0
        prev_date = None
        
        for record in employee_attendance.filter(status='A').order_by('date'):
            if prev_date and (record.date - prev_date).days == 1:
                consecutive_absences += 1
            else:
                consecutive_absences = 1
            max_consecutive = max(max_consecutive, consecutive_absences)
            prev_date = record.date
        
        # Flag if consecutive absences >= 3
        is_flagged = max_consecutive >= 3
        
        # Leave balance (simplified)
        total_leave_applications = employee_leaves.count()
        approved_leaves = employee_leaves.filter(status='A').count()
        pending_leaves = employee_leaves.filter(status='P').count()
        
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'absent_days': absent_days,
            'leave_days': leave_days,
            'max_consecutive_absences': max_consecutive,
            'is_flagged': is_flagged,
            'total_leave_applications': total_leave_applications,
            'approved_leaves': approved_leaves,
            'pending_leaves': pending_leaves,
        })
    
    # Summary
    summary = {
        'total_employees': len(report_data),
        'total_absent_days': sum([emp['absent_days'] for emp in report_data]),
        'total_leave_days': sum([emp['leave_days'] for emp in report_data]),
        'flagged_employees': sum([1 for emp in report_data if emp['is_flagged']]),
        'total_leave_applications': sum([emp['total_leave_applications'] for emp in report_data]),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Leave and Absence Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/leave_absence.html', context)

# ==================== Report 6: Late Arrival and Early Departure Report ====================
@login_required
def late_early_report(request):
    """
    Late Arrival and Early Departure Report
    লেট চেক-ইন এবং আর্লি চেক-আউটের ডিটেলস, গ্রেস টাইম কনসিডার করে
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/late_early.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records with check-in/out times
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date],
        status='P'
    ).select_related('employee', 'shift', 'employee__department').order_by('date')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Process late and early data
    late_arrivals = []
    early_departures = []
    
    for record in attendance_records:
        if record.shift and record.check_in_time:
            # Calculate late arrival
            shift_start = timezone.datetime.combine(record.date, record.shift.start_time)
            shift_start = timezone.make_aware(shift_start)
            grace_minutes = record.shift.grace_time
            
            late_minutes = (record.check_in_time - shift_start).total_seconds() / 60
            
            if late_minutes > grace_minutes:
                late_arrivals.append({
                    'employee_id': record.employee.employee_id,
                    'employee_name': record.employee.name,
                    'department': record.employee.department.name if record.employee.department else 'No Department',
                    'date': record.date,
                    'shift': record.shift.name,
                    'scheduled_time': shift_start.strftime('%H:%M'),
                    'actual_time': record.check_in_time.strftime('%H:%M'),
                    'late_minutes': int(late_minutes - grace_minutes),
                })
        
        if record.shift and record.check_out_time:
            # Calculate early departure
            shift_end = timezone.datetime.combine(record.date, record.shift.end_time)
            shift_end = timezone.make_aware(shift_end)
            
            # Handle overnight shifts
            if record.shift.end_time < record.shift.start_time:
                shift_end += timedelta(days=1)
            
            early_minutes = (shift_end - record.check_out_time).total_seconds() / 60
            
            if early_minutes > 0:
                early_departures.append({
                    'employee_id': record.employee.employee_id,
                    'employee_name': record.employee.name,
                    'department': record.employee.department.name if record.employee.department else 'No Department',
                    'date': record.date,
                    'shift': record.shift.name,
                    'scheduled_time': shift_end.strftime('%H:%M'),
                    'actual_time': record.check_out_time.strftime('%H:%M'),
                    'early_minutes': int(early_minutes),
                })
    
    # Summary
    summary = {
        'total_late_arrivals': len(late_arrivals),
        'total_early_departures': len(early_departures),
        'avg_late_minutes': round(sum([la['late_minutes'] for la in late_arrivals]) / max(len(late_arrivals), 1), 2),
        'avg_early_minutes': round(sum([ed['early_minutes'] for ed in early_departures]) / max(len(early_departures), 1), 2),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'late_arrivals': late_arrivals,
        'early_departures': early_departures,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Late Arrival & Early Departure Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/late_early.html', context)

# ==================== Report 7: Payroll Summary Sheet ====================
@login_required
def payroll_summary_report(request):
    """
    Comprehensive Payroll Summary Report
    Includes all payroll components: basic salary, allowances, overtime, deductions, and net pay
    """
    # Get company
    company = Company.objects.first()

    # Get parameters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
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
    
    # Base queryset for employees
    employees_filter = Q(is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    all_employees = Employee.objects.filter(employees_filter).select_related(
        'department', 'designation', 'default_shift'
    )
    
    # Process payroll data
    report_data = []
    summary = {
        'total_employees': 0,
        'total_basic_salary': Decimal('0.00'),
        'total_house_rent': Decimal('0.00'),
        'total_medical': Decimal('0.00'),
        'total_conveyance': Decimal('0.00'),
        'total_food': Decimal('0.00'),
        'total_attendance_bonus': Decimal('0.00'),
        'total_festival_bonus': Decimal('0.00'),
        'total_gross_salary': Decimal('0.00'),
        'total_work_hours': Decimal('0.00'),
        'total_hourly_pay': Decimal('0.00'),
        'total_overtime_hours': Decimal('0.00'),
        'total_overtime_pay': Decimal('0.00'),
        'total_provident_fund': Decimal('0.00'),
        'total_tax_deduction': Decimal('0.00'),
        'total_loan_deduction': Decimal('0.00'),
        'total_absence_deduction': Decimal('0.00'),
        'total_deductions': Decimal('0.00'),
        'total_net_pay': Decimal('0.00'),
    }

    # Calculate days in period for per-day calculations
    days_in_period = (end_date - start_date).days + 1
    working_days_in_period = 0
    
    # Estimate working days (excluding weekends - assuming 2 weekends per week)
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Monday to Friday
            working_days_in_period += 1
        current_date += timedelta(days=1)

    for employee in all_employees:
        # --- Salary Components ---
        basic_salary = employee.basic_salary or Decimal('0.00')
        house_rent = employee.house_rent_allowance or Decimal('0.00')
        medical = employee.medical_allowance or Decimal('0.00')
        conveyance = employee.conveyance_allowance or Decimal('0.00')
        food = employee.food_allowance or Decimal('0.00')
        attendance_bonus = employee.attendance_bonus or Decimal('0.00')
        festival_bonus = employee.festival_bonus or Decimal('0.00')
        
        # Gross Salary (Fixed components)
        gross_salary = (basic_salary + house_rent + medical + conveyance + 
                       food + attendance_bonus + festival_bonus)

        # --- Attendance & Work Hours ---
        employee_attendance = Attendance.objects.filter(
            employee=employee, 
            date__range=[start_date, end_date]
        )
        
        # Work hours calculation - Convert to Decimal properly
        work_hours = Decimal('0.00')
        for record in employee_attendance:
            if record.work_hours:
                work_hours += Decimal(str(record.work_hours))
        
        # Overtime hours - already Decimal from model
        overtime_hours_result = employee_attendance.aggregate(
            total_ot=Sum('overtime_hours')
        )
        overtime_hours = overtime_hours_result['total_ot'] or Decimal('0.00')
        
        # Hourly rate calculation - Ensure Decimal operations
        per_hour_rate = employee.per_hour_rate or Decimal('0.00')
        if not per_hour_rate and employee.expected_working_hours and basic_salary:
            # Calculate hourly rate from basic salary if not set
            expected_hours_decimal = Decimal(str(employee.expected_working_hours))
            per_hour_rate = basic_salary / (Decimal(str(working_days_in_period)) * expected_hours_decimal)
        
        # Convert work_hours to Decimal for multiplication
        work_hours_decimal = Decimal(str(float(work_hours)))
        hourly_pay = work_hours_decimal * per_hour_rate
        
        # Overtime pay calculation
        overtime_rate = employee.overtime_rate or Decimal('0.00')
        if not overtime_rate and per_hour_rate:
            # Default overtime rate: 1.5x hourly rate
            overtime_rate = per_hour_rate * Decimal('1.5')
        
        overtime_pay = overtime_hours * overtime_rate

        # --- Deductions ---
        provident_fund = employee.provident_fund or Decimal('0.00')
        tax_deduction = employee.tax_deduction or Decimal('0.00')
        loan_deduction = employee.loan_deduction or Decimal('0.00')
        
        # --- Absence Deduction ---
        absent_days = employee_attendance.filter(status='A').count()
        present_days = employee_attendance.filter(status='P').count()
        leave_days = employee_attendance.filter(status='L').count()
        
        # Calculate per day salary for absence deduction
        per_day_salary = Decimal('0.00')
        if working_days_in_period > 0:
            per_day_salary = gross_salary / Decimal(str(working_days_in_period))
        
        absence_deduction = per_day_salary * Decimal(str(absent_days))
        
        # Total deductions
        total_deductions = (provident_fund + tax_deduction + loan_deduction + absence_deduction)
        
        # --- Net Pay Calculation ---
        # Total earnings = Gross salary + Hourly pay + Overtime pay
        total_earnings = gross_salary + hourly_pay + overtime_pay
        net_pay = total_earnings - total_deductions

        # Append employee data
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else '-',
            'designation': employee.designation.name if employee.designation else '-',
            
            # Salary components
            'basic_salary': basic_salary,
            'house_rent': house_rent,
            'medical': medical,
            'conveyance': conveyance,
            'food': food,
            'attendance_bonus': attendance_bonus,
            'festival_bonus': festival_bonus,
            'gross_salary': gross_salary,
            
            # Work and attendance
            'work_hours': float(work_hours),  # Convert to float for template
            'per_hour_rate': per_hour_rate,
            'hourly_pay': hourly_pay,
            'overtime_hours': float(overtime_hours),  # Convert to float for template
            'overtime_rate': overtime_rate,
            'overtime_pay': overtime_pay,
            
            # Attendance summary
            'present_days': present_days,
            'absent_days': absent_days,
            'leave_days': leave_days,
            'total_days_in_period': days_in_period,
            'working_days_in_period': working_days_in_period,
            
            # Deductions
            'provident_fund': provident_fund,
            'tax_deduction': tax_deduction,
            'loan_deduction': loan_deduction,
            'absence_deduction': absence_deduction,
            'total_deductions': total_deductions,
            
            # Final pay
            'total_earnings': total_earnings,
            'net_pay': net_pay,
            
            # Additional info
            'payment_method': employee.payment_method or 'Cash',
            'bank_account_no': employee.bank_account_no or '-',
        })
        
        # Update summary totals - Convert all to Decimal properly
        summary['total_employees'] += 1
        summary['total_basic_salary'] += basic_salary
        summary['total_house_rent'] += house_rent
        summary['total_medical'] += medical
        summary['total_conveyance'] += conveyance
        summary['total_food'] += food
        summary['total_attendance_bonus'] += attendance_bonus
        summary['total_festival_bonus'] += festival_bonus
        summary['total_gross_salary'] += gross_salary
        summary['total_work_hours'] += work_hours
        summary['total_hourly_pay'] += hourly_pay
        summary['total_overtime_hours'] += overtime_hours
        summary['total_overtime_pay'] += overtime_pay
        summary['total_provident_fund'] += provident_fund
        summary['total_tax_deduction'] += tax_deduction
        summary['total_loan_deduction'] += loan_deduction
        summary['total_absence_deduction'] += absence_deduction
        summary['total_deductions'] += total_deductions
        summary['total_net_pay'] += net_pay

    # Calculate averages
    if summary['total_employees'] > 0:
        summary['avg_basic_salary'] = summary['total_basic_salary'] / summary['total_employees']
        summary['avg_net_pay'] = summary['total_net_pay'] / summary['total_employees']
        summary['avg_work_hours'] = summary['total_work_hours'] / summary['total_employees']

    # Get departments for filtering
    departments = Department.objects.all().order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
    }
    
    return render(request, 'zkteco/reports/payroll_summary.html', context)
# ==================== Report 8: Department-wise Attendance Analytics ====================
@login_required
def department_analytics_report(request):
    """
    Department-wise Attendance Analytics Report
    ডিপার্টমেন্ট-ভিত্তিক অ্যাটেনডেন্স রেট, ওভারটাইম, এবং প্রোডাকটিভিটি সামারি
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/department_analytics.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Get attendance records
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date]
    ).select_related('employee', 'employee__department')
    
    # Get all departments
    departments = Department.objects.filter(company=company)
    
    # Process department-wise data
    report_data = []
    
    for dept in departments:
        dept_attendance = attendance_records.filter(employee__department=dept)
        dept_employees = Employee.objects.filter(department=dept, company=company, is_active=True)
        
        total_records = dept_attendance.count()
        present_count = dept_attendance.filter(status='P').count()
        absent_count = dept_attendance.filter(status='A').count()
        leave_count = dept_attendance.filter(status='L').count()
        
        total_work_hours = sum([record.work_hours for record in dept_attendance.filter(status='P')])
        total_overtime = sum([float(record.overtime_hours) for record in dept_attendance if record.overtime_hours])
        
        # Calculate attendance rate
        attendance_rate = (present_count / max(total_records, 1)) * 100 if total_records > 0 else 0
        
        # Calculate productivity (work hours per employee)
        productivity = total_work_hours / max(dept_employees.count(), 1)
        
        report_data.append({
            'department': dept.name,
            'total_employees': dept_employees.count(),
            'total_records': total_records,
            'present_count': present_count,
            'absent_count': absent_count,
            'leave_count': leave_count,
            'attendance_rate': round(attendance_rate, 1),
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime, 2),
            'avg_daily_hours': round(total_work_hours / max(present_count, 1), 2),
            'productivity_score': round(productivity, 2),
        })
    
    # Overall summary
    summary = {
        'total_departments': len(report_data),
        'total_employees': sum([dept['total_employees'] for dept in report_data]),
        'overall_attendance_rate': round(sum([dept['attendance_rate'] for dept in report_data]) / max(len(report_data), 1), 1),
        'total_work_hours': sum([dept['total_work_hours'] for dept in report_data]),
        'total_overtime_hours': sum([dept['total_overtime_hours'] for dept in report_data]),
    }
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'report_title': f'Department Analytics - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/department_analytics.html', context)

# ==================== Report 9: Shift and Roster Compliance Report ====================
@login_required
def shift_roster_compliance_report(request):
    """
    Shift and Roster Compliance Report
    শিফট অ্যাসাইনমেন্ট, রোস্টার ডেজ, এবং কমপ্লায়েন্স
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/shift_compliance.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date],
        status='P'
    ).select_related('employee', 'shift', 'employee__department')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process compliance data
    report_data = []
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        
        total_days = employee_attendance.count()
        compliant_days = 0
        non_compliant_days = 0
        
        for record in employee_attendance:
            if record.shift:
                # Check if check-in is within shift time (with grace)
                if record.check_in_time:
                    shift_start = timezone.datetime.combine(record.date, record.shift.start_time)
                    shift_start = timezone.make_aware(shift_start)
                    grace_minutes = record.shift.grace_time
                    
                    late_minutes = (record.check_in_time - shift_start).total_seconds() / 60
                    
                    if late_minutes <= grace_minutes:
                        compliant_days += 1
                    else:
                        non_compliant_days += 1
                else:
                    non_compliant_days += 1
            else:
                non_compliant_days += 1
        
        compliance_rate = (compliant_days / max(total_days, 1)) * 100 if total_days > 0 else 0
        
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'default_shift': employee.default_shift.name if employee.default_shift else 'No Shift',
            'total_days': total_days,
            'compliant_days': compliant_days,
            'non_compliant_days': non_compliant_days,
            'compliance_rate': round(compliance_rate, 1),
        })
    
    # Summary
    summary = {
        'total_employees': len(report_data),
        'total_days': sum([emp['total_days'] for emp in report_data]),
        'total_compliant_days': sum([emp['compliant_days'] for emp in report_data]),
        'total_non_compliant_days': sum([emp['non_compliant_days'] for emp in report_data]),
        'overall_compliance_rate': round(sum([emp['compliance_rate'] for emp in report_data]) / max(len(report_data), 1), 1),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Shift & Roster Compliance - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/shift_compliance.html', context)

# ==================== Report 10: Employee Performance and Productivity Report ====================
@login_required
def employee_performance_report(request):
    """
    Employee Performance and Productivity Report
    টোটাল ওয়ার্ক আওয়ারস, অ্যাটেনডেন্স পার্সেন্টেজ, ওভারটাইম, এবং টপ পারফর্মারস
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/employee_performance.html', {
            'error_message': 'No company access found'
        })
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
    
    # Base queryset
    employees_filter = Q(company=company, is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get attendance records
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date]
    ).select_related('employee', 'employee__department')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all employees
    all_employees = Employee.objects.filter(employees_filter)
    
    # Process performance data
    report_data = []
    total_days = (end_date - start_date).days + 1
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        
        # Count statuses
        present_days = employee_attendance.filter(status='P').count()
        absent_days = employee_attendance.filter(status='A').count()
        leave_days = employee_attendance.filter(status='L').count()
        holiday_days = employee_attendance.filter(status='H').count()
        
        # Calculate statistics
        total_work_hours = sum([record.work_hours for record in employee_attendance.filter(status='P')])
        total_overtime = sum([float(record.overtime_hours) for record in employee_attendance if record.overtime_hours])
        
        # Calculate attendance percentage
        working_days = total_days - holiday_days
        attendance_percentage = (present_days / max(working_days, 1)) * 100 if working_days > 0 else 0
        
        # Calculate performance score (weighted average)
        # Attendance: 40%, Work Hours: 30%, Overtime: 20%, Punctuality: 10%
        attendance_score = attendance_percentage * 0.4
        work_hours_score = min((total_work_hours / max(present_days * 8, 1)) * 100, 100) * 0.3
        overtime_score = min((total_overtime / max(present_days, 1)) * 10, 100) * 0.2
        
        # Punctuality (simplified - based on late arrivals)
        late_count = 0
        for record in employee_attendance.filter(status='P'):
            if record.shift and record.check_in_time:
                shift_start = timezone.datetime.combine(record.date, record.shift.start_time)
                shift_start = timezone.make_aware(shift_start)
                grace_minutes = record.shift.grace_time
                late_minutes = (record.check_in_time - shift_start).total_seconds() / 60
                if late_minutes > grace_minutes:
                    late_count += 1
        
        punctuality_score = max(100 - (late_count / max(present_days, 1) * 100), 0) * 0.1
        
        performance_score = attendance_score + work_hours_score + overtime_score + punctuality_score
        
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'present_days': present_days,
            'absent_days': absent_days,
            'leave_days': leave_days,
            'attendance_percentage': round(attendance_percentage, 1),
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime, 2),
            'avg_daily_hours': round(total_work_hours / max(present_days, 1), 2),
            'late_arrivals': late_count,
            'performance_score': round(performance_score, 1),
        })
    
    # Sort by performance score
    report_data.sort(key=lambda x: x['performance_score'], reverse=True)
    
    # Top performers (top 10)
    top_performers = report_data[:10]
    
    # Summary
    summary = {
        'total_employees': len(report_data),
        'avg_attendance_percentage': round(sum([emp['attendance_percentage'] for emp in report_data]) / max(len(report_data), 1), 1),
        'total_work_hours': sum([emp['total_work_hours'] for emp in report_data]),
        'total_overtime_hours': sum([emp['total_overtime_hours'] for emp in report_data]),
        'avg_performance_score': round(sum([emp['performance_score'] for emp in report_data]) / max(len(report_data), 1), 1),
    }
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'report_data': report_data,
        'top_performers': top_performers,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'selected_department': department_id,
        'report_title': f'Employee Performance Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    }
    
    return render(request, 'zkteco/reports/employee_performance.html', context)

# ==================== Main Reports Dashboard ====================
@login_required
def reports_dashboard(request):
    """Main reports dashboard with links to all reports"""
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/dashboard.html', {
            'error_message': 'No company access found'
        })
    
    # Get date range for default values
    today = timezone.now().date()
    first_day_of_month = today.replace(day=1)
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'departments': departments,
        'default_start_date': first_day_of_month.strftime('%Y-%m-%d'),
        'default_end_date': today.strftime('%Y-%m-%d'),
    }
    
    return render(request, 'zkteco/reports/dashboard.html', context)
