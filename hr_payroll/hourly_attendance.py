# hourly_attendance.py - Updated with per_hour_rate amount calculation only
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db.models import Q, Count, Min, Max
from django.utils import timezone
from datetime import datetime, timedelta, date, time
from decimal import Decimal
import calendar
from .models import Employee, AttendanceLog, Department, Designation
from core.models import Company

def calculate_work_hours_enhanced(punches):
    """
    Enhanced work hours calculation for your specific requirements
    - First and last punch define the work period
    - All middle punches are deducted from work time (IN-OUT pairs)
    - If odd number of punches, deduct 1 hour penalty
    - Handle cross-day scenarios (6 AM to 2-4 AM next day)
    """
    if not punches:
        return 0, None, None, 0
    
    # Sort punches by timestamp
    punches = sorted(punches, key=lambda x: x['timestamp'])
    
    first_punch = punches[0]['timestamp']
    last_punch = punches[-1]['timestamp']
    punch_count = len(punches)
    
    # Calculate total duration between first and last punch
    total_duration_seconds = (last_punch - first_punch).total_seconds()
    
    # Calculate break time (middle punches)
    break_seconds = 0
    
    if punch_count > 2:
        # Process middle punches in pairs (OUT-IN)
        middle_punches = punches[1:-1]  # Exclude first and last punch
        
        for i in range(0, len(middle_punches), 2):
            if i + 1 < len(middle_punches):
                # OUT punch
                out_time = middle_punches[i]['timestamp']
                # IN punch  
                in_time = middle_punches[i + 1]['timestamp']
                
                break_duration = (in_time - out_time).total_seconds()
                break_seconds += break_duration
    
    # Odd punch penalty (1 hour deduction)
    odd_penalty_seconds = 3600 if punch_count % 2 != 0 else 0
    
    # Final work time calculation
    work_seconds = total_duration_seconds - break_seconds - odd_penalty_seconds
    work_hours = max(0, work_seconds / 3600)
    
    return round(work_hours, 2), first_punch, last_punch, punch_count

def get_work_day_punches(employee, target_date):
    """
    Get punches for a work day considering cross-day shifts
    Work day starts at 6 AM and can extend to 2-4 AM next day
    """
    # Work day starts at 6 AM on target_date
    work_start = datetime.combine(target_date, time(6, 0))
    # Work day can end up to 4 AM next day
    work_end = datetime.combine(target_date + timedelta(days=1), time(4, 0))
    
    punches = AttendanceLog.objects.filter(
        employee=employee,
        timestamp__range=[work_start, work_end]
    ).order_by('timestamp')
    
    return punches

def get_monthly_attendance_enhanced(employee, year, month):
    """
    Enhanced monthly attendance calculation with amount calculation based on per_hour_rate
    """
    # Get the range of dates for the month
    start_date = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    end_date = date(year, month, days_in_month)
    
    monthly_data = {
        'total_days': days_in_month,
        'present_days': 0,
        'total_hours': 0,
        'total_amount': 0,  # NEW: Total amount based on per_hour_rate
        'daily_data': {}
    }
    
    # Get employee's per hour rate
    per_hour_rate = float(employee.per_hour_rate)
    
    current_date = start_date
    while current_date <= end_date:
        # Get punches for this work day
        day_punches = get_work_day_punches(employee, current_date)
        
        punch_list = []
        for punch in day_punches:
            punch_list.append({
                'timestamp': punch.timestamp,
                'device': punch.device.name,
                'punch_type': punch.punch_type
            })
        
        # Calculate work hours using your existing calculation method
        work_hours, first_punch, last_punch, punch_count = calculate_work_hours_enhanced(punch_list)
        
        # Calculate daily amount based on per_hour_rate
        daily_amount = work_hours * per_hour_rate
        
        # Store daily data
        monthly_data['daily_data'][current_date] = {
            'work_hours': work_hours,
            'daily_amount': round(daily_amount, 2),  # Daily amount
            'first_punch': first_punch,
            'last_punch': last_punch,
            'punch_count': punch_count,
            'punches': punch_list,
            'is_present': work_hours > 0
        }
        
        # Update monthly totals
        if work_hours > 0:
            monthly_data['present_days'] += 1
            monthly_data['total_hours'] += work_hours
            monthly_data['total_amount'] += daily_amount  # Add to total amount
        
        current_date += timedelta(days=1)
    
    monthly_data['total_hours'] = round(monthly_data['total_hours'], 2)
    monthly_data['total_amount'] = round(monthly_data['total_amount'], 2)  # Round total amount
    
    return monthly_data

