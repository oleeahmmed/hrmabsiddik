# payroll/demo_data.py
"""
Demo data import script for Payroll app
Run with: python manage.py runscript payroll.demo_data
"""

from django.contrib.auth.models import User
from core.models import Company
from hr_payroll.models import Employee
from payroll.models import (
    SalaryComponent, EmployeeSalaryStructure, SalaryStructureComponent,
    SalaryMonth, EmployeeSalary, SalaryDetail, Bonus, EmployeeAdvance
)
from decimal import Decimal
from datetime import date, timedelta
import random


def run():
    """Main function to import demo data"""
    print("🚀 Starting payroll demo data import...")
    
    # Get or create company
    company, created = Company.objects.get_or_create(
        name="Demo Company Ltd.",
        defaults={
            'address': "123 Demo Street, Demo City",
            'phone': "+880123456789",
            'email': "info@democompany.com",
        }
    )
    
    # Get admin user
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        print("❌ No superuser found. Please create a superuser first.")
        return
    
    # Create Salary Components
    print("📊 Creating salary components...")
    components_data = [
        # Earnings
        {'name': 'Basic Salary', 'code': 'BASIC', 'type': 'EARN', 'taxable': True},
        {'name': 'House Rent Allowance', 'code': 'HRA', 'type': 'EARN', 'taxable': True},
        {'name': 'Medical Allowance', 'code': 'MEDICAL', 'type': 'EARN', 'taxable': True},
        {'name': 'Transport Allowance', 'code': 'TRANSPORT', 'type': 'EARN', 'taxable': True},
        {'name': 'Special Allowance', 'code': 'SPECIAL', 'type': 'EARN', 'taxable': True},
        
        # Deductions
        {'name': 'Provident Fund', 'code': 'PF', 'type': 'DED', 'taxable': False},
        {'name': 'Tax', 'code': 'TAX', 'type': 'DED', 'taxable': False},
        {'name': 'Advance Deduction', 'code': 'ADVANCE', 'type': 'DED', 'taxable': False},
    ]
    
    components = {}
    for comp_data in components_data:
        component, created = SalaryComponent.objects.get_or_create(
            company=company,
            code=comp_data['code'],
            defaults={
                'name': comp_data['name'],
                'component_type': comp_data['type'],
                'is_taxable': comp_data['taxable'],
                'description': f"{comp_data['name']} component"
            }
        )
        components[comp_data['code']] = component
        print(f"   ✅ {component.name}")

    # Get employees
    employees = Employee.objects.filter(company=company, is_active=True)[:5]
    if not employees:
        print("❌ No active employees found. Please create employees first.")
        return

    # Create Salary Structures for employees
    print("\n💰 Creating salary structures...")
    for employee in employees:
        # Determine base salary based on designation
        base_salary = Decimal('25000.00')
        if employee.designation:
            if 'manager' in employee.designation.name.lower():
                base_salary = Decimal('50000.00')
            elif 'senior' in employee.designation.name.lower():
                base_salary = Decimal('35000.00')
        
        # Create salary structure
        structure, created = EmployeeSalaryStructure.objects.get_or_create(
            employee=employee,
            defaults={
                'effective_date': date(2024, 1, 1),
                'basic_salary': base_salary,
            }
        )
        
        if created:
            # Add components to structure
            structure_components = [
                # Earnings (percentages of basic)
                {'component': components['HRA'], 'percentage': Decimal('50.00')},
                {'component': components['MEDICAL'], 'amount': Decimal('2000.00')},
                {'component': components['TRANSPORT'], 'amount': Decimal('1500.00')},
                {'component': components['SPECIAL'], 'percentage': Decimal('10.00')},
                
                # Deductions (percentages of gross)
                {'component': components['PF'], 'percentage': Decimal('10.00')},
                {'component': components['TAX'], 'percentage': Decimal('5.00')},
            ]
            
            for comp_data in structure_components:
                SalaryStructureComponent.objects.create(
                    salary_structure=structure,
                    component=comp_data['component'],
                    amount=comp_data.get('amount'),
                    percentage=comp_data.get('percentage'),
                    is_active=True
                )
            
            # Calculate totals
            structure.calculate_totals()
            structure.save()
            
            print(f"   ✅ Salary structure for {employee.name}: Basic {base_salary}, Net {structure.net_salary}")

    # Create Salary Months
    print("\n📅 Creating salary months...")
    current_year = 2024
    months = [1, 2, 3]  # Jan, Feb, Mar
    
    for month in months:
        salary_month, created = SalaryMonth.objects.get_or_create(
            company=company,
            year=current_year,
            month=month,
            defaults={
                'is_generated': True,
                'generated_by': admin_user,
                'generated_date': date(current_year, month, 28),
            }
        )
        
        if created:
            print(f"   ✅ Salary month: {current_year}-{month:02d}")

    # Create Employee Salaries
    print("\n💵 Generating employee salaries...")
    salary_months = SalaryMonth.objects.filter(company=company, is_generated=True)
    
    for salary_month in salary_months:
        for employee in employees:
            # Skip if salary already exists
            if EmployeeSalary.objects.filter(salary_month=salary_month, employee=employee).exists():
                continue
            
            try:
                structure = employee.payroll_salary_structure
            except EmployeeSalaryStructure.DoesNotExist:
                continue
            
            # Simulate attendance data
            working_days = 22
            present_days = random.randint(18, 22)
            absent_days = random.randint(0, 2)
            leave_days = working_days - present_days - absent_days
            
            # Simulate overtime
            overtime_hours = Decimal(str(random.uniform(0, 20)))
            overtime_amount = overtime_hours * Decimal('200.00')  # Assume 200/hour rate
            
            # Random bonus
            bonus_amount = Decimal('0.00')
            if random.random() > 0.7:  # 30% chance of bonus
                bonus_amount = Decimal(str(random.randint(1000, 5000)))
            
            # Create salary record
            employee_salary = EmployeeSalary.objects.create(
                salary_month=salary_month,
                employee=employee,
                basic_salary=structure.basic_salary,
                gross_salary=structure.gross_salary + overtime_amount + bonus_amount,
                total_earnings=structure.total_earnings + overtime_amount + bonus_amount,
                total_deductions=structure.total_deductions,
                net_salary=structure.net_salary + overtime_amount + bonus_amount,
                working_days=working_days,
                present_days=present_days,
                absent_days=absent_days,
                leave_days=leave_days,
                overtime_hours=overtime_hours,
                overtime_amount=overtime_amount,
                bonus=bonus_amount,
            )
            
            # Create salary details
            for structure_component in structure.structure_components.filter(is_active=True):
                SalaryDetail.objects.create(
                    salary=employee_salary,
                    component=structure_component.component,
                    amount=structure_component.calculated_amount
                )
            
            # Add overtime as earning if applicable
            if overtime_amount > 0:
                SalaryDetail.objects.create(
                    salary=employee_salary,
                    component=components['SPECIAL'],  # Use special allowance for overtime
                    amount=overtime_amount
                )
            
            print(f"   ✅ Salary for {employee.name} - {salary_month}: ₱{employee_salary.net_salary}")

    # Create Bonuses
    print("\n🎉 Creating bonus records...")
    bonus_types = ['Performance Bonus', 'Festival Bonus', 'Annual Bonus', 'Special Bonus']
    
    for employee in employees:
        if random.random() > 0.5:  # 50% chance of bonus
            bonus = Bonus.objects.create(
                employee=employee,
                bonus_type=random.choice(bonus_types),
                amount=Decimal(str(random.randint(5000, 20000))),
                bonus_date=date(2024, 2, 15),
                remarks="Performance based bonus"
            )
            print(f"   ✅ Bonus for {employee.name}: {bonus.bonus_type} - ₱{bonus.amount}")

    # Create Employee Advances
    print("\n🏦 Creating advance records...")
    for employee in employees[:3]:  # Only for first 3 employees
        if random.random() > 0.7:  # 30% chance of advance
            advance_amount = Decimal(str(random.randint(5000, 15000)))
            installments = random.randint(3, 6)
            
            advance = EmployeeAdvance.objects.create(
                employee=employee,
                amount=advance_amount,
                installments=installments,
                installment_amount=advance_amount / installments,
                application_date=date(2024, 1, 10),
                status='APP',
                approved_by=admin_user,
                approval_date=date(2024, 1, 12),
                reason="Emergency financial requirement",
                remarks="Approved by management"
            )
            print(f"   ✅ Advance for {employee.name}: ₱{advance.amount} in {installments} installments")

    print(f"\n🎉 Payroll demo data import completed successfully!")
    print(f"📊 Summary:")
    print(f"   • Salary Components: {SalaryComponent.objects.count()}")
    print(f"   • Salary Structures: {EmployeeSalaryStructure.objects.count()}")
    print(f"   • Salary Months: {SalaryMonth.objects.count()}")
    print(f"   • Employee Salaries: {EmployeeSalary.objects.count()}")
    print(f"   • Bonuses: {Bonus.objects.count()}")
    print(f"   • Advances: {EmployeeAdvance.objects.count()}")