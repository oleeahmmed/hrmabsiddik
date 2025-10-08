# payroll_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg, F
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from datetime import datetime, date, timedelta
from django.core.cache import cache
from django.core.paginator import Paginator
from decimal import Decimal
import json
import logging
import csv
import calendar

from ..models import (
    Employee, Attendance, AttendanceLog, AttendanceProcessorConfiguration,
    PayrollCycle, PayrollRecord, PayrollTemplate, PayrollAdjustment, PayrollPayment,
    Department, Holiday, LeaveApplication, Shift
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


# ==================== PAYROLL DASHBOARD ====================

class PayrollDashboardView(LoginRequiredMixin, View):
    """Main payroll dashboard"""
    
    def get(self, request):
        company = get_company_from_request(request)
        if not company:
            messages.error(request, "কোম্পানি পাওয়া যায়নি।")
            return redirect('/')
        
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        
        # Statistics
        total_cycles = PayrollCycle.objects.filter(company=company).count()
        
        current_cycle = PayrollCycle.objects.filter(
            company=company,
            start_date__lte=today,
            end_date__gte=today
        ).first()
        
        pending_payments = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payment_status='pending'
        ).count()
        
        total_paid_this_month = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payment_date__gte=current_month_start,
            payment_status='paid'
        ).aggregate(total=Sum('net_salary'))['total'] or Decimal('0.00')
        
        # Recent cycles
        recent_cycles = PayrollCycle.objects.filter(
            company=company
        ).order_by('-start_date')[:5]
        
        # Active templates
        templates = PayrollTemplate.objects.filter(
            company=company,
            is_active=True
        )
        
        # Monthly trend (last 6 months)
        monthly_trend = []
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=30*i)
            month_start = month_date.replace(day=1)
            if month_date.month == 12:
                month_end = month_date.replace(day=31)
            else:
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            month_total = PayrollRecord.objects.filter(
                payroll_cycle__company=company,
                payroll_cycle__start_date__gte=month_start,
                payroll_cycle__end_date__lte=month_end,
                payment_status='paid'
            ).aggregate(total=Sum('net_salary'))['total'] or 0
            
            monthly_trend.append({
                'month': month_date.strftime('%b %Y'),
                'total': float(month_total)
            })
        
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
            'monthly_trend': monthly_trend,
            'today': today,
        }
        
        return render(request, 'zkteco/payroll/dashboard.html', context)


# ==================== PAYROLL CYCLE VIEWS ====================

class PayrollCycleListView(LoginRequiredMixin, ListView):
    """List all payroll cycles"""
    model = PayrollCycle
    template_name = 'zkteco/payroll/cycle_list.html'
    context_object_name = 'cycles'
    paginate_by = 20
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        queryset = PayrollCycle.objects.filter(company=company).order_by('-start_date')
        
        # Filters
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        year = self.request.GET.get('year')
        
        if status:
            queryset = queryset.filter(status=status)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(cycle_type__icontains=search)
            )
        
        if year:
            queryset = queryset.filter(start_date__year=year)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = get_company_from_request(self.request)
        
        # Get unique years
        years = PayrollCycle.objects.filter(
            company=context['company']
        ).dates('start_date', 'year', order='DESC')
        context['years'] = [d.year for d in years]
        
        return context


class PayrollCycleDetailView(LoginRequiredMixin, DetailView):
    """View payroll cycle details"""
    model = PayrollCycle
    template_name = 'zkteco/payroll/cycle_detail.html'
    context_object_name = 'cycle'
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollCycle.objects.filter(company=company)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cycle = self.object
        
        records = cycle.payroll_records.select_related(
            'employee', 'employee__department', 'employee__designation'
        ).order_by('employee__employee_id')
        
        # Filters
        department = self.request.GET.get('department')
        payment_status = self.request.GET.get('payment_status')
        search = self.request.GET.get('search')
        
        if department:
            records = records.filter(employee__department_id=department)
        
        if payment_status:
            records = records.filter(payment_status=payment_status)
        
        if search:
            records = records.filter(
                Q(employee__employee_id__icontains=search) |
                Q(employee__name__icontains=search)
            )
        
        # Pagination
        paginator = Paginator(records, 50)
        page = self.request.GET.get('page')
        records = paginator.get_page(page)
        
        # Statistics
        all_records = cycle.payroll_records.all()
        stats = {
            'total_records': all_records.count(),
            'paid_records': all_records.filter(payment_status='paid').count(),
            'pending_records': all_records.filter(payment_status='pending').count(),
            'total_gross': all_records.aggregate(total=Sum('gross_salary'))['total'] or 0,
            'total_net': all_records.aggregate(total=Sum('net_salary'))['total'] or 0,
            'total_paid': all_records.filter(payment_status='paid').aggregate(
                total=Sum('net_salary'))['total'] or 0,
        }
        
        # Department breakdown
        dept_breakdown = all_records.values(
            'employee__department__name'
        ).annotate(
            count=Count('id'),
            total_net=Sum('net_salary')
        ).order_by('-total_net')
        
        context['records'] = records
        context['stats'] = stats
        context['dept_breakdown'] = dept_breakdown
        context['departments'] = Department.objects.filter(company=cycle.company)
        context['company'] = cycle.company
        
        return context


