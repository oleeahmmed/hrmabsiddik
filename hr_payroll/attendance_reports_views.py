from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg, Sum
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
import logging

from .models import Attendance, Employee, Department
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
def attendance_reports_main(request):
    """Main attendance reports view"""
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/main.html', {
            'error_message': 'No company access found'
        })
    
    # Get departments for filtering
    departments = Department.objects.filter(company=company).order_by('name')
    
    # Get date range for default values
    today = timezone.now().date()
    first_day_of_month = today.replace(day=1)
    
    context = {
        'company': company,
        'departments': departments,
        'default_start_date': first_day_of_month.strftime('%Y-%m-%d'),
        'default_end_date': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'zkteco/reports/main.html', context)

@login_required
def daily_attendance_report(request):
    """
    Daily Attendance Report - Simple and effective version
    Shows attendance records from Attendance model only
    """
    company = get_company_from_request(request)
    if not company:
        return render(request, 'zkteco/reports/daily_attendance.html', {
            'error_message': 'No company access found'
        })
    
    # Get filter parameters
    selected_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    department_id = request.GET.get('department', '')
    employee_id = request.GET.get('employee', '')
    status_filter = request.GET.get('status', '')
    
    # Parse date
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = timezone.now().date()
    
    # Base queryset - get attendance records for selected date
    attendance_records = Attendance.objects.filter(
        employee__company=company,
        date=selected_date
    ).select_related(
        'employee',
        'employee__department',
        'employee__designation',
        'shift'
    ).order_by('employee__employee_id')
    
    # Apply filters
    if department_id:
        attendance_records = attendance_records.filter(employee__department_id=department_id)
    
    if employee_id:
        attendance_records = attendance_records.filter(employee_id=employee_id)
    
    if status_filter:
        attendance_records = attendance_records.filter(status=status_filter)
    
    # Calculate summary statistics
    total_records = attendance_records.count()
    present_count = attendance_records.filter(status='P').count()
    absent_count = attendance_records.filter(status='A').count()
    leave_count = attendance_records.filter(status='L').count()
    holiday_count = attendance_records.filter(status='H').count()
    
    # Calculate attendance rate
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    # Calculate total work hours and overtime
    present_records = attendance_records.filter(status='P')
    total_work_hours = sum([record.work_hours for record in present_records])
    total_overtime = sum([float(record.overtime_hours or 0) for record in present_records])
    
    # Prepare summary data
    summary = {
        'total_employees': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'leave_count': leave_count,
        'holiday_count': holiday_count,
        'attendance_rate': round(attendance_rate, 1),
        'total_work_hours': round(total_work_hours, 2),
        'total_overtime': round(total_overtime, 2),
    }
    
    # Get filter options
    departments = Department.objects.filter(company=company).order_by('name')
    employees = Employee.objects.filter(company=company, is_active=True).order_by('employee_id')
    
    # Prepare context
    context = {
        'company': company,
        'attendance_records': attendance_records,
        'summary': summary,
        'selected_date': selected_date,
        'current_date': selected_date_str,
        'departments': departments,
        'employees': employees,
        'current_department': department_id,
        'current_employee': employee_id,
        'current_status': status_filter,
    }
    
    return render(request, 'zkteco/reports/daily_attendance.html', context)
