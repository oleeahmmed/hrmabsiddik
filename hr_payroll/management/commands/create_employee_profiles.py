from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from hr_payroll.models import Employee
from core.models import Company


class Command(BaseCommand):
    help = 'Create employee profiles for users who don\'t have them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            help='Company ID to assign to new employee profiles',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        dry_run = options.get('dry_run', False)
        
        # Get users without employee profiles
        users_without_employees = User.objects.filter(
            employee_user__isnull=True
        ).exclude(is_superuser=True)
        
        if not users_without_employees.exists():
            self.stdout.write(
                self.style.SUCCESS('All users already have employee profiles!')
            )
            return
        
        # Get company
        if company_id:
            try:
                company = Company.objects.get(id=company_id)
            except Company.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Company with ID {company_id} does not exist')
                )
                return
        else:
            # Get the first active company
            company = Company.objects.filter(is_active=True).first()
            if not company:
                self.stdout.write(
                    self.style.ERROR('No active company found. Please specify --company-id')
                )
                return
        
        self.stdout.write(f'Found {users_without_employees.count()} users without employee profiles')
        self.stdout.write(f'Will assign to company: {company.name} (ID: {company.id})')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        created_count = 0
        
        for user in users_without_employees:
            employee_id = f"EMP{user.id:04d}"
            
            # Check if employee_id already exists
            while Employee.objects.filter(employee_id=employee_id).exists():
                employee_id = f"EMP{user.id:04d}_{created_count + 1}"
            
            if dry_run:
                self.stdout.write(
                    f'Would create: {employee_id} - {user.get_full_name() or user.username} ({user.email})'
                )
            else:
                employee = Employee.objects.create(
                    company=company,
                    employee_id=employee_id,
                    name=user.get_full_name() or user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    user=user,
                    is_active=True
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created: {employee.employee_id} - {employee.name} ({employee.email})'
                    )
                )
            
            created_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'Would create {created_count} employee profiles')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created {created_count} employee profiles')
            )