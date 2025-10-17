"""
Payroll Demo Data Import Script for SignTech
Run: python payroll_import.py
"""

import os
import sys
import django
from datetime import date
from decimal import Decimal
import random

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Django setup - configure settings first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    django.setup()
    
    from django.contrib.auth.models import User
    from core.models import Company
    from hr_payroll.models import Employee
    from payroll.models import (
        SalaryComponent, EmployeeSalaryStructure, SalaryStructureComponent,
        SalaryMonth, EmployeeSalary, SalaryDetail, Bonus, EmployeeAdvance
    )
    
except django.core.exceptions.ImproperlyConfigured:
    print("❌ Django settings not configured properly.")
    print("💡 Make sure you're running this from the project root directory.")
    sys.exit(1)
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure all apps are properly installed in settings.py")
    sys.exit(1)

def create_payroll_demo_data():
    print("🚀 Starting payroll demo data import for SignTech...")
    
    # ==================== ১. কোম্পানি পাওয়া ====================
    print("📋 Getting Company...")
    
    try:
        company = Company.objects.get(company_code="SIGNTECH")
        print(f"✅ Company found: {company.name}")
    except Company.DoesNotExist:
        print("❌ Company not found. Please run core demo data import first.")
        return
    
    # ==================== ২. অ্যাডমিন ইউজার পাওয়া ====================
    print("\n👤 Getting Admin User...")
    
    try:
        admin_user = User.objects.get(username='rahul')
        print(f"✅ Admin user found: {admin_user.get_full_name()}")
    except User.DoesNotExist:
        print("❌ Admin user not found. Please run core demo data import first.")
        return
    
    # ==================== ৩. এমপ্লয়ী পাওয়া ====================
    print("\n👥 Getting Employees...")
    
    employees = Employee.objects.filter(company=company, is_active=True)
    if not employees:
        print("❌ No active employees found. Please create employees in HR system first.")
        print("💡 Run: python import_demo_data.py first")
        return
    
    print(f"✅ Found {employees.count()} active employees")
    
    # ==================== ৪. স্যালারি কম্পোনেন্ট তৈরি ====================
    print("\n📊 Creating Salary Components...")
    
    components_data = [
        # আয় (Earnings)
        {'name': 'Basic Salary', 'code': 'BASIC', 'type': 'EARN', 'taxable': True},
        {'name': 'House Rent Allowance', 'code': 'HRA', 'type': 'EARN', 'taxable': True},
        {'name': 'Medical Allowance', 'code': 'MEDICAL', 'type': 'EARN', 'taxable': True},
        {'name': 'Transport Allowance', 'code': 'TRANSPORT', 'type': 'EARN', 'taxable': True},
        {'name': 'Special Allowance', 'code': 'SPECIAL', 'type': 'EARN', 'taxable': True},
        {'name': 'Overtime', 'code': 'OVERTIME', 'type': 'EARN', 'taxable': True},
        
        # কর্তন (Deductions)
        {'name': 'Provident Fund', 'code': 'PF', 'type': 'DED', 'taxable': False},
        {'name': 'Tax', 'code': 'TAX', 'type': 'DED', 'taxable': False},
        {'name': 'Advance Deduction', 'code': 'ADVANCE', 'type': 'DED', 'taxable': False},
        {'name': 'Other Deduction', 'code': 'OTHER_DED', 'type': 'DED', 'taxable': False},
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
        if created:
            print(f"   ✅ Component created: {component.name}")
        else:
            print(f"   ℹ️ Component exists: {component.name}")

    # ==================== ৫. স্যালারি স্ট্রাকচার তৈরি ====================
    print("\n💰 Creating Salary Structures...")
    
    for employee in employees:
        # Determine basic salary
        base_salary = Decimal('25000.00')
        if hasattr(employee, 'designation') and employee.designation:
            designation_name = employee.designation.name.lower()
            if 'manager' in designation_name:
                base_salary = Decimal('55000.00')
            elif 'senior' in designation_name:
                base_salary = Decimal('40000.00')
            elif 'lead' in designation_name:
                base_salary = Decimal('45000.00')
        
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
                # Earnings (percentage of basic)
                {'component': components['HRA'], 'percentage': Decimal('45.00')},
                {'component': components['MEDICAL'], 'amount': Decimal('2500.00')},
                {'component': components['TRANSPORT'], 'amount': Decimal('2000.00')},
                {'component': components['SPECIAL'], 'percentage': Decimal('15.00')},
                
                # Deductions (percentage of gross)
                {'component': components['PF'], 'percentage': Decimal('10.00')},
                {'component': components['TAX'], 'percentage': Decimal('7.50')},
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
            
            print(f"   ✅ Structure created: {employee.name} - Basic ৳{base_salary}, Net ৳{structure.net_salary}")

    # ==================== ৬. স্যালারি মাস তৈরি ====================
    print("\n📅 Creating Salary Months...")
    
    current_year = 2024
    months = [1, 2, 3]  # January, February, March
    
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

    # ==================== ৭. এমপ্লয়ী স্যালারি তৈরি ====================
    print("\n💵 Generating Employee Salaries...")
    
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
            overtime_hours = Decimal(str(random.uniform(0, 25)))
            overtime_amount = overtime_hours * Decimal('250.00')  # ৳250/hour
            
            # Random bonus
            bonus_amount = Decimal('0.00')
            if random.random() > 0.7:  # 30% chance
                bonus_amount = Decimal(str(random.randint(2000, 8000)))
            
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
            
            # Add overtime if applicable
            if overtime_amount > 0:
                SalaryDetail.objects.create(
                    salary=employee_salary,
                    component=components['OVERTIME'],
                    amount=overtime_amount
                )
            
            print(f"   ✅ Salary: {employee.name} - {salary_month}: ৳{employee_salary.net_salary}")

    # ==================== ৮. বোনাস তৈরি ====================
    print("\n🎉 Creating Bonus Records...")
    
    bonus_types = ['Performance Bonus', 'Festival Bonus', 'Annual Bonus', 'Special Bonus']
    
    for employee in employees:
        if random.random() > 0.5:  # 50% chance
            bonus = Bonus.objects.create(
                employee=employee,
                bonus_type=random.choice(bonus_types),
                amount=Decimal(str(random.randint(5000, 25000))),
                bonus_date=date(2024, 2, 15),
                remarks="Performance based bonus"
            )
            print(f"   ✅ Bonus: {employee.name} - {bonus.bonus_type} - ৳{bonus.amount}")

    # ==================== ৯. অ্যাডভান্স তৈরি ====================
    print("\n🏦 Creating Advance Records...")
    
    for employee in employees[:3]:  # Only for first 3 employees
        if random.random() > 0.7:  # 30% chance
            advance_amount = Decimal(str(random.randint(8000, 20000)))
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
            print(f"   ✅ Advance: {employee.name} - ৳{advance.amount} ({installments} installments)")

    # ==================== Summary ====================
    print(f"\n🎉 Payroll Demo Data Import Completed Successfully!")
    print(f"\n📊 Summary:")
    print(f"   • Salary Components: {SalaryComponent.objects.count()}")
    print(f"   • Salary Structures: {EmployeeSalaryStructure.objects.count()}")
    print(f"   • Salary Months: {SalaryMonth.objects.count()}")
    print(f"   • Employee Salaries: {EmployeeSalary.objects.count()}")
    print(f"   • Bonuses: {Bonus.objects.count()}")
    print(f"   • Advances: {EmployeeAdvance.objects.count()}")
    print(f"\n💼 Payroll Admin: http://localhost:8000/admin/payroll/")

if __name__ == "__main__":
    create_payroll_demo_data()