def hourly_attendance_report(request):
    # Get all companies (since user is not linked to company)
    companies = Company.objects.all()
    
    # If no companies exist, return empty context
    if not companies.exists():
        context = {
            'error_message': 'No companies found in the system.',
            'report_data': [],
            'current_filters': {},
            'summary_stats': None,
        }
        return render(request, 'zkteco/hourly_attendance_report.html', context)
    
    # Use the first company for now (you can modify this logic as needed)
    user_company = companies.first()
    
    # Get filter parameters - only month_year needed
    month_year = request.GET.get('month_year', '')
    
    # Parse month_year if provided
    year = month = None
    if month_year:
        try:
            year, month = map(int, month_year.split('-'))
        except:
            today = timezone.now()
            year, month = today.year, today.month
            month_year = f"{year}-{month:02d}"
    else:
        # Default to current month if not provided
        today = timezone.now()
        year, month = today.year, today.month
        month_year = f"{year}-{month:02d}"
    
    # Initialize empty report data
    report_data = []
    summary_stats = None
    month_name = ''
    
    # Generate report for the selected month
    if year and month:
        # Get all active employees for the company
        employees = Employee.objects.filter(company=user_company, is_active=True)
        
        # Get monthly data for each employee
        for employee in employees:
            monthly_data = get_monthly_attendance_enhanced(employee, year, month)
            
            # Calculate average hours per day
            avg_hours = 0
            if monthly_data['present_days'] > 0:
                avg_hours = round(monthly_data['total_hours'] / monthly_data['present_days'], 2)
            
            report_data.append({
                'employee': employee,
                'monthly_data': monthly_data,
                'avg_hours_per_day': avg_hours,
                'year': year,
                'month': month
            })
        
        # Calculate summary statistics including total amount
        total_employees = len(report_data)
        total_work_hours = sum(data['monthly_data']['total_hours'] for data in report_data)
        total_amount = sum(data['monthly_data']['total_amount'] for data in report_data)  # NEW: Total amount
        total_present_days = sum(data['monthly_data']['present_days'] for data in report_data)
        
        avg_hours_all = 0
        if total_present_days > 0:
            avg_hours_all = round(total_work_hours / total_present_days, 2)
        
        summary_stats = {
            'total_employees': total_employees,
            'total_work_hours': round(total_work_hours, 2),
            'total_amount': round(total_amount, 2),  # NEW: Total amount in summary
            'total_present_days': total_present_days,
            'avg_hours_all': avg_hours_all
        }
        
        month_name = datetime(year, month, 1).strftime('%B %Y')
    
    context = {
        'report_data': report_data,
        'current_filters': {
            'month_year': month_year,
        },
        'month_name': month_name,
        'year': year,
        'month': month,
        'summary_stats': summary_stats,
        'user_company': user_company,
    }
    
    return render(request, 'zkteco/hourly_attendance_report.html', context)

def hourly_attendance_detail(request, employee_id, month_year):
    """
    Detailed view for specific employee's hourly attendance with amount calculation
    """
    # Get all companies
    companies = Company.objects.all()
    
    if not companies.exists():
        context = {
            'error_message': 'No companies found in the system.',
        }
        return render(request, 'zkteco/hourly_attendance_detail.html', context)
    
    # Use the first company
    user_company = companies.first()
    
    # Get employee
    employee = get_object_or_404(Employee, id=employee_id, company=user_company)
    
    try:
        year, month = map(int, month_year.split('-'))
    except:
        today = timezone.now()
        year, month = today.year, today.month
    
    monthly_data = get_monthly_attendance_enhanced(employee, year, month)
    
    # Calculate additional statistics
    avg_hours_per_day = 0
    max_hours_day = 0
    min_hours_day = float('inf')
    
    for day_data in monthly_data['daily_data'].values():
        if day_data['work_hours'] > 0:
            if day_data['work_hours'] > max_hours_day:
                max_hours_day = day_data['work_hours']
            if day_data['work_hours'] < min_hours_day:
                min_hours_day = day_data['work_hours']
    
    if monthly_data['present_days'] > 0:
        avg_hours_per_day = round(monthly_data['total_hours'] / monthly_data['present_days'], 2)
    
    if min_hours_day == float('inf'):
        min_hours_day = 0
    
    # Calculate attendance percentage
    attendance_percentage = 0
    if monthly_data['total_days'] > 0:
        attendance_percentage = round((monthly_data['present_days'] / monthly_data['total_days']) * 100, 1)
    
    context = {
        'employee': employee,
        'monthly_data': monthly_data,
        'year': year,
        'month': month,
        'month_year': month_year,
        'month_name': datetime(year, month, 1).strftime('%B %Y'),
        'statistics': {
            'avg_hours_per_day': avg_hours_per_day,
            'max_hours_day': max_hours_day,
            'min_hours_day': min_hours_day,
            'attendance_percentage': attendance_percentage
        },
        'user_company': user_company,
    }
    
    return render(request, 'zkteco/hourly_attendance_detail.html', context)

def export_hourly_report(request):
    """
    Export hourly attendance report to CSV/Excel
    """
    return JsonResponse({'status': 'success', 'message': 'Export functionality coming soon'})