class PayrollCycleCreateView(LoginRequiredMixin, View):
    """Create new payroll cycle with generation wizard"""
    
    def get(self, request):
        company = get_company_from_request(request)
        
        # Get templates
        templates = PayrollTemplate.objects.filter(company=company, is_active=True)
        
        # Get employees
        employees = Employee.objects.filter(company=company, is_active=True)
        
        # Get departments
        departments = Department.objects.filter(company=company)
        
        # Suggest cycle name based on current month
        today = timezone.now().date()
        suggested_name = f"Payroll {today.strftime('%B %Y')}"
        
        context = {
            'company': company,
            'templates': templates,
            'employees': employees,
            'departments': departments,
            'suggested_name': suggested_name,
            'today': today,
        }
        
        return render(request, 'zkteco/payroll/cycle_create.html', context)


class PayrollCycleUpdateView(LoginRequiredMixin, UpdateView):
    """Update payroll cycle"""
    model = PayrollCycle
    template_name = 'zkteco/payroll/cycle_update.html'
    fields = ['name', 'status', 'payment_date', 'notes']
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollCycle.objects.filter(company=company)
    
    def get_success_url(self):
        return reverse('zkteco:payroll_cycle_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'পেরোল সাইকেল সফলভাবে আপডেট হয়েছে।')
        return super().form_valid(form)


class PayrollCycleDeleteView(LoginRequiredMixin, DeleteView):
    """Delete payroll cycle"""
    model = PayrollCycle
    template_name = 'zkteco/payroll/cycle_confirm_delete.html'
    success_url = reverse_lazy('zkteco:payroll_cycle_list')
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollCycle.objects.filter(company=company)
    
    def delete(self, request, *args, **kwargs):
        cycle = self.get_object()
        if cycle.status == 'paid':
            messages.error(request, 'পরিশোধিত পেরোল সাইকেল মুছে ফেলা যাবে না।')
            return redirect('zkteco:payroll_cycle_detail', pk=cycle.pk)
        
        messages.success(request, f'পেরোল সাইকেল "{cycle.name}" সফলভাবে মুছে ফেলা হয়েছে।')
        return super().delete(request, *args, **kwargs)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_cycle_approve(request, cycle_id):
    """Approve a payroll cycle"""
    try:
        company = get_company_from_request(request)
        cycle = get_object_or_404(PayrollCycle, id=cycle_id, company=company)
        
        if cycle.status != 'generated':
            return JsonResponse({
                'success': False,
                'error': 'শুধুমাত্র জেনারেট করা সাইকেল অনুমোদন করা যাবে'
            })
        
        with transaction.atomic():
            cycle.status = 'approved'
            cycle.approved_at = timezone.now()
            cycle.approved_by = request.user
            cycle.save()
        
        return JsonResponse({
            'success': True,
            'message': 'পেরোল সাইকেল সফলভাবে অনুমোদিত হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL RECORD VIEWS ====================

class PayrollRecordDetailView(LoginRequiredMixin, DetailView):
    """View detailed payroll record"""
    model = PayrollRecord
    template_name = 'zkteco/payroll/record_detail.html'
    context_object_name = 'record'
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollRecord.objects.filter(payroll_cycle__company=company)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = self.object
        
        # Get adjustments
        adjustments = record.adjustments.all()
        
        # Get payments
        payments = record.payments.all()
        
        # Get attendance details
        attendance_records = Attendance.objects.filter(
            employee=record.employee,
            date__range=[record.payroll_cycle.start_date, record.payroll_cycle.end_date]
        ).order_by('date')
        
        context['adjustments'] = adjustments
        context['payments'] = payments
        context['attendance_records'] = attendance_records
        context['company'] = record.payroll_cycle.company
        
        return context


class PayrollRecordUpdateView(LoginRequiredMixin, View):
    """Update payroll record"""
    
    def get(self, request, pk):
        company = get_company_from_request(request)
        record = get_object_or_404(
            PayrollRecord, 
            id=pk, 
            payroll_cycle__company=company
        )
        
        context = {
            'record': record,
            'company': company,
        }
        
        return render(request, 'zkteco/payroll/record_update.html', context)
    
    def post(self, request, pk):
        try:
            company = get_company_from_request(request)
            record = get_object_or_404(
                PayrollRecord, 
                id=pk, 
                payroll_cycle__company=company
            )
            
            with transaction.atomic():
                # Update fields
                record.basic_salary = Decimal(request.POST.get('basic_salary', 0))
                record.house_rent_allowance = Decimal(request.POST.get('house_rent_allowance', 0))
                record.medical_allowance = Decimal(request.POST.get('medical_allowance', 0))
                record.conveyance_allowance = Decimal(request.POST.get('conveyance_allowance', 0))
                record.food_allowance = Decimal(request.POST.get('food_allowance', 0))
                record.attendance_bonus = Decimal(request.POST.get('attendance_bonus', 0))
                record.festival_bonus = Decimal(request.POST.get('festival_bonus', 0))
                record.other_allowances = Decimal(request.POST.get('other_allowances', 0))
                
                record.overtime_hours = Decimal(request.POST.get('overtime_hours', 0))
                record.overtime_rate = Decimal(request.POST.get('overtime_rate', 0))
                
                record.provident_fund = Decimal(request.POST.get('provident_fund', 0))
                record.tax_deduction = Decimal(request.POST.get('tax_deduction', 0))
                record.loan_deduction = Decimal(request.POST.get('loan_deduction', 0))
                record.absence_deduction = Decimal(request.POST.get('absence_deduction', 0))
                record.other_deductions = Decimal(request.POST.get('other_deductions', 0))
                
                record.remarks = request.POST.get('remarks', '')
                
                record.save()  # Will auto-calculate totals
                
                # Update cycle totals
                record.payroll_cycle.calculate_totals()
            
            messages.success(request, 'পেরোল রেকর্ড সফলভাবে আপডেট হয়েছে।')
            return redirect('zkteco:payroll_record_detail', pk=record.pk)
            
        except Exception as e:
            messages.error(request, f'আপডেট ব্যর্থ: {str(e)}')
            return redirect('zkteco:payroll_record_update', pk=pk)


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
            
            # Create payment record
            PayrollPayment.objects.create(
                payroll_record=record,
                amount=record.net_salary,
                payment_date=record.payment_date,
                payment_method=payment_method,
                reference_number=payment_reference,
                status='completed',
                processed_by=request.user
            )
            
            # Update cycle totals
            record.payroll_cycle.calculate_totals()
        
        return JsonResponse({
            'success': True,
            'message': 'পেমেন্ট সফলভাবে সম্পন্ন হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_bulk_mark_paid(request):
    """Mark multiple payroll records as paid"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        record_ids = data.get('record_ids', [])
        payment_date = data.get('payment_date')
        payment_method = data.get('payment_method', 'bank_transfer')
        
        if not record_ids:
            return JsonResponse({'success': False, 'error': 'কোনো রেকর্ড নির্বাচন করা হয়নি'})
        
        with transaction.atomic():
            records = PayrollRecord.objects.filter(id__in=record_ids)
            payment_date_obj = datetime.strptime(payment_date, '%Y-%m-%d').date() if payment_date else timezone.now().date()
            
            for record in records:
                record.payment_status = 'paid'
                record.payment_date = payment_date_obj
                record.payment_method = payment_method
                record.save()
                
                # Create payment record
                PayrollPayment.objects.create(
                    payroll_record=record,
                    amount=record.net_salary,
                    payment_date=payment_date_obj,
                    payment_method=payment_method,
                    status='completed',
                    processed_by=request.user
                )
            
            # Update cycle totals
            cycles = set([r.payroll_cycle for r in records])
            for cycle in cycles:
                cycle.calculate_totals()
        
        return JsonResponse({
            'success': True,
            'message': f'{len(record_ids)} টি পেমেন্ট সফলভাবে সম্পন্ন হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL TEMPLATE VIEWS ====================

class PayrollTemplateListView(LoginRequiredMixin, ListView):
    """List all payroll templates"""
    model = PayrollTemplate
    template_name = 'zkteco/payroll/template_list.html'
    context_object_name = 'templates'
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollTemplate.objects.filter(company=company).order_by('-is_active', 'name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = get_company_from_request(self.request)
        return context


class PayrollTemplateCreateView(LoginRequiredMixin, CreateView):
    """Create new payroll template"""
    model = PayrollTemplate
    template_name = 'zkteco/payroll/template_form.html'
    fields = [
        'name', 'description', 'default_cycle_type', 'payment_day',
        'auto_calculate_overtime', 'auto_calculate_deductions', 'auto_calculate_bonuses',
        'perfect_attendance_bonus', 'minimum_attendance_for_bonus',
        'per_day_absence_deduction_rate', 'late_arrival_penalty',
        'is_active'
    ]
    success_url = reverse_lazy('zkteco:payroll_template_list')
    
    def form_valid(self, form):
        company = get_company_from_request(self.request)
        form.instance.company = company
        messages.success(self.request, 'পেরোল টেমপ্লেট সফলভাবে তৈরি হয়েছে।')
        return super().form_valid(form)


class PayrollTemplateUpdateView(LoginRequiredMixin, UpdateView):
    """Update payroll template"""
    model = PayrollTemplate
    template_name = 'zkteco/payroll/template_form.html'
    fields = [
        'name', 'description', 'default_cycle_type', 'payment_day',
        'auto_calculate_overtime', 'auto_calculate_deductions', 'auto_calculate_bonuses',
        'perfect_attendance_bonus', 'minimum_attendance_for_bonus',
        'per_day_absence_deduction_rate', 'late_arrival_penalty',
        'is_active'
    ]
    success_url = reverse_lazy('zkteco:payroll_template_list')
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollTemplate.objects.filter(company=company)
    
    def form_valid(self, form):
        messages.success(self.request, 'পেরোল টেমপ্লেট সফলভাবে আপডেট হয়েছে।')
        return super().form_valid(form)


class PayrollTemplateDeleteView(LoginRequiredMixin, DeleteView):
    """Delete payroll template"""
    model = PayrollTemplate
    template_name = 'zkteco/payroll/template_confirm_delete.html'
    success_url = reverse_lazy('zkteco:payroll_template_list')
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        return PayrollTemplate.objects.filter(company=company)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'পেরোল টেমপ্লেট সফলভাবে মুছে ফেলা হয়েছে।')
        return super().delete(request, *args, **kwargs)


# ==================== PAYROLL ADJUSTMENT VIEWS ====================

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_add_adjustment(request, record_id):
    """Add adjustment to payroll record"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        record = get_object_or_404(PayrollRecord, id=record_id)
        
        adjustment_type = data.get('adjustment_type')
        title = data.get('title')
        amount = Decimal(data.get('amount', 0))
        description = data.get('description', '')
        
        if not title or amount <= 0:
            return JsonResponse({'success': False, 'error': 'শিরোনাম এবং পরিমাণ প্রয়োজন'})
        
        with transaction.atomic():
            adjustment = PayrollAdjustment.objects.create(
                payroll_record=record,
                adjustment_type=adjustment_type,
                title=title,
                amount=amount,
                description=description,
                created_by=request.user
            )
            
            # Update will happen in model's save method
        
        return JsonResponse({
            'success': True,
            'adjustment_id': adjustment.id,
            'message': 'সমন্বয় সফলভাবে যুক্ত হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def payroll_delete_adjustment(request, adjustment_id):
    """Delete payroll adjustment"""
    try:
        adjustment = get_object_or_404(PayrollAdjustment, id=adjustment_id)
        record = adjustment.payroll_record
        
        with transaction.atomic():
            # Reverse adjustment
            if adjustment.adjustment_type == 'addition':
                record.other_allowances -= adjustment.amount
            else:
                record.other_deductions -= adjustment.amount
            
            adjustment.delete()
            record.calculate_totals()
        
        return JsonResponse({
            'success': True,
            'message': 'সমন্বয় সফলভাবে মুছে ফেলা হয়েছে'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== PAYROLL PAYMENT VIEWS ====================

class PayrollPaymentListView(LoginRequiredMixin, ListView):
    """List all payroll payments"""
    model = PayrollPayment
    template_name = 'zkteco/payroll/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 50
    
    def get_queryset(self):
        company = get_company_from_request(self.request)
        queryset = PayrollPayment.objects.filter(
            payroll_record__payroll_cycle__company=company
        ).select_related(
            'payroll_record', 'payroll_record__employee', 'processed_by'
        ).order_by('-payment_date')
        
        # Filters
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if status:
            queryset = queryset.filter(status=status)
        
        if search:
            queryset = queryset.filter(
                Q(payroll_record__employee__employee_id__icontains=search) |
                Q(payroll_record__employee__name__icontains=search) |
                Q(reference_number__icontains=search)
            )
        
        if date_from:
            queryset = queryset.filter(payment_date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(payment_date__lte=date_to)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = get_company_from_request(self.request)
        
        # Summary
        queryset = self.get_queryset()
        context['total_amount'] = queryset.aggregate(total=Sum('amount'))['total'] or 0
        context['completed_count'] = queryset.filter(status='completed').count()
        
        return context


# ==================== EXPORT VIEWS ====================

@login_required
@require_http_methods(["GET"])
def payroll_export_csv(request, cycle_id):
    """Export payroll cycle to CSV"""
    try:
        company = get_company_from_request(request)
        cycle = get_object_or_404(PayrollCycle, id=cycle_id, company=company)
        
        records = cycle.payroll_records.select_related(
            'employee', 'employee__department', 'employee__designation'
        ).order_by('employee__employee_id')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="payroll_{cycle.name}_{timezone.now().strftime("%Y%m%d")}.csv"'
        response.write('\ufeff')  # BOM for Excel
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow([
            'কর্মচারী আইডি', 'নাম', 'বিভাগ', 'পদবী',
            'কার্যদিবস', 'উপস্থিতি', 'অনুপস্থিতি', 'ছুটি',
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
                record.working_days,
                float(record.present_days),
                record.absent_days,
                record.leave_days,
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
        logger.error(f"Export error: {str(e)}")
        messages.error(request, f'এক্সপোর্ট ব্যর্থ: {str(e)}')
        return redirect('zkteco:payroll_cycle_detail', pk=cycle_id)


@login_required
@require_http_methods(["GET"])
def payroll_export_bank_format(request, cycle_id):
    """Export payroll in bank transfer format"""
    try:
        company = get_company_from_request(request)
        cycle = get_object_or_404(PayrollCycle, id=cycle_id, company=company)
        
        records = cycle.payroll_records.filter(
            payment_method='bank_transfer',
            payment_status='approved'
        ).select_related('employee').order_by('employee__employee_id')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="bank_transfer_{cycle.name}_{timezone.now().strftime("%Y%m%d")}.csv"'
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Bank format header
        writer.writerow([
            'Employee ID',
            'Employee Name',
            'Bank Account Number',
            'Amount',
            'Reference'
        ])
        
        total_amount = Decimal('0.00')
        
        for record in records:
            if record.bank_account:
                writer.writerow([
                    record.employee.employee_id,
                    record.employee.name,
                    record.bank_account,
                    float(record.net_salary),
                    f'Salary-{cycle.name}'
                ])
                total_amount += record.net_salary
        
        # Total row
        writer.writerow(['', '', 'TOTAL', float(total_amount), ''])
        
        return response
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        messages.error(request, f'এক্সপোর্ট ব্যর্থ: {str(e)}')
        return redirect('zkteco:payroll_cycle_detail', pk=cycle_id)


# ==================== PAYROLL GENERATION VIEWS ====================

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
        
        # Generate preview data
        preview_data = []
        total_gross = Decimal('0.00')
        total_net = Decimal('0.00')
        total_deductions = Decimal('0.00')
        total_overtime = Decimal('0.00')
        
        # Calculate working days
        working_days = 0
        current = start_date
        while current <= end_date:
            is_weekend = config and current.weekday() in config.weekend_days
            is_holiday = Holiday.objects.filter(company=company, date=current).exists()
            
            if not is_weekend and not is_holiday:
                working_days += 1
            
            current += timedelta(days=1)
        
        for employee in employees:
            # Get attendance data
            attendance_records = Attendance.objects.filter(
                employee=employee,
                date__range=[start_date, end_date]
            )
            
            present_days = 0
            absent_days = 0
            leave_days = 0
            half_days = 0
            late_count = 0
            early_count = 0
            total_work_hours = 0.0
            total_overtime_hours = 0.0
            
            for att in attendance_records:
                if att.status == 'P':
                    present_days += 1
                    if att.check_in_time and att.check_out_time:
                        delta = att.check_out_time - att.check_in_time
                        total_work_hours += delta.total_seconds() / 3600
                    total_overtime_hours += float(att.overtime_hours)
                elif att.status == 'A':
                    absent_days += 1
                elif att.status == 'L':
                    leave_days += 1
            
            # Get salary components from employee
            basic_salary = employee.basic_salary or Decimal('0.00')
            house_rent = employee.house_rent_allowance or Decimal('0.00')
            medical = employee.medical_allowance or Decimal('0.00')
            conveyance = employee.conveyance_allowance or Decimal('0.00')
            food = employee.food_allowance or Decimal('0.00')
            
            # Calculate attendance bonus
            attendance_percentage = (present_days / max(working_days, 1)) * 100
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
            
            # Calculate absence deduction
            absence_deduction = Decimal('0.00')
            if absent_days > 0:
                per_day_salary = basic_salary / Decimal(str(working_days)) if working_days > 0 else Decimal('0.00')
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
                
                # Attendance
                'working_days': working_days,
                'present_days': present_days,
                'absent_days': absent_days,
                'leave_days': leave_days,
                'half_days': half_days,
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
                'overtime_hours': round(total_overtime_hours, 2),
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
            'total_gross_salary': float(total_gross),
            'total_net_salary': float(total_net),
            'total_deductions': float(total_deductions),
            'total_overtime_amount': float(total_overtime),
            'average_salary': float(total_net / len(preview_data)) if preview_data else 0,
            'working_days': working_days,
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
        logger.error(f"Error in payroll preview: {str(e)}")
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
                            
                            # Attendance
                            'working_days': record_data['working_days'],
                            'present_days': Decimal(str(record_data['present_days'])),
                            'absent_days': record_data['absent_days'],
                            'leave_days': record_data['leave_days'],
                            'half_days': record_data['half_days'],
                            'late_arrivals': record_data['late_count'],
                            'early_departures': record_data['early_count'],
                            
                            # Totals
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
        logger.error(f"Error in payroll generation: {str(e)}")
        return JsonResponse({'success': False, 'error': f'পেরোল তৈরি ব্যর্থ: {str(e)}'})


# ==================== REPORTS & ANALYTICS ====================

class PayrollReportsView(LoginRequiredMixin, View):
    """Payroll reports and analytics"""
    
    def get(self, request):
        company = get_company_from_request(request)
        
        # Get date range from request or default to current month
        today = timezone.now().date()
        start_date = request.GET.get('start_date', today.replace(day=1))
        end_date = request.GET.get('end_date', today)
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get payroll records in date range
        records = PayrollRecord.objects.filter(
            payroll_cycle__company=company,
            payroll_cycle__start_date__gte=start_date,
            payroll_cycle__end_date__lte=end_date
        )
        
        # Department-wise summary
        dept_summary = records.values(
            'employee__department__name'
        ).annotate(
            total_employees=Count('id'),
            total_gross=Sum('gross_salary'),
            total_net=Sum('net_salary'),
            avg_salary=Avg('net_salary')
        ).order_by('-total_net')
        
        # Payment method summary
        payment_summary = records.values('payment_method').annotate(
            count=Count('id'),
            total=Sum('net_salary')
        )
        
        # Payment status summary
        status_summary = records.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('net_salary')
        )
        
        # Monthly trend
        monthly_data = []
        current = start_date
        while current <= end_date:
            month_start = current.replace(day=1)
            if current.month == 12:
                month_end = current.replace(day=31)
            else:
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            month_records = records.filter(
                payroll_cycle__start_date__gte=month_start,
                payroll_cycle__end_date__lte=month_end
            )
            
            monthly_data.append({
                'month': current.strftime('%b %Y'),
                'total_paid': float(month_records.filter(payment_status='paid').aggregate(
                    total=Sum('net_salary'))['total'] or 0),
                'employee_count': month_records.count()
            })
            
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        context = {
            'company': company,
            'start_date': start_date,
            'end_date': end_date,
            'dept_summary': dept_summary,
            'payment_summary': payment_summary,
            'status_summary': status_summary,
            'monthly_data': monthly_data,
        }
        
        return render(request, 'zkteco/payroll/reports.html', context)