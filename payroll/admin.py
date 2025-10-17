# ==================== payroll/admin.py ====================

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.db import transaction
from decimal import Decimal

from .models import (
    SalaryComponent,
    EmployeeSalaryStructure,
    SalaryStructureComponent,
    SalaryMonth,
    EmployeeSalary,
    SalaryDetail,
    Bonus,
    EmployeeAdvance,
)


# ==================== BASE ADMIN ====================

class PayrollBaseAdmin(ModelAdmin):
    """Base admin for payroll models"""
    search_help_text = _("Search by name, code, or ID")
    list_per_page = 25
    empty_value_display = _("Not set")


# ==================== SALARY COMPONENT ====================

@admin.register(SalaryComponent)
class SalaryComponentAdmin(PayrollBaseAdmin):
    list_display = ('name', 'code', 'company', 'component_type', 'is_taxable', 'created_at')
    list_filter = ('company', 'component_type', 'is_taxable', 'created_at')
    search_fields = ('name', 'code', 'company__name')
    ordering = ('company', 'component_type', 'name')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('company', 'name', 'code', 'component_type'),
            'classes': ('tab',)
        }),
        (_("⚙️ Settings"), {
            'fields': ('is_taxable',),
            'classes': ('tab',)
        }),
        (_("📝 Description"), {
            'fields': ('description',),
            'classes': ('tab', 'collapse')
        }),
    )


# ==================== SALARY STRUCTURE ====================

class SalaryStructureComponentInline(TabularInline):
    model = SalaryStructureComponent
    extra = 1
    fields = ('component', 'amount', 'percentage', 'calculated_amount', 'is_active')
    readonly_fields = ('calculated_amount',)
    autocomplete_fields = ['component']


@admin.register(EmployeeSalaryStructure)
class EmployeeSalaryStructureAdmin(PayrollBaseAdmin):
    list_display = (
        'employee', 'basic_salary', 'gross_salary', 'net_salary', 
        'total_earnings', 'total_deductions', 'effective_date', 'updated_at'
    )
    list_filter = ('effective_date', 'created_at')
    search_fields = ('employee__name', 'employee__employee_id')
    ordering = ('-effective_date',)
    inlines = [SalaryStructureComponentInline]
    readonly_fields = ('gross_salary', 'net_salary', 'total_earnings', 'total_deductions')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'effective_date', 'basic_salary'),
            'classes': ('tab',)
        }),
        (_("💰 Calculated Amounts"), {
            'fields': ('total_earnings', 'gross_salary', 'total_deductions', 'net_salary'),
            'classes': ('tab',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Recalculate totals
        obj.calculate_totals()
        obj.save()


# ==================== SALARY MONTH ====================

@admin.register(SalaryMonth)
class SalaryMonthAdmin(PayrollBaseAdmin):
    list_display = (
        'company', 'year', 'month', 'is_generated', 'is_paid', 
        'generated_date', 'payment_date', 'created_at'
    )
    list_filter = ('company', 'is_generated', 'is_paid', 'year', 'month')
    search_fields = ('company__name',)
    ordering = ('-year', '-month')
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('company', 'year', 'month'),
            'classes': ('tab',)
        }),
        (_("⚙️ Status"), {
            'fields': ('is_generated', 'is_paid'),
            'classes': ('tab',)
        }),
        (_("📅 Dates"), {
            'fields': ('generated_date', 'generated_by', 'payment_date'),
            'classes': ('tab', 'collapse')
        }),
        (_("📝 Remarks"), {
            'fields': ('remarks',),
            'classes': ('tab', 'collapse')
        }),
    )
    
    actions = ['generate_salaries']
    
    def generate_salaries(self, request, queryset):
        """Generate salary records for selected months"""
        from hr_payroll.models import Employee, Attendance
        from datetime import date
        
        success_count = 0
        error_count = 0
        
        for salary_month in queryset:
            if salary_month.is_generated:
                self.message_user(
                    request,
                    f"Salary already generated for {salary_month}",
                    messages.WARNING
                )
                continue
            
            try:
                with transaction.atomic():
                    # Get all active employees of this company
                    employees = Employee.objects.filter(
                        company=salary_month.company,
                        is_active=True
                    )
                    
                    for employee in employees:
                        # Skip if salary already exists
                        if EmployeeSalary.objects.filter(
                            salary_month=salary_month,
                            employee=employee
                        ).exists():
                            continue
                        
                        # Get employee salary structure
                        try:
                            salary_structure = employee.payroll_salary_structure
                        except EmployeeSalaryStructure.DoesNotExist:
                            error_count += 1
                            continue
                        
                        # Calculate attendance
                        start_date = date(salary_month.year, salary_month.month, 1)
                        if salary_month.month == 12:
                            end_date = date(salary_month.year + 1, 1, 1)
                        else:
                            end_date = date(salary_month.year, salary_month.month + 1, 1)
                        
                        attendances = Attendance.objects.filter(
                            employee=employee,
                            date__gte=start_date,
                            date__lt=end_date
                        )
                        
                        working_days = attendances.count()
                        present_days = attendances.filter(status='P').count()
                        absent_days = attendances.filter(status='A').count()
                        leave_days = attendances.filter(status='L').count()
                        
                        # Calculate overtime
                        total_overtime = sum([
                            att.overtime_hours for att in attendances 
                            if att.overtime_hours
                        ]) or Decimal('0.00')
                        
                        overtime_amount = Decimal('0.00')
                        if employee.overtime_rate and total_overtime > 0:
                            overtime_amount = employee.overtime_rate * total_overtime
                        
                        # Create salary record
                        employee_salary = EmployeeSalary.objects.create(
                            salary_month=salary_month,
                            employee=employee,
                            basic_salary=salary_structure.basic_salary,
                            gross_salary=salary_structure.gross_salary,
                            total_earnings=salary_structure.total_earnings + overtime_amount,
                            total_deductions=salary_structure.total_deductions,
                            net_salary=salary_structure.net_salary + overtime_amount,
                            working_days=working_days,
                            present_days=present_days,
                            absent_days=absent_days,
                            leave_days=leave_days,
                            overtime_hours=total_overtime,
                            overtime_amount=overtime_amount,
                        )
                        
                        # Create salary details
                        for component in salary_structure.structure_components.filter(is_active=True):
                            SalaryDetail.objects.create(
                                salary=employee_salary,
                                component=component.component,
                                amount=component.calculated_amount
                            )
                    
                    # Mark as generated
                    salary_month.is_generated = True
                    salary_month.generated_date = timezone.now()
                    salary_month.generated_by = request.user
                    salary_month.save()
                    
                    success_count += 1
                    
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Error generating salary for {salary_month}: {str(e)}",
                    messages.ERROR
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f"Successfully generated salaries for {success_count} month(s)",
                messages.SUCCESS
            )
        
        if error_count > 0:
            self.message_user(
                request,
                f"Failed to generate {error_count} salary records",
                messages.ERROR
            )
    
    generate_salaries.short_description = _("Generate Salaries for Selected Months")


