# ==================== payroll/models.py ====================
"""
Simple Payroll Management System
Imports Employee from hr_payroll app
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User

# Import from other apps
from core.models import Company
from hr_payroll.models import Employee, Attendance


# ==================== SALARY COMPONENTS ====================

class SalaryComponent(models.Model):
    """Salary components like Basic, HRA, Medical, PF, Tax etc."""
    COMPONENT_TYPE_CHOICES = (
        ('EARN', 'Earning'),
        ('DED', 'Deduction'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    name = models.CharField(_("Name"), max_length=100)
    code = models.CharField(_("Code"), max_length=20)
    component_type = models.CharField(_("Type"), max_length=4, choices=COMPONENT_TYPE_CHOICES)
    is_taxable = models.BooleanField(_("Taxable"), default=True)
    description = models.TextField(_("Description"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_component_type_display()})"

    class Meta:
        verbose_name = _("Salary Component")
        verbose_name_plural = _("Salary Components")
        unique_together = ('company', 'code')
        ordering = ['component_type', 'name']


# ==================== EMPLOYEE SALARY STRUCTURE ====================

class EmployeeSalaryStructure(models.Model):
    """Employee's salary structure"""
    employee = models.OneToOneField(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='payroll_salary_structure',
        verbose_name=_("Employee")
    )
    effective_date = models.DateField(_("Effective Date"))
    basic_salary = models.DecimalField(
        _("Basic Salary"), 
        max_digits=10, 
        decimal_places=2,
        help_text=_("Base salary amount")
    )
    gross_salary = models.DecimalField(
        _("Gross Salary"), 
        max_digits=10, 
        decimal_places=2,
        default=0,
        help_text=_("Total including earnings")
    )
    net_salary = models.DecimalField(
        _("Net Salary"), 
        max_digits=10, 
        decimal_places=2,
        default=0,
        help_text=_("After deductions")
    )
    total_earnings = models.DecimalField(_("Total Earnings"), max_digits=10, decimal_places=2, default=0)
    total_deductions = models.DecimalField(_("Total Deductions"), max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def calculate_totals(self):
        """Calculate total earnings and deductions"""
        earnings = self.basic_salary
        deductions = Decimal('0.00')
        
        # Calculate from components
        for component in self.structure_components.filter(component__component_type='EARN', is_active=True):
            if component.percentage:
                amount = (self.basic_salary * component.percentage) / 100
            else:
                amount = component.amount or Decimal('0.00')
            earnings += amount
        
        for component in self.structure_components.filter(component__component_type='DED', is_active=True):
            if component.percentage:
                amount = (earnings * component.percentage) / 100
            else:
                amount = component.amount or Decimal('0.00')
            deductions += amount
        
        self.total_earnings = earnings
        self.total_deductions = deductions
        self.gross_salary = earnings
        self.net_salary = earnings - deductions
        
        return {
            'total_earnings': self.total_earnings,
            'total_deductions': self.total_deductions,
            'gross_salary': self.gross_salary,
            'net_salary': self.net_salary
        }
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.calculate_totals()
        super().save(update_fields=['total_earnings', 'total_deductions', 'gross_salary', 'net_salary'])
    
    def __str__(self):
        return f"{self.employee.name} - {self.gross_salary}"

    class Meta:
        verbose_name = _("Employee Salary Structure")
        verbose_name_plural = _("Employee Salary Structures")
        ordering = ['employee__name']


class SalaryStructureComponent(models.Model):
    """Links components to employee salary structure"""
    salary_structure = models.ForeignKey(
        EmployeeSalaryStructure, 
        on_delete=models.CASCADE, 
        related_name='structure_components',
        verbose_name=_("Salary Structure")
    )
    component = models.ForeignKey(
        SalaryComponent, 
        on_delete=models.CASCADE,
        verbose_name=_("Component")
    )
    amount = models.DecimalField(
        _("Fixed Amount"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text=_("Fixed amount for this component")
    )
    percentage = models.DecimalField(
        _("Percentage"), 
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text=_("Percentage of basic/gross salary")
    )
    calculated_amount = models.DecimalField(
        _("Calculated Amount"), 
        max_digits=10, 
        decimal_places=2,
        default=0
    )
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def calculate_amount(self):
        """Calculate final amount"""
        if self.percentage:
            if self.component.component_type == 'EARN':
                base_amount = self.salary_structure.basic_salary
            else:
                base_amount = self.salary_structure.gross_salary or self.salary_structure.basic_salary
            
            self.calculated_amount = (base_amount * self.percentage) / 100
        else:
            self.calculated_amount = self.amount or Decimal('0.00')
        
        return self.calculated_amount
    
    def save(self, *args, **kwargs):
        self.calculate_amount()
        super().save(*args, **kwargs)
        self.salary_structure.save()
    
    def __str__(self):
        return f"{self.salary_structure.employee.name} - {self.component.name}"

    class Meta:
        verbose_name = _("Salary Structure Component")
        verbose_name_plural = _("Salary Structure Components")
        unique_together = ('salary_structure', 'component')
        ordering = ['component__component_type', 'component__name']


# ==================== SALARY MONTH ====================

class SalaryMonth(models.Model):
    """Represents a salary month/period"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name=_("Company"))
    year = models.PositiveIntegerField(_("Year"))
    month = models.PositiveIntegerField(_("Month"))
    is_generated = models.BooleanField(_("Generated"), default=False)
    generated_date = models.DateTimeField(_("Generated Date"), null=True, blank=True)
    generated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("Generated By")
    )
    is_paid = models.BooleanField(_("Paid"), default=False)
    payment_date = models.DateField(_("Payment Date"), null=True, blank=True)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.company.name} - {self.year}-{self.month:02d}"

    class Meta:
        verbose_name = _("Salary Month")
        verbose_name_plural = _("Salary Months")
        unique_together = ('company', 'year', 'month')
        ordering = ['-year', '-month']


# ==================== EMPLOYEE SALARY ====================

class EmployeeSalary(models.Model):
    """Monthly salary record for each employee"""
    salary_month = models.ForeignKey(
        SalaryMonth, 
        on_delete=models.CASCADE, 
        related_name='employee_salaries',
        verbose_name=_("Salary Month")
    )
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='monthly_salaries',
        verbose_name=_("Employee")
    )
    basic_salary = models.DecimalField(_("Basic Salary"), max_digits=10, decimal_places=2)
    gross_salary = models.DecimalField(_("Gross Salary"), max_digits=10, decimal_places=2)
    total_earnings = models.DecimalField(_("Total Earnings"), max_digits=10, decimal_places=2)
    total_deductions = models.DecimalField(_("Total Deductions"), max_digits=10, decimal_places=2)
    net_salary = models.DecimalField(_("Net Salary"), max_digits=10, decimal_places=2)
    
    # Attendance based calculations
    working_days = models.PositiveIntegerField(_("Working Days"), default=0)
    present_days = models.PositiveIntegerField(_("Present Days"), default=0)
    absent_days = models.PositiveIntegerField(_("Absent Days"), default=0)
    leave_days = models.PositiveIntegerField(_("Leave Days"), default=0)
    
    # Overtime
    overtime_hours = models.DecimalField(_("Overtime Hours"), max_digits=5, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(_("Overtime Amount"), max_digits=10, decimal_places=2, default=0)
    
    # Additional
    bonus = models.DecimalField(_("Bonus"), max_digits=10, decimal_places=2, default=0)
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    def __str__(self):
        return f"{self.employee.name} - {self.salary_month}"

    class Meta:
        verbose_name = _("Employee Salary")
        verbose_name_plural = _("Employee Salaries")
        unique_together = ('salary_month', 'employee')
        ordering = ['-salary_month__year', '-salary_month__month', 'employee__name']


class SalaryDetail(models.Model):
    """Details of salary components for each employee salary"""
    salary = models.ForeignKey(
        EmployeeSalary, 
        on_delete=models.CASCADE, 
        related_name='details',
        verbose_name=_("Salary")
    )
    component = models.ForeignKey(
        SalaryComponent, 
        on_delete=models.CASCADE,
        verbose_name=_("Component")
    )
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    def __str__(self):
        return f"{self.salary.employee.name} - {self.component.name} - {self.amount}"

    class Meta:
        verbose_name = _("Salary Detail")
        verbose_name_plural = _("Salary Details")
        ordering = ['component__component_type', 'component__name']


# ==================== BONUS ====================

class Bonus(models.Model):
    """Employee bonus records"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='bonuses',
        verbose_name=_("Employee")
    )
    bonus_type = models.CharField(_("Bonus Type"), max_length=100)
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    bonus_date = models.DateField(_("Bonus Date"))
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    def __str__(self):
        return f"{self.employee.name} - {self.bonus_type} - {self.amount}"

    class Meta:
        verbose_name = _("Bonus")
        verbose_name_plural = _("Bonuses")
        ordering = ['-bonus_date']


# ==================== ADVANCE/LOAN ====================

class EmployeeAdvance(models.Model):
    """Employee advance/loan records"""
    STATUS_CHOICES = (
        ('PEN', 'Pending'),
        ('APP', 'Approved'),
        ('REJ', 'Rejected'),
        ('PAI', 'Paid'),
    )
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='advances',
        verbose_name=_("Employee")
    )
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    installments = models.PositiveIntegerField(_("Installments"))
    installment_amount = models.DecimalField(_("Installment Amount"), max_digits=10, decimal_places=2)
    application_date = models.DateField(_("Application Date"))
    approval_date = models.DateField(_("Approval Date"), null=True, blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("Approved By")
    )
    status = models.CharField(_("Status"), max_length=3, choices=STATUS_CHOICES, default='PEN')
    reason = models.TextField(_("Reason"))
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    def __str__(self):
        return f"{self.employee.name} - {self.amount} - {self.get_status_display()}"

    class Meta:
        verbose_name = _("Employee Advance")
        verbose_name_plural = _("Employee Advances")
        ordering = ['-application_date']