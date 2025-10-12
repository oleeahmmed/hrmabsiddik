from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg, Sum, F, Case, When, IntegerField
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
import logging
import calendar
from django.urls import reverse

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

@login_required
def monthly_attendance_summary(request):
    """
    Monthly Attendance Summary Report
    মাসিক অ্যাটেনডেন্স পার্সেন্টেজ, প্রেজেন্ট/অ্যাবসেন্ট/লিভ ডেজ, টোটাল ওয়ার্ক আওয়ারস
    সব ডেটা Attendance রেকর্ড থেকে সরাসরি আসবে
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
    ).select_related('employee', 'employee__department', 'shift')
    
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    # Get all active employees
    all_employees = Employee.objects.filter(employees_filter).select_related('department', 'designation', 'default_shift')
    
    # Process data by employee
    report_data = []
    total_days = (end_date - start_date).days + 1
    
    for employee in all_employees:
        employee_attendance = attendance_records.filter(employee=employee)
        
        # Count different statuses DIRECTLY from attendance records
        present_days = employee_attendance.filter(status='P').count()
        absent_days = employee_attendance.filter(status='A').count()
        leave_days = employee_attendance.filter(status='L').count()
        holiday_days = employee_attendance.filter(status='H').count()
        weekly_off_days = employee_attendance.filter(status='W').count()
        
        # Half days count (if you track half day status)
        half_days = employee_attendance.filter(status__icontains='Half').count()
        
        # Calculate working statistics
        total_work_hours = sum([record.work_hours for record in employee_attendance.filter(status='P')])
        total_overtime_hours = sum([float(record.overtime_hours) for record in employee_attendance if record.overtime_hours])
        
        # Calculate total working days (excluding weekends and holidays)
        total_working_days = total_days - weekly_off_days - holiday_days
        
        # Calculate attendance percentage based on working days
        if total_working_days > 0:
            attendance_percentage = (present_days / total_working_days) * 100
        else:
            attendance_percentage = 0
        
        # Late arrivals and early departures calculation
        late_arrivals = 0
        early_departures = 0
        
        for record in employee_attendance.filter(status='P'):
            if record.shift and record.check_in_time:
                # Calculate late arrival
                shift_start = timezone.datetime.combine(record.date, record.shift.start_time)
                shift_start = timezone.make_aware(shift_start)
                grace_minutes = record.shift.grace_time
                late_minutes = (record.check_in_time - shift_start).total_seconds() / 60
                if late_minutes > grace_minutes:
                    late_arrivals += 1
            
            if record.shift and record.check_out_time:
                # Calculate early departure
                shift_end = timezone.datetime.combine(record.date, record.shift.end_time)
                shift_end = timezone.make_aware(shift_end)
                # Handle overnight shifts
                if record.shift.end_time < record.shift.start_time:
                    shift_end += timedelta(days=1)
                early_minutes = (shift_end - record.check_out_time).total_seconds() / 60
                if early_minutes > 0:
                    early_departures += 1
        
        report_data.append({
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'No Department',
            'total_days': total_days,
            'working_days': total_working_days,
            'present_days': present_days,
            'absent_days': absent_days,
            'leave_days': leave_days,
            'holiday_days': holiday_days,
            'weekly_off_days': weekly_off_days,
            'half_days': half_days,
            'late_arrivals': late_arrivals,
            'early_departures': early_departures,
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime_hours, 2),
            'avg_daily_hours': round(total_work_hours / max(present_days, 1), 2),
            'attendance_percentage': round(attendance_percentage, 1),
        })
    
    # Summary data - সব তথ্য attendance রেকর্ড থেকে
    summary = {
        'total_employees': len(report_data),
        'total_days': total_days,
        'total_present_days': sum([emp['present_days'] for emp in report_data]),
        'total_absent_days': sum([emp['absent_days'] for emp in report_data]),
        'total_leave_days': sum([emp['leave_days'] for emp in report_data]),
        'total_holiday_days': sum([emp['holiday_days'] for emp in report_data]),
        'total_weekly_off_days': sum([emp['weekly_off_days'] for emp in report_data]),
        'total_half_days': sum([emp['half_days'] for emp in report_data]),
        'total_late_arrivals': sum([emp['late_arrivals'] for emp in report_data]),
        'total_early_departures': sum([emp['early_departures'] for emp in report_data]),
        'total_work_hours': round(sum([emp['total_work_hours'] for emp in report_data]), 2),
        'total_overtime_hours': round(sum([emp['total_overtime_hours'] for emp in report_data]), 2),
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

# ==================== Main Reports Dashboard ====================
@login_required
def reports_dashboard(request):
    """Main reports dashboard - only report grid"""
    return render(request, 'zkteco/reports/dashboard.html')

@login_required
def employee_monthly_attendance(request):
    """
    একজন শ্রমিকের মাসিক অ্যাটেনডেন্স রিপোর্ট
    Employee, Month এবং Year সিলেক্ট করে দেখা যাবে
    """
    # Get company
    company = Company.objects.first()
    
    # Get all employees for dropdown
    employees = Employee.objects.filter(is_active=True).select_related('department', 'designation').order_by('employee_id')
    
    # Get parameters from request
    employee_id = request.GET.get('employee', '')
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')
    
    # Default to current month/year if not provided
    today = datetime.now().date()
    if not month:
        month = str(today.month)
    if not year:
        year = str(today.year)
    
    # Initialize context
    context = {
        'company': company,
        'employees': employees,
        'selected_employee': employee_id,
        'selected_month': month,
        'selected_year': year,
        'months': [
            {'value': '1', 'name': 'জানুয়ারি'},
            {'value': '2', 'name': 'ফেব্রুয়ারি'},
            {'value': '3', 'name': 'মার্চ'},
            {'value': '4', 'name': 'এপ্রিল'},
            {'value': '5', 'name': 'মে'},
            {'value': '6', 'name': 'জুন'},
            {'value': '7', 'name': 'জুলাই'},
            {'value': '8', 'name': 'আগস্ট'},
            {'value': '9', 'name': 'সেপ্টেম্বর'},
            {'value': '10', 'name': 'অক্টোবর'},
            {'value': '11', 'name': 'নভেম্বর'},
            {'value': '12', 'name': 'ডিসেম্বর'},
        ],
        'years': list(range(2020, 2030)),
        'report_data': None,
        'summary': None,
    }
    
    # If employee is selected, generate report
    if employee_id:
        try:
            employee = Employee.objects.select_related('department', 'designation', 'default_shift').get(id=employee_id)
            
            # Calculate date range for the month
            month_int = int(month)
            year_int = int(year)
            
            # Get first and last day of month
            first_day = datetime(year_int, month_int, 1).date()
            last_day_num = calendar.monthrange(year_int, month_int)[1]
            last_day = datetime(year_int, month_int, last_day_num).date()
            
            # Get attendance records for the month
            attendance_records = Attendance.objects.filter(
                employee=employee,
                date__range=[first_day, last_day]
            ).select_related('shift').order_by('date')
            
            # Create attendance lookup dictionary
            attendance_dict = {record.date: record for record in attendance_records}
            
            # Generate daily report data
            report_data = []
            total_present = 0
            total_absent = 0
            total_leave = 0
            total_holiday = 0
            total_weekly_off = 0
            total_work_hours = Decimal('0.00')
            total_overtime_hours = Decimal('0.00')
            
            current_date = first_day
            while current_date <= last_day:
                attendance = attendance_dict.get(current_date)
                
                if attendance:
                    status = attendance.get_status_display()
                    status_code = attendance.status
                    check_in = attendance.check_in_time.strftime('%I:%M %p') if attendance.check_in_time else '-'
                    check_out = attendance.check_out_time.strftime('%I:%M %p') if attendance.check_out_time else '-'
                    work_hours = Decimal(str(attendance.work_hours))
                    overtime_hours = attendance.overtime_hours or Decimal('0.00')
                    shift_name = attendance.shift.name if attendance.shift else (employee.default_shift.name if employee.default_shift else '-')
                    
                    # Count statuses
                    if status_code == 'P':
                        total_present += 1
                        total_work_hours += work_hours
                        total_overtime_hours += overtime_hours
                    elif status_code == 'A':
                        total_absent += 1
                    elif status_code == 'L':
                        total_leave += 1
                    elif status_code == 'H':
                        total_holiday += 1
                    elif status_code == 'W':
                        total_weekly_off += 1
                else:
                    # No record - mark as absent
                    status = 'Absent'
                    status_code = 'A'
                    check_in = '-'
                    check_out = '-'
                    work_hours = Decimal('0.00')
                    overtime_hours = Decimal('0.00')
                    shift_name = employee.default_shift.name if employee.default_shift else '-'
                    total_absent += 1
                
                # Day name in Bangla
                day_names = ['সোমবার', 'মঙ্গলবার', 'বুধবার', 'বৃহস্পতিবার', 'শুক্রবার', 'শনিবার', 'রবিবার']
                day_name = day_names[current_date.weekday()]
                
                report_data.append({
                    'date': current_date,
                    'day_name': day_name,
                    'shift': shift_name,
                    'check_in': check_in,
                    'check_out': check_out,
                    'status': status,
                    'status_code': status_code,
                    'work_hours': work_hours,
                    'overtime_hours': overtime_hours,
                })
                
                current_date += timedelta(days=1)
            
            # Calculate summary
            total_days = len(report_data)
            working_days = total_days - total_holiday - total_weekly_off
            attendance_percentage = (total_present / working_days * 100) if working_days > 0 else 0
            
            # Calculate per hour rate
            per_hour_rate = employee.per_hour_rate or Decimal('0.00')
            if not per_hour_rate and employee.expected_working_hours and employee.basic_salary:
                per_hour_rate = employee.basic_salary / (Decimal('22') * Decimal(str(employee.expected_working_hours)))
            
            # Calculate hourly pay
            hourly_pay = total_work_hours * per_hour_rate
            
            # Calculate overtime rate
            overtime_rate = employee.overtime_rate or Decimal('0.00')
            if not overtime_rate and per_hour_rate:
                overtime_rate = per_hour_rate * Decimal('1.5')
            
            # Calculate overtime pay
            overtime_pay = total_overtime_hours * overtime_rate
            
            summary = {
                'total_days': total_days,
                'working_days': working_days,
                'present_days': total_present,
                'absent_days': total_absent,
                'leave_days': total_leave,
                'holiday_days': total_holiday,
                'weekly_off_days': total_weekly_off,
                'attendance_percentage': round(attendance_percentage, 1),
                'total_work_hours': total_work_hours,
                'total_overtime_hours': total_overtime_hours,
                'per_hour_rate': per_hour_rate,
                'hourly_pay': hourly_pay,
                'overtime_rate': overtime_rate,
                'overtime_pay': overtime_pay,
                'total_earnings': hourly_pay + overtime_pay,
            }
            
            context['employee_info'] = employee
            context['report_data'] = report_data
            context['summary'] = summary
            context['month_name'] = context['months'][month_int - 1]['name']
            
        except Employee.DoesNotExist:
            context['error_message'] = 'নির্বাচিত শ্রমিক পাওয়া যায়নি'
    
    return render(request, 'zkteco/reports/employee_monthly_attendance.html', context)


@login_required
def payroll_summary_report(request):
    """
    Payroll Summary Report generated from Attendance, Employee, Holiday, Leave models
    """
    company = get_company_from_request(request)
    
    # Get parameters from request
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')
    department_id = request.GET.get('department', '')
    
    # Default to current month/year if not provided
    today = datetime.now().date()
    if not month:
        month = str(today.month)
    if not year:
        year = str(today.year)
    
    # Calculate date range for the month
    try:
        month_int = int(month)
        year_int = int(year)
        
        # Get first and last day of month
        first_day = datetime(year_int, month_int, 1).date()
        last_day_num = calendar.monthrange(year_int, month_int)[1]
        last_day = datetime(year_int, month_int, last_day_num).date()
        
        total_days_in_month = (last_day - first_day).days + 1
        
    except (ValueError, TypeError):
        # Fallback to current month
        today = timezone.now().date()
        first_day = today.replace(day=1)
        last_day = today
        month_int = today.month
        year_int = today.year
        total_days_in_month = calendar.monthrange(year_int, month_int)[1]
    
    # Base queryset for employees
    employees_filter = Q(is_active=True)
    if department_id:
        employees_filter &= Q(department_id=department_id)
    
    # Get all active employees
    employees = Employee.objects.filter(employees_filter).select_related(
        'department', 'designation'
    ).order_by('employee_id')
    
    # Get attendance records for the month
    attendance_records = Attendance.objects.filter(
        date__range=[first_day, last_day],
        employee__in=employees
    ).select_related('employee', 'shift')
    
    # Get holidays for the month
    holidays = Holiday.objects.filter(
        date__range=[first_day, last_day]
    ).values_list('date', flat=True)
    
    # Get approved leave applications for the month
    leave_applications = LeaveApplication.objects.filter(
        status='A',  # Approved
        start_date__lte=last_day,
        end_date__gte=first_day
    ).select_related('employee', 'leave_type')
    
    # Create leave lookup dictionary
    leave_lookup = {}
    for leave in leave_applications:
        employee_id = leave.employee.id
        if employee_id not in leave_lookup:
            leave_lookup[employee_id] = 0
        # Calculate leave days within the month
        leave_start = max(leave.start_date, first_day)
        leave_end = min(leave.end_date, last_day)
        leave_days = (leave_end - leave_start).days + 1
        leave_lookup[employee_id] += leave_days
    
    # Process payroll data for each employee
    payroll_data = []
    total_gross_salary = Decimal('0.00')
    total_net_payable = Decimal('0.00')
    
    for employee in employees:
        # Get attendance records for this employee
        emp_attendance = attendance_records.filter(employee=employee)
        
        # Count different statuses
        present_days = emp_attendance.filter(status='P').count()
        absent_days = emp_attendance.filter(status='A').count()
        holiday_days = emp_attendance.filter(status='H').count()
        weekly_off_days = emp_attendance.filter(status='W').count()
        
        # Get leave days from leave applications
        leave_days = leave_lookup.get(employee.id, 0)
        
        # Calculate working days (excluding weekends and holidays)
        working_days = total_days_in_month - weekly_off_days - holiday_days
        
        # Calculate payable days
        payable_days = present_days + leave_days  # Full pay for leave days
        
        # CORRECTED: Use base_salary instead of basic_salary
        basic_salary = employee.base_salary or Decimal('0.00')
        
        # Calculate per day rate
        per_day_rate = basic_salary / Decimal('30') if basic_salary > 0 else Decimal('0.00')
        
        # Allowances (you can modify these calculations based on your business rules)
        house_rent = employee.house_rent_allowance or Decimal('0.00')
        medical_allowance = employee.medical_allowance or Decimal('0.00')
        conveyance_allowance = employee.conveyance_allowance or Decimal('0.00')
        food_allowance = employee.food_allowance or Decimal('0.00')
        
        # Calculate gross salary based on payable days
        basic_payable = (basic_salary / Decimal('30')) * payable_days if basic_salary > 0 else Decimal('0.00')
        house_rent_payable = house_rent
        medical_payable = medical_allowance
        conveyance_payable = conveyance_allowance
        food_payable = food_allowance
        
        gross_salary = (
            basic_payable + 
            house_rent_payable + 
            medical_payable + 
            conveyance_payable + 
            food_payable
        )
        
        # Deductions
        absence_deduction = (basic_salary / Decimal('30')) * absent_days if basic_salary > 0 else Decimal('0.00')
        advance_deduction = Decimal('0.00')  # You can add advance model later
        total_deductions = absence_deduction + advance_deduction
        
        # Other calculations
        stamp_fee = Decimal('10.00')  # Fixed stamp fee
        
        # Net payable
        net_payable = gross_salary - total_deductions - stamp_fee
        
        # Update totals
        total_gross_salary += gross_salary
        total_net_payable += net_payable
        
        payroll_data.append({
            'sl_no': len(payroll_data) + 1,
            'employee': employee,
            'designation': employee.designation.name if employee.designation else '-',
            'employee_id': employee.employee_id,
            'doj': employee.joining_date or '-',
            'grade': '-',  # You can add grade field to Employee model
            'total_days': total_days_in_month,
            'absent_days': absent_days,
            'leave_days': leave_days,
            'payable_days': payable_days,
            'basic_salary': basic_salary,  # Monthly basic salary - CORRECTED: This is base_salary value
            'basic_payable': basic_payable,  # Pro-rated basic for payable days
            'house_rent': house_rent_payable,
            'medical_allowance': medical_payable,
            'conveyance_allowance': conveyance_payable,
            'food_allowance': food_payable,
            'gross_salary': gross_salary,
            'absence_deduction': absence_deduction,
            'advance_deduction': advance_deduction,
            'total_deductions': total_deductions,
            'stamp_fee': stamp_fee,
            'net_payable': net_payable,
        })
    
    # Summary
    summary = {
        'total_employees': len(payroll_data),
        'total_gross_salary': total_gross_salary,
        'total_net_payable': total_net_payable,
        'report_month': first_day.strftime('%B, %Y'),
        'total_days_in_month': total_days_in_month,
    }
    
    # Get departments for filtering
    departments = Department.objects.all().order_by('name')
    
    context = {
        'company': company,
        'payroll_data': payroll_data,
        'summary': summary,
        'departments': departments,
        'selected_month': month,
        'selected_year': year,
        'selected_department': department_id,
        'months': [
            {'value': '1', 'name': 'January'},
            {'value': '2', 'name': 'February'},
            {'value': '3', 'name': 'March'},
            {'value': '4', 'name': 'April'},
            {'value': '5', 'name': 'May'},
            {'value': '6', 'name': 'June'},
            {'value': '7', 'name': 'July'},
            {'value': '8', 'name': 'August'},
            {'value': '9', 'name': 'September'},
            {'value': '10', 'name': 'October'},
            {'value': '11', 'name': 'November'},
            {'value': '12', 'name': 'December'},
        ],
        'years': list(range(2020, 2031)),
    }
    
    return render(request, 'zkteco/reports/payroll_summary.html', context)