# ==================== EMPLOYEE SALARY ====================

class SalaryDetailInline(TabularInline):
    model = SalaryDetail
    extra = 0
    fields = ('component', 'amount')
    readonly_fields = ('component', 'amount')
    can_delete = False


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(PayrollBaseAdmin):
    list_display = (
        'employee', 'salary_month', 'basic_salary', 'gross_salary', 
        'net_salary', 'present_days', 'absent_days', 'overtime_hours'
    )
    list_filter = ('salary_month__year', 'salary_month__month', 'salary_month__company')
    search_fields = ('employee__name', 'employee__employee_id')
    ordering = ('-salary_month__year', '-salary_month__month', 'employee__name')
    inlines = [SalaryDetailInline]
    
    fieldsets = (
        (_("📋 Basic Info"), {
            'fields': ('salary_month', 'employee'),
            'classes': ('tab',)
        }),
        (_("💰 Salary Breakdown"), {
            'fields': (
                'basic_salary', 'total_earnings', 'gross_salary',
                'total_deductions', 'net_salary', 'bonus'
            ),
            'classes': ('tab',)
        }),
        (_("📊 Attendance"), {
            'fields': (
                'working_days', 'present_days', 'absent_days', 'leave_days'
            ),
            'classes': ('tab',)
        }),
        (_("⏰ Overtime"), {
            'fields': ('overtime_hours', 'overtime_amount'),
            'classes': ('tab',)
        }),
        (_("📝 Remarks"), {
            'fields': ('remarks',),
            'classes': ('tab', 'collapse')
        }),
    )


# ==================== BONUS ====================

@admin.register(Bonus)
class BonusAdmin(PayrollBaseAdmin):
    list_display = ('employee', 'bonus_type', 'amount', 'bonus_date', 'created_at')
    list_filter = ('bonus_type', 'bonus_date', 'created_at')
    search_fields = ('employee__name', 'employee__employee_id', 'bonus_type')
    ordering = ('-bonus_date',)
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'bonus_type', 'amount', 'bonus_date'),
            'classes': ('tab',)
        }),
        (_("📝 Remarks"), {
            'fields': ('remarks',),
            'classes': ('tab', 'collapse')
        }),
    )


# ==================== ADVANCE ====================

@admin.register(EmployeeAdvance)
class EmployeeAdvanceAdmin(PayrollBaseAdmin):
    list_display = (
        'employee', 'amount', 'installments', 'installment_amount', 
        'status', 'application_date', 'approved_by'
    )
    list_filter = ('status', 'application_date', 'approval_date')
    search_fields = ('employee__name', 'employee__employee_id', 'reason')
    ordering = ('-application_date',)
    
    fieldsets = (
        (_("📋 Required Fields"), {
            'fields': ('employee', 'amount', 'installments', 'installment_amount', 'application_date'),
            'classes': ('tab',)
        }),
        (_("📝 Reason"), {
            'fields': ('reason',),
            'classes': ('tab',)
        }),
        (_("⚙️ Status"), {
            'fields': ('status', 'approved_by', 'approval_date'),
            'classes': ('tab',)
        }),
        (_("📝 Remarks"), {
            'fields': ('remarks',),
            'classes': ('tab', 'collapse')
        }),
    )
    
    actions = ['approve_advance', 'reject_advance']
    
    def approve_advance(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='PEN').update(
            status='APP',
            approved_by=request.user,
            approval_date=timezone.now().date()
        )
        self.message_user(request, f'{updated} advances approved.')
    
    approve_advance.short_description = _("Approve selected advances")
    
    def reject_advance(self, request, queryset):
        updated = queryset.filter(status='PEN').update(status='REJ')
        self.message_user(request, f'{updated} advances rejected.')
    
    reject_advance.short_description = _("Reject selected advances")