# payroll_generation_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, models
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.core.cache import cache
from decimal import Decimal
import json
import logging
import csv
import calendar

from ..models import (
    Employee, Attendance, AttendanceLog, AttendanceProcessorConfiguration,
    PayrollCycle, PayrollRecord, PayrollTemplate,
    Department, Holiday, LeaveApplication
)
from core.models import Company

logger = logging.getLogger(__name__)


def get_company_from_request(request):
    """Helper to get company"""
    try:
        return Company.objects.first()
    except Exception as e:
        logger.error(f"Error getting company: {str(e)}")
        return None


@login_required
def payroll_generation_dashboard(request):
    """Payroll generation main dashboard"""
    try:
        company = get_company_from_request(request)
        if not company:
            messages.error(request, "কোনো কোম্পানি পাওয়া যায়নি।")
            return redirect('/')
        
        # Get statistics
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        
        # Total cycles
        total_cycles = PayrollCycle.objects.filter(company=company).count()
        
        # Current month cycle
        current_cycle = PayrollCycle.objects.filter(
            company=company,
            start_date__lte=today,
            end_date__gte=today
        ).first()
        
        # Pending payments
        pending_payments = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payment_status='pending'
        ).count()
        
        # Total paid this month
        total_paid_this_month = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payment_date__gte=current_month_start,
            payment_status='paid'
        ).aggregate(
            total=models.Sum('net_salary')
        )['total'] or Decimal('0.00')
        
        # Recent cycles
        recent_cycles = PayrollCycle.objects.filter(
            company=company
        ).order_by('-start_date')[:5]
        
        # Active templates
        templates = PayrollTemplate.objects.filter(
            company=company,
            is_active=True
        )
        
        stats = {
            'total_cycles': total_cycles,
            'current_cycle': current_cycle,
            'pending_payments': pending_payments,
            'total_paid_this_month': float(total_paid_this_month),
            'active_employees': Employee.objects.filter(company=company, is_active=True).count(),
        }
        
        context = {
            'company': company,
            'stats': stats,
            'recent_cycles': recent_cycles,
            'templates': templates,
            'today': today,
        }
        
        return render(request, 'zkteco/payroll/generation_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error in payroll dashboard: {str(e)}")
        messages.error(request, f"সিস্টেম এরর: {str(e)}")
        return redirect('/')


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_preview(request):
    """Generate payroll preview"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        company = get_company_from_request(request)
        
        if not company:
            return JsonResponse({'success': False, 'error': 'কোম্পানি পাওয়া যায়নি'})
        
        # Get parameters
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        cycle_name = data.get('cycle_name', '')
        template_id = data.get('template_id')
        employee_ids = data.get('employee_ids', [])
        department_ids = data.get('department_ids', [])
        
        # Validate dates
        if not start_date_str or not end_date_str:
            return JsonResponse({'success': False, 'error': 'তারিখ প্রয়োজন'})
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return JsonResponse({'success': False, 'error': f'ভুল তারিখ ফরম্যাট: {str(e)}'})
        
        if end_date < start_date:
            return JsonResponse({'success': False, 'error': 'শেষ তারিখ শুরু তারিখের পরে হতে হবে'})
        
        # Get template settings
        template = None
        if template_id:
            try:
                template = PayrollTemplate.objects.get(id=template_id, company=company)
            except PayrollTemplate.DoesNotExist:
                pass
        
        # Get employees
        employees_query = Employee.objects.filter(company=company, is_active=True)
        
        if employee_ids:
            employees_query = employees_query.filter(id__in=employee_ids)
        
        if department_ids:
            employees_query = employees_query.filter(department_id__in=department_ids)
        
        employees = employees_query.select_related('department', 'default_shift')
        
        if not employees.exists():
            return JsonResponse({'success': False, 'error': 'কোনো কর্মচারী পাওয়া যায়নি'})
        
        # Get configuration
        config = AttendanceProcessorConfiguration.get_active_config(company)
        weekend_days = config.weekend_days if config else [4, 5]  # Friday, Saturday
        
        # Get holidays
        holidays = Holiday.objects.filter(
            company=company,
            date__range=[start_date, end_date]
        ).values_list('date', flat=True)
        
        # Get leave applications
        leave_applications = LeaveApplication.objects.filter(
            employee__company=company,
            status='A',  # Approved leaves only
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related('employee', 'leave_type')
        
        # Create leave days mapping
        leave_days_map = {}
        for leave in leave_applications:
            emp_id = leave.employee.id
            if emp_id not in leave_days_map:
                leave_days_map[emp_id] = set()
            
            # Add all dates in leave range
            current = max(leave.start_date, start_date)
            leave_end = min(leave.end_date, end_date)
            
            while current <= leave_end:
                leave_days_map[emp_id].add(current)
                current += timedelta(days=1)
        
        # Calculate period statistics
        total_days = (end_date - start_date).days + 1
        
        # Calculate working days, weekends, and holidays for the period
        working_days_count = 0
        weekend_days_count = 0
        holiday_days_count = len(holidays)
        
        current_date = start_date
        while current_date <= end_date:
            is_weekend = current_date.weekday() in weekend_days
            is_holiday = current_date in holidays
            
            if is_weekend:
                weekend_days_count += 1
            elif not is_holiday:
                working_days_count += 1
            
            current_date += timedelta(days=1)
        
        # Generate preview data
        preview_data = []
        total_gross = Decimal('0.00')
        total_net = Decimal('0.00')
        total_deductions = Decimal('0.00')
        total_overtime = Decimal('0.00')
        
        for employee in employees:
            # Get attendance records
            attendance_records = Attendance.objects.filter(
                employee=employee,
                date__range=[start_date, end_date]
            )
            
            # Initialize counters
            present_days = 0
            absent_days = 0
            leave_days = 0
            half_days = 0
            late_count = 0
            early_count = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            weekend_worked_days = 0
            holiday_worked_days = 0
            
            # Employee specific leave days
            employee_leave_days = leave_days_map.get(employee.id, set())
            
            # Process each day in the period
            current_date = start_date
            while current_date <= end_date:
                is_weekend = current_date.weekday() in weekend_days
                is_holiday = current_date in holidays
                is_leave_day = current_date in employee_leave_days
                
                # Find attendance record for this date
                attendance_record = None
                for att in attendance_records:
                    if att.date == current_date:
                        attendance_record = att
                        break
                
                if attendance_record:
                    # Count based on attendance status
                    if attendance_record.status == 'P':
                        present_days += 1
                        if attendance_record.check_in_time and attendance_record.check_out_time:
                            delta = attendance_record.check_out_time - attendance_record.check_in_time
                            total_work_hours += delta.total_seconds() / 3600
                        total_overtime_hours += float(attendance_record.overtime_hours)
                    
                    elif attendance_record.status == 'L':
                        leave_days += 1
                    
                    elif attendance_record.status == 'W':
                        weekend_worked_days += 1
                        if attendance_record.overtime_hours:
                            total_overtime_hours += float(attendance_record.overtime_hours)
                    
                    elif attendance_record.status == 'H':
                        holiday_worked_days += 1
                        if attendance_record.overtime_hours:
                            total_overtime_hours += float(attendance_record.overtime_hours)
                
                else:
                    # No attendance record found
                    if is_leave_day:
                        leave_days += 1
                    elif is_holiday:
                        # Holiday - no attendance required
                        pass
                    elif is_weekend:
                        # Weekend - no attendance required  
                        pass
                    else:
                        # Working day but no attendance = absent
                        absent_days += 1
                
                current_date += timedelta(days=1)
            
            # Calculate payable days (working days + leaves + worked holidays/weekends)
            payable_days = present_days + leave_days + weekend_worked_days + holiday_worked_days
            
            # Get salary components from employee
            basic_salary = employee.basic_salary or Decimal('0.00')
            house_rent = employee.house_rent_allowance or Decimal('0.00')
            medical = employee.medical_allowance or Decimal('0.00')
            conveyance = employee.conveyance_allowance or Decimal('0.00')
            food = employee.food_allowance or Decimal('0.00')
            
            # Calculate attendance bonus
            attendance_percentage = (present_days / max(working_days_count, 1)) * 100 if working_days_count > 0 else 0
            attendance_bonus = Decimal('0.00')
            
            if template and template.auto_calculate_bonuses:
                if attendance_percentage >= float(template.minimum_attendance_for_bonus):
                    attendance_bonus = template.perfect_attendance_bonus
            else:
                attendance_bonus = employee.attendance_bonus or Decimal('0.00')
            
            festival_bonus = employee.festival_bonus or Decimal('0.00')
            
            # Calculate overtime
            overtime_rate = Decimal(str(employee.get_overtime_rate()))
            overtime_amount = Decimal(str(total_overtime_hours)) * overtime_rate
            
            # Calculate hourly wage (if applicable)
            hourly_rate = employee.per_hour_rate or Decimal('0.00')
            hourly_wage = Decimal(str(total_work_hours)) * hourly_rate
            
            # Total allowances
            total_allowances = (
                house_rent + medical + conveyance + 
                food + attendance_bonus + festival_bonus
            )
            
            # Deductions
            provident_fund = employee.provident_fund or Decimal('0.00')
            tax = employee.tax_deduction or Decimal('0.00')
            loan = employee.loan_deduction or Decimal('0.00')
            
            # Calculate absence deduction (শুধুমাত্র কর্মদিবসের অনুপস্থিতির জন্য)
            absence_deduction = Decimal('0.00')
            if absent_days > 0 and working_days_count > 0:
                per_day_salary = basic_salary / Decimal(str(working_days_count))
                if template and template.auto_calculate_deductions:
                    deduction_rate = template.per_day_absence_deduction_rate / Decimal('100')
                    absence_deduction = per_day_salary * Decimal(str(absent_days)) * deduction_rate
                else:
                    absence_deduction = per_day_salary * Decimal(str(absent_days))
            
            # Late penalty
            late_penalty = Decimal('0.00')
            if template and late_count > 0:
                late_penalty = template.late_arrival_penalty * Decimal(str(late_count))
            
            # Total deductions
            total_deduction = (
                provident_fund + tax + loan + 
                absence_deduction + late_penalty
            )
            
            # Calculate gross and net salary
            gross_salary = basic_salary + total_allowances + overtime_amount + hourly_wage
            net_salary = gross_salary - total_deduction
            
            # Add to totals
            total_gross += gross_salary
            total_net += net_salary
            total_deductions += total_deduction
            total_overtime += overtime_amount
            
            preview_record = {
                'employee_id': employee.id,
                'employee_code': employee.employee_id,
                'employee_name': employee.name,
                'department': employee.department.name if employee.department else 'সাধারণ',
                'designation': employee.designation.name if employee.designation else '-',
                
                # Period Information
                'total_days': total_days,
                'working_days': working_days_count,
                'weekend_days': weekend_days_count,
                'holiday_days': holiday_days_count,
                
                # Attendance Summary
                'present_days': present_days,
                'absent_days': absent_days,
                'leave_days': leave_days,
                'half_days': half_days,
                'payable_days': payable_days,
                
                # Special Work Days
                'weekend_worked': weekend_worked_days,
                'holiday_worked': holiday_worked_days,
                
                # Time Tracking
                'late_count': late_count,
                'early_count': early_count,
                'attendance_percentage': round(attendance_percentage, 2),
                
                # Working Hours
                'total_work_hours': round(total_work_hours, 2),
                'total_overtime_hours': round(total_overtime_hours, 2),
                
                # Salary Components
                'basic_salary': float(basic_salary),
                'house_rent': float(house_rent),
                'medical': float(medical),
                'conveyance': float(conveyance),
                'food': float(food),
                'attendance_bonus': float(attendance_bonus),
                'festival_bonus': float(festival_bonus),
                'total_allowances': float(total_allowances),
                
                # Overtime & Hourly
                'overtime_rate': float(overtime_rate),
                'overtime_amount': float(overtime_amount),
                'hourly_wage': float(hourly_wage),
                
                # Deductions
                'provident_fund': float(provident_fund),
                'tax': float(tax),
                'loan': float(loan),
                'absence_deduction': float(absence_deduction),
                'late_penalty': float(late_penalty),
                'total_deductions': float(total_deduction),
                
                # Totals
                'gross_salary': float(gross_salary),
                'net_salary': float(net_salary),
                
                # Bank Details
                'bank_account': employee.bank_account_no or '',
                'payment_method': employee.payment_method or 'Cash',
            }
            
            preview_data.append(preview_record)
        
        # Summary
        summary = {
            'total_employees': len(preview_data),
            'total_days': total_days,
            'working_days': working_days_count,
            'weekend_days': weekend_days_count,
            'holiday_days': holiday_days_count,
            'total_gross_salary': float(total_gross),
            'total_net_salary': float(total_net),
            'total_deductions': float(total_deductions),
            'total_overtime_amount': float(total_overtime),
            'average_salary': float(total_net / len(preview_data)) if preview_data else 0,
        }
        
        # Cache preview data
        cache_key = f"payroll_preview_{request.user.id}"
        cache.set(cache_key, {
            'data': preview_data,
            'params': data,
            'summary': summary,
            'timestamp': timezone.now().isoformat()
        }, 1800)  # 30 minutes
        
        return JsonResponse({
            'success': True,
            'preview_data': preview_data,
            'summary': summary,
            'message': f'সফলভাবে {len(preview_data)} টি পেরোল রেকর্ড প্রিভিউ তৈরি হয়েছে'
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({'success': False, 'error': f'ভুল JSON ফরম্যাট: {str(e)}'})
    except Exception as e:
        logger.error(f"Error in payroll preview: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'প্রিভিউ ব্যর্থ: {str(e)}'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_generate_records(request):
    """Generate actual payroll records from preview"""
    try:
        company = get_company_from_request(request)
        
        if not company:
            return JsonResponse({'success': False, 'error': 'কোম্পানি পাওয়া যায়নি'})
        
        # Get cached preview data
        cache_key = f"payroll_preview_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return JsonResponse({'success': False, 'error': 'প্রিভিউ ডেটা মেয়াদোত্তীর্ণ। দয়া করে আবার প্রিভিউ তৈরি করুন।'})
        
        preview_data = cached_data.get('data', [])
        params = cached_data.get('params', {})
        summary = cached_data.get('summary', {})
        
        if not preview_data:
            return JsonResponse({'success': False, 'error': 'কোনো ডেটা পাওয়া যায়নি'})
        
        # Parse dates
        start_date = datetime.strptime(params['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(params['end_date'], '%Y-%m-%d').date()
        cycle_name = params.get('cycle_name', f'Payroll {start_date.strftime("%B %Y")}')
        
        generated_count = 0
        updated_count = 0
        error_count = 0
        
        with transaction.atomic():
            # Create or get payroll cycle
            cycle, cycle_created = PayrollCycle.objects.get_or_create(
                company=company,
                start_date=start_date,
                end_date=end_date,
                defaults={
                    'name': cycle_name,
                    'cycle_type': 'monthly',
                    'status': 'generated',
                    'generated_at': timezone.now(),
                    'generated_by': request.user,
                }
            )
            
            # Generate payroll records
            for record_data in preview_data:
                try:
                    employee = Employee.objects.get(id=record_data['employee_id'])
                    
                    # Create or update payroll record
                    payroll_record, created = PayrollRecord.objects.update_or_create(
                        payroll_cycle=cycle,
                        employee=employee,
                        defaults={
                            # Salary components
                            'basic_salary': Decimal(str(record_data['basic_salary'])),
                            'house_rent_allowance': Decimal(str(record_data['house_rent'])),
                            'medical_allowance': Decimal(str(record_data['medical'])),
                            'conveyance_allowance': Decimal(str(record_data['conveyance'])),
                            'food_allowance': Decimal(str(record_data['food'])),
                            'attendance_bonus': Decimal(str(record_data['attendance_bonus'])),
                            'festival_bonus': Decimal(str(record_data['festival_bonus'])),
                            
                            # Overtime
                            'overtime_hours': Decimal(str(record_data['total_overtime_hours'])),
                            'overtime_rate': Decimal(str(record_data['overtime_rate'])),
                            'overtime_amount': Decimal(str(record_data['overtime_amount'])),
                            
                            # Hourly wage
                            'working_hours': Decimal(str(record_data['total_work_hours'])),
                            'hourly_rate': Decimal(str(employee.per_hour_rate or 0)),
                            'hourly_wage_amount': Decimal(str(record_data['hourly_wage'])),
                            
                            # Deductions
                            'provident_fund': Decimal(str(record_data['provident_fund'])),
                            'tax_deduction': Decimal(str(record_data['tax'])),
                            'loan_deduction': Decimal(str(record_data['loan'])),
                            'absence_deduction': Decimal(str(record_data['absence_deduction'])),
                            'other_deductions': Decimal(str(record_data.get('late_penalty', 0))),
                            
                            # Attendance - Updated fields
                            'working_days': record_data['working_days'],
                            'present_days': Decimal(str(record_data['present_days'])),
                            'absent_days': record_data['absent_days'],
                            'leave_days': record_data['leave_days'],
                            'half_days': record_data['half_days'],
                            'late_arrivals': record_data['late_count'],
                            'early_departures': record_data['early_count'],
                            
                            # Totals (will be calculated by save method)
                            'total_allowances': Decimal(str(record_data['total_allowances'])),
                            'total_deductions': Decimal(str(record_data['total_deductions'])),
                            'gross_salary': Decimal(str(record_data['gross_salary'])),
                            'net_salary': Decimal(str(record_data['net_salary'])),
                            
                            # Payment info
                            'payment_status': 'pending',
                            'payment_method': record_data.get('payment_method', 'cash'),
                            'bank_account': record_data.get('bank_account', ''),
                        }
                    )
                    
                    if created:
                        generated_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing payroll record: {e}")
            
            # Update cycle totals
            cycle.calculate_totals()
        
        # Clear cache
        cache.delete(cache_key)
        
        message = f'সফলভাবে {generated_count} টি পেরোল রেকর্ড তৈরি এবং {updated_count} টি আপডেট হয়েছে'
        if error_count > 0:
            message += f' ({error_count} টি ত্রুটি)'
        
        return JsonResponse({
            'success': True,
            'cycle_id': cycle.id,
            'records_created': generated_count,
            'records_updated': updated_count,
            'error_count': error_count,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error in payroll generation: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'পেরোল তৈরি ব্যর্থ: {str(e)}'})


@login_required
def payroll_cycle_list(request):
    """List all payroll cycles"""
    company = get_company_from_request(request)
    
    cycles = PayrollCycle.objects.filter(
        company=company
    ).order_by('-start_date')
    
    context = {
        'company': company,
        'cycles': cycles,
    }
    
    return render(request, 'zkteco/payroll/cycle_list.html', context)


@login_required
def payroll_cycle_detail(request, cycle_id):
    """View payroll cycle details"""
    company = get_company_from_request(request)
    cycle = get_object_or_404(PayrollCycle, id=cycle_id, company=company)
    
    records = cycle.payroll_records.select_related(
        'employee', 'employee__department'
    ).order_by('employee__employee_id')
    
    # Statistics
    stats = {
        'total_records': records.count(),
        'paid_records': records.filter(payment_status='paid').count(),
        'pending_records': records.filter(payment_status='pending').count(),
        'total_gross': sum([r.gross_salary for r in records]),
        'total_net': sum([r.net_salary for r in records]),
        'total_paid': sum([r.net_salary for r in records.filter(payment_status='paid')]),
    }
    
    context = {
        'company': company,
        'cycle': cycle,
        'records': records,
        'stats': stats,
    }
    
    return render(request, 'zkteco/payroll/cycle_detail.html', context)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_mark_paid(request, record_id):
    """Mark a payroll record as paid"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        
        record = get_object_or_404(PayrollRecord, id=record_id)
        
        payment_date = data.get('payment_date')
        payment_method = data.get('payment_method', record.payment_method)
        payment_reference = data.get('payment_reference', '')
        
        with transaction.atomic():
            record.payment_status = 'paid'
            record.payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date() if payment_date else timezone.now().date()
            record.payment_method = payment_method
            record.payment_reference = payment_reference
            record.save()
            
            # Update cycle totals
            record.payroll_cycle.calculate_totals()
        
        return JsonResponse({
            'success': True,
            'message': 'পেমেন্ট সফলভাবে সম্পন্ন হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'পেমেন্ট ব্যর্থ: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def payroll_export_csv(request, cycle_id):
    """Export payroll cycle to CSV"""
    try:
        company = get_company_from_request(request)
        cycle = get_object_or_404(PayrollCycle, id=cycle_id, company=company)
        
        records = cycle.payroll_records.select_related(
            'employee', 'employee__department'
        ).order_by('employee__employee_id')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="payroll_{cycle.name}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        # Add BOM for Excel to recognize UTF-8
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow([
            'কর্মচারী আইডি', 'নাম', 'বিভাগ', 'পদবী',
            'মোট দিন', 'কর্মদিবস', 'উপস্থিত', 'অনুপস্থিত', 'ছুটি', 'প্রদেয় দিন',
            'মূল বেতন', 'ভাড়া', 'চিকিৎসা', 'যাতায়াত', 'খাবার',
            'উপস্থিতি বোনাস', 'উৎসব বোনাস', 'মোট ভাতা',
            'ওভারটাইম ঘণ্টা', 'ওভারটাইম টাকা', 'ঘণ্টাভিত্তিক টাকা',
            'ভবিষ্য তহবিল', 'কর', 'ঋণ', 'অনুপস্থিতি কর্তন', 'মোট কর্তন',
            'মোট বেতন', 'নেট বেতন', 'পেমেন্ট স্ট্যাটাস', 'পেমেন্ট তারিখ'
        ])
        
        # Data
        for record in records:
            writer.writerow([
                record.employee.employee_id,
                record.employee.name,
                record.employee.department.name if record.employee.department else '',
                record.employee.designation.name if record.employee.designation else '',
                (cycle.end_date - cycle.start_date).days + 1,  # মোট দিন
                record.working_days,
                float(record.present_days),
                record.absent_days,
                record.leave_days,
                float(record.present_days) + record.leave_days,  # প্রদেয় দিন
                float(record.basic_salary),
                float(record.house_rent_allowance),
                float(record.medical_allowance),
                float(record.conveyance_allowance),
                float(record.food_allowance),
                float(record.attendance_bonus),
                float(record.festival_bonus),
                float(record.total_allowances),
                float(record.overtime_hours),
                float(record.overtime_amount),
                float(record.hourly_wage_amount),
                float(record.provident_fund),
                float(record.tax_deduction),
                float(record.loan_deduction),
                float(record.absence_deduction),
                float(record.total_deductions),
                float(record.gross_salary),
                float(record.net_salary),
                record.get_payment_status_display(),
                record.payment_date.strftime('%d/%m/%Y') if record.payment_date else '',
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'এক্সপোর্ট ব্যর্থ: {str(e)}'})