@login_required
def monthly_attendance_report(request):
    """Generate monthly attendance report"""
    company = get_company_from_request(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company access found'})
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid date format'})
    
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
        attendance_percentage = (present_days / max(total_days - holiday_days, 1)) * 100 if (total_days - holiday_days) > 0 else 0
        
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
    
    return JsonResponse({
        'success': True,
        'report_data': report_data,
        'summary': summary,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'report_title': f'Monthly Attendance Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    })

@login_required
def analytics_summary_report(request):
    """Generate analytics summary report"""
    company = get_company_from_request(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company access found'})
    
    # Get parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    department_id = request.GET.get('department', '')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid date format'})
    
    # Base attendance queryset
    attendance_qs = Attendance.objects.filter(
        employee__company=company,
        date__range=[start_date, end_date]
    ).select_related('employee', 'employee__department')
    
    if department_id:
        attendance_qs = attendance_qs.filter(employee__department_id=department_id)
    
    # Department-wise analysis
    departments = Department.objects.filter(company=company)
    if department_id:
        departments = departments.filter(id=department_id)
    
    department_data = []
    for dept in departments:
        dept_attendance = attendance_qs.filter(employee__department=dept)
        
        total_records = dept_attendance.count()
        present_count = dept_attendance.filter(status='P').count()
        absent_count = dept_attendance.filter(status='A').count()
        leave_count = dept_attendance.filter(status='L').count()
        
        total_work_hours = sum([record.work_hours for record in dept_attendance])
        total_overtime = sum([float(record.overtime_hours) for record in dept_attendance if record.overtime_hours])
        
        department_data.append({
            'department': dept.name,
            'total_employees': Employee.objects.filter(department=dept, company=company, is_active=True).count(),
            'total_records': total_records,
            'present_count': present_count,
            'absent_count': absent_count,
            'leave_count': leave_count,
            'attendance_rate': round((present_count / max(total_records, 1)) * 100, 1),
            'total_work_hours': round(total_work_hours, 2),
            'total_overtime_hours': round(total_overtime, 2),
            'avg_daily_hours': round(total_work_hours / max(present_count, 1), 2),
        })
    
    # Daily trend analysis
    daily_stats = []
    current_date = start_date
    while current_date <= end_date:
        day_attendance = attendance_qs.filter(date=current_date)
        
        daily_stats.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'day_name': current_date.strftime('%A'),
            'total_present': day_attendance.filter(status='P').count(),
            'total_absent': day_attendance.filter(status='A').count(),
            'total_leave': day_attendance.filter(status='L').count(),
            'total_work_hours': round(sum([record.work_hours for record in day_attendance]), 2),
            'total_overtime': round(sum([float(record.overtime_hours) for record in day_attendance if record.overtime_hours]), 2),
        })
        
        current_date += timedelta(days=1)
    
    # Top performers (by attendance rate)
    employee_stats = (attendance_qs.values(
        'employee__employee_id', 
        'employee__name', 
        'employee__department__name'
    ).annotate(
        total_days=Count('id'),
        present_days=Count('id', filter=Q(status='P')),
        total_hours=Sum('overtime_hours'),
    ).order_by('-present_days'))[:10]
    
    top_performers = []
    for emp_stat in employee_stats:
        attendance_rate = (emp_stat['present_days'] / max(emp_stat['total_days'], 1)) * 100
        top_performers.append({
            'employee_id': emp_stat['employee__employee_id'],
            'employee_name': emp_stat['employee__name'],
            'department': emp_stat['employee__department__name'] or 'No Department',
            'attendance_rate': round(attendance_rate, 1),
            'total_days': emp_stat['total_days'],
            'present_days': emp_stat['present_days'],
            'total_overtime': round(float(emp_stat['total_hours'] or 0), 2),
        })
    
    # Overall summary
    total_records = attendance_qs.count()
    total_present = attendance_qs.filter(status='P').count()
    total_absent = attendance_qs.filter(status='A').count()
    total_leave = attendance_qs.filter(status='L').count()
    total_work_hours = sum([record.work_hours for record in attendance_qs])
    total_overtime = sum([float(record.overtime_hours) for record in attendance_qs if record.overtime_hours])
    
    overall_summary = {
        'total_records': total_records,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_leave': total_leave,
        'overall_attendance_rate': round((total_present / max(total_records, 1)) * 100, 1),
        'total_work_hours': round(total_work_hours, 2),
        'total_overtime_hours': round(total_overtime, 2),
        'avg_daily_work_hours': round(total_work_hours / max(total_present, 1), 2),
        'total_employees': Employee.objects.filter(company=company, is_active=True).count(),
    }
    
    return JsonResponse({
        'success': True,
        'department_data': department_data,
        'daily_stats': daily_stats,
        'top_performers': top_performers,
        'overall_summary': overall_summary,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'report_title': f'Analytics Summary Report - {start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}'
    })