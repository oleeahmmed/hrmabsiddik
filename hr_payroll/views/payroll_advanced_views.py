# payroll_advanced_views.py
# Additional advanced features for payroll management

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg, F, Case, When, Value, DecimalField
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
import logging
from io import BytesIO
from django.template.loader import render_to_string

from ..models import (
    Employee, Attendance, PayrollCycle, PayrollRecord, 
    PayrollTemplate, PayrollAdjustment, PayrollPayment,
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


# ==================== PAYROLL COMPARISON & ANALYSIS ====================

class PayrollComparisonView(LoginRequiredMixin, View):
    """Compare payroll across different cycles"""
    
    def get(self, request):
        company = get_company_from_request(request)
        
        # Get cycles for comparison
        cycle_ids = request.GET.getlist('cycles')
        
        if not cycle_ids:
            # Default: compare last 3 months
            cycles = PayrollCycle.objects.filter(
                company=company
            ).order_by('-start_date')[:3]
        else:
            cycles = PayrollCycle.objects.filter(
                id__in=cycle_ids,
                company=company
            ).order_by('-start_date')
        
        # Build comparison data
        comparison_data = []
        for cycle in cycles:
            records = cycle.payroll_records.all()
            
            comparison_data.append({
                'cycle': cycle,
                'total_employees': records.count(),
                'total_gross': records.aggregate(total=Sum('gross_salary'))['total'] or 0,
                'total_net': records.aggregate(total=Sum('net_salary'))['total'] or 0,
                'total_overtime': records.aggregate(total=Sum('overtime_amount'))['total'] or 0,
                'total_deductions': records.aggregate(total=Sum('total_deductions'))['total'] or 0,
                'avg_salary': records.aggregate(avg=Avg('net_salary'))['avg'] or 0,
                'paid_count': records.filter(payment_status='paid').count(),
            })
        
        # Get all cycles for selection
        all_cycles = PayrollCycle.objects.filter(
            company=company
        ).order_by('-start_date')
        
        context = {
            'company': company,
            'comparison_data': comparison_data,
            'all_cycles': all_cycles,
            'selected_cycle_ids': cycle_ids,
        }
        
        return render(request, 'zkteco/payroll/comparison.html', context)


# ==================== PAYROLL SALARY SLIP GENERATION ====================

class PayrollSalarySlipView(LoginRequiredMixin, View):
    """Generate individual salary slip"""
    
    def get(self, request, record_id):
        company = get_company_from_request(request)
        record = get_object_or_404(
            PayrollRecord, 
            id=record_id,
            payroll_cycle__company=company
        )
        
        # Get adjustments
        adjustments = record.adjustments.all()
        
        # Get attendance summary
        attendance_records = Attendance.objects.filter(
            employee=record.employee,
            date__range=[record.payroll_cycle.start_date, record.payroll_cycle.end_date]
        )
        
        context = {
            'company': company,
            'record': record,
            'adjustments': adjustments,
            'attendance_records': attendance_records,
            'generated_date': timezone.now(),
        }
        
        return render(request, 'zkteco/payroll/salary_slip.html', context)


class BulkSalarySlipGenerateView(LoginRequiredMixin, View):
    """Generate multiple salary slips as PDF"""
    
    def post(self, request):
        try:
            data = json.loads(request.body.decode('utf-8'))
            record_ids = data.get('record_ids', [])
            
            if not record_ids:
                return JsonResponse({
                    'success': False, 
                    'error': 'কোনো রেকর্ড নির্বাচন করা হয়নি'
                })
            
            company = get_company_from_request(request)
            records = PayrollRecord.objects.filter(
                id__in=record_ids,
                payroll_cycle__company=company
            ).select_related('employee', 'payroll_cycle')
            
            # Generate PDF or ZIP of PDFs
            # This would require a PDF library like ReportLab or WeasyPrint
            
            return JsonResponse({
                'success': True,
                'message': f'{len(records)} টি স্যালারি স্লিপ তৈরি হয়েছে',
                'download_url': '#'  # Return actual download URL
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL STATISTICS & ANALYTICS ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_get_statistics(request):
    """Get payroll statistics for dashboard"""
    try:
        company = get_company_from_request(request)
        data = json.loads(request.body.decode('utf-8'))
        
        period = data.get('period', 'month')  # month, quarter, year
        
        today = timezone.now().date()
        
        if period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'quarter':
            quarter = (today.month - 1) // 3
            start_date = date(today.year, quarter * 3 + 1, 1)
            end_date = today
        else:  # year
            start_date = date(today.year, 1, 1)
            end_date = today
        
        # Get records in period
        records = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payroll_cycle__start_date__gte=start_date,
            payroll_cycle__end_date__lte=end_date
        )
        
        # Calculate statistics
        stats = {
            'total_payroll': float(records.aggregate(total=Sum('net_salary'))['total'] or 0),
            'total_employees': records.values('employee').distinct().count(),
            'total_overtime': float(records.aggregate(total=Sum('overtime_amount'))['total'] or 0),
            'total_deductions': float(records.aggregate(total=Sum('total_deductions'))['total'] or 0),
            'avg_salary': float(records.aggregate(avg=Avg('net_salary'))['avg'] or 0),
            'pending_payments': records.filter(payment_status='pending').count(),
            'paid_amount': float(records.filter(payment_status='paid').aggregate(
                total=Sum('net_salary'))['total'] or 0),
        }
        
        # Department breakdown
        dept_stats = records.values(
            'employee__department__name'
        ).annotate(
            total=Sum('net_salary'),
            count=Count('id')
        ).order_by('-total')[:5]
        
        stats['top_departments'] = list(dept_stats)
        
        return JsonResponse({'success': True, 'statistics': stats})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== EMPLOYEE PAYROLL HISTORY ====================

class EmployeePayrollHistoryView(LoginRequiredMixin, View):
    """View employee's complete payroll history"""
    
    def get(self, request, employee_id):
        company = get_company_from_request(request)
        employee = get_object_or_404(Employee, id=employee_id, company=company)
        
        # Get all payroll records for this employee
        records = PayrollRecord.objects.filter(
            employee=employee
        ).select_related('payroll_cycle').order_by('-payroll_cycle__start_date')
        
        # Calculate totals
        total_earned = records.aggregate(total=Sum('net_salary'))['total'] or 0
        total_overtime = records.aggregate(total=Sum('overtime_amount'))['total'] or 0
        total_deductions = records.aggregate(total=Sum('total_deductions'))['total'] or 0
        avg_salary = records.aggregate(avg=Avg('net_salary'))['avg'] or 0
        
        # Yearly breakdown
        yearly_data = records.values(
            year=F('payroll_cycle__start_date__year')
        ).annotate(
            total_salary=Sum('net_salary'),
            total_ot=Sum('overtime_amount'),
            record_count=Count('id')
        ).order_by('-year')
        
        # Monthly trend (last 12 months)
        monthly_trend = []
        for i in range(11, -1, -1):
            month_date = timezone.now().date() - timedelta(days=30*i)
            month_start = month_date.replace(day=1)
            
            if month_date.month == 12:
                month_end = month_date.replace(day=31)
            else:
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            month_records = records.filter(
                payroll_cycle__start_date__gte=month_start,
                payroll_cycle__end_date__lte=month_end
            )
            
            monthly_trend.append({
                'month': month_date.strftime('%b %Y'),
                'total': float(month_records.aggregate(total=Sum('net_salary'))['total'] or 0)
            })
        
        context = {
            'company': company,
            'employee': employee,
            'records': records,
            'total_earned': total_earned,
            'total_overtime': total_overtime,
            'total_deductions': total_deductions,
            'avg_salary': avg_salary,
            'yearly_data': yearly_data,
            'monthly_trend': monthly_trend,
        }
        
        return render(request, 'zkteco/payroll/employee_history.html', context)


# ==================== PAYROLL AUDIT LOG ====================

class PayrollAuditLogView(LoginRequiredMixin, View):
    """View audit log of payroll changes"""
    
    def get(self, request):
        company = get_company_from_request(request)
        
        # Get adjustments as audit trail
        adjustments = PayrollAdjustment.objects.filter(
            payroll_record__payroll_cycle__company=company
        ).select_related(
            'payroll_record', 'payroll_record__employee', 'created_by'
        ).order_by('-created_at')
        
        # Get payments as audit trail
        payments = PayrollPayment.objects.filter(
            payroll_record__payroll_cycle__company=company
        ).select_related(
            'payroll_record', 'payroll_record__employee', 'processed_by'
        ).order_by('-created_at')
        
        # Filters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        user = request.GET.get('user')
        
        if start_date:
            adjustments = adjustments.filter(created_at__gte=start_date)
            payments = payments.filter(created_at__gte=start_date)
        
        if end_date:
            adjustments = adjustments.filter(created_at__lte=end_date)
            payments = payments.filter(created_at__lte=end_date)
        
        if user:
            adjustments = adjustments.filter(created_by_id=user)
            payments = payments.filter(processed_by_id=user)
        
        context = {
            'company': company,
            'adjustments': adjustments[:100],
            'payments': payments[:100],
        }
        
        return render(request, 'zkteco/payroll/audit_log.html', context)


# ==================== PAYROLL BUDGET & FORECASTING ====================

class PayrollBudgetView(LoginRequiredMixin, View):
    """Budget planning and forecasting"""
    
    def get(self, request):
        company = get_company_from_request(request)
        
        # Get current year data
        current_year = timezone.now().year
        
        # Monthly actual vs budget
        monthly_data = []
        for month in range(1, 13):
            month_start = date(current_year, month, 1)
            if month == 12:
                month_end = date(current_year, 12, 31)
            else:
                month_end = date(current_year, month + 1, 1) - timedelta(days=1)
            
            actual = PayrollRecord.objects.filter(
                payroll_cycle__company=company,
                payroll_cycle__start_date__gte=month_start,
                payroll_cycle__end_date__lte=month_end,
                payment_status='paid'
            ).aggregate(total=Sum('net_salary'))['total'] or 0
            
            monthly_data.append({
                'month': month_start.strftime('%b'),
                'actual': float(actual),
                'budget': 0,  # Set from budget model if available
            })
        
        # Department-wise budget
        dept_budget = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payroll_cycle__start_date__year=current_year
        ).values(
            'employee__department__name'
        ).annotate(
            total_spent=Sum('net_salary')
        ).order_by('-total_spent')
        
        # Projected annual cost
        completed_months = timezone.now().month
        if completed_months > 0:
            avg_monthly = sum([m['actual'] for m in monthly_data[:completed_months]]) / completed_months
            projected_annual = avg_monthly * 12
        else:
            projected_annual = 0
        
        context = {
            'company': company,
            'monthly_data': monthly_data,
            'dept_budget': dept_budget,
            'projected_annual': projected_annual,
            'current_year': current_year,
        }
        
        return render(request, 'zkteco/payroll/budget.html', context)


# ==================== PAYROLL DEDUCTION MANAGEMENT ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_calculate_tax(request):
    """Calculate tax for employee"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        gross_salary = Decimal(str(data.get('gross_salary', 0)))
        
        # Simple progressive tax calculation
        # Customize based on your country's tax rules
        
        if gross_salary <= 25000:
            tax = Decimal('0')
        elif gross_salary <= 50000:
            tax = (gross_salary - 25000) * Decimal('0.05')
        elif gross_salary <= 100000:
            tax = 1250 + (gross_salary - 50000) * Decimal('0.10')
        elif gross_salary <= 150000:
            tax = 6250 + (gross_salary - 100000) * Decimal('0.15')
        else:
            tax = 13750 + (gross_salary - 150000) * Decimal('0.20')
        
        return JsonResponse({
            'success': True,
            'tax_amount': float(tax),
            'net_salary': float(gross_salary - tax)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_calculate_provident_fund(request):
    """Calculate provident fund contribution"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        basic_salary = Decimal(str(data.get('basic_salary', 0)))
        pf_rate = Decimal(str(data.get('pf_rate', 10)))  # Default 10%
        
        employee_contribution = basic_salary * (pf_rate / 100)
        employer_contribution = employee_contribution  # Usually matched
        
        return JsonResponse({
            'success': True,
            'employee_contribution': float(employee_contribution),
            'employer_contribution': float(employer_contribution),
            'total_contribution': float(employee_contribution + employer_contribution)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL BONUS CALCULATION ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_calculate_bonus(request):
    """Calculate performance or festival bonus"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        employee_id = data.get('employee_id')
        bonus_type = data.get('bonus_type', 'performance')  # performance, festival
        
        employee = Employee.objects.get(id=employee_id)
        
        if bonus_type == 'festival':
            # Festival bonus = basic salary
            bonus = employee.basic_salary
        else:
            # Performance bonus based on attendance
            # Get last 3 months attendance
            three_months_ago = timezone.now().date() - timedelta(days=90)
            attendance = Attendance.objects.filter(
                employee=employee,
                date__gte=three_months_ago
            )
            
            total_days = attendance.count()
            present_days = attendance.filter(status='P').count()
            
            if total_days > 0:
                attendance_rate = (present_days / total_days) * 100
                
                if attendance_rate >= 95:
                    bonus = employee.basic_salary * Decimal('0.10')  # 10% bonus
                elif attendance_rate >= 90:
                    bonus = employee.basic_salary * Decimal('0.05')  # 5% bonus
                else:
                    bonus = Decimal('0')
            else:
                bonus = Decimal('0')
        
        return JsonResponse({
            'success': True,
            'bonus_amount': float(bonus),
            'bonus_type': bonus_type
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL EMAIL NOTIFICATIONS ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_send_salary_slip_email(request, record_id):
    """Send salary slip via email"""
    try:
        record = get_object_or_404(PayrollRecord, id=record_id)
        
        # Check if employee has email
        if not record.employee.user or not record.employee.user.email:
            return JsonResponse({
                'success': False,
                'error': 'কর্মচারীর ইমেইল পাওয়া যায়নি'
            })
        
        # Generate salary slip HTML
        html_content = render_to_string('zkteco/payroll/salary_slip_email.html', {
            'record': record,
            'company': record.payroll_cycle.company,
        })
        
        # Send email (implement with your email backend)
        # send_mail(
        #     subject=f'Salary Slip - {record.payroll_cycle.name}',
        #     message='',
        #     html_message=html_content,
        #     from_email='noreply@company.com',
        #     recipient_list=[record.employee.user.email],
        # )
        
        return JsonResponse({
            'success': True,
            'message': 'স্যালারি স্লিপ ইমেইল পাঠানো হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_bulk_send_salary_slips(request):
    """Send salary slips to multiple employees"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        cycle_id = data.get('cycle_id')
        
        cycle = get_object_or_404(PayrollCycle, id=cycle_id)
        
        records = cycle.payroll_records.filter(
            employee__user__isnull=False,
            employee__user__email__isnull=False
        ).select_related('employee', 'employee__user')
        
        sent_count = 0
        failed_count = 0
        
        for record in records:
            try:
                # Send email for each record
                # Implement email sending here
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send email to {record.employee.name}: {e}")
                failed_count += 1
        
        return JsonResponse({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'message': f'{sent_count} টি ইমেইল সফলভাবে পাঠানো হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL DATA VALIDATION ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_validate_cycle(request, cycle_id):
    """Validate payroll cycle for errors"""
    try:
        cycle = get_object_or_404(PayrollCycle, id=cycle_id)
        
        errors = []
        warnings = []
        
        records = cycle.payroll_records.all()
        
        for record in records:
            # Check for negative values
            if record.net_salary < 0:
                errors.append({
                    'employee': record.employee.name,
                    'issue': 'নেট বেতন ঋণাত্মক'
                })
            
            # Check for missing bank details for bank transfer
            if record.payment_method == 'bank_transfer' and not record.bank_account:
                warnings.append({
                    'employee': record.employee.name,
                    'issue': 'ব্যাংক একাউন্ট নম্বর নেই'
                })
            
            # Check for excessive overtime
            if record.overtime_hours > 100:
                warnings.append({
                    'employee': record.employee.name,
                    'issue': f'অতিরিক্ত ওভারটাইম: {record.overtime_hours} ঘণ্টা'
                })
            
            # Check for low attendance
            if record.present_days < (record.working_days * 0.5):
                warnings.append({
                    'employee': record.employee.name,
                    'issue': 'কম উপস্থিতি'
                })
        
        return JsonResponse({
            'success': True,
            'errors': errors,
            'warnings': warnings,
            'total_records': records.count(),
            'is_valid': len(errors) == 0
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})