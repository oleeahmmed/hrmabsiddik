from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, Case, When, DecimalField, Avg
from decimal import Decimal
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Extended User Profile with Company Association"""
    GENDER_CHOICES = [
        ('male', _('Male')),
        ('female', _('Female')),
        ('other', _('Other')),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_("User")
    )
    company = models.ForeignKey(
        'Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_profiles',
        verbose_name=_("Company")
    )
    
    # Personal Information
    phone_number = models.CharField(_("Phone Number"), max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(_("Date of Birth"), blank=True, null=True)
    gender = models.CharField(_("Gender"), max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    profile_picture = models.ImageField(_("Profile Picture"), upload_to='user_profiles/', blank=True, null=True)
    
    # Address Information
    address_line1 = models.CharField(_("Address Line 1"), max_length=255, blank=True, null=True)
    address_line2 = models.CharField(_("Address Line 2"), max_length=255, blank=True, null=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)
    state = models.CharField(_("State/Province"), max_length=100, blank=True, null=True)
    zip_code = models.CharField(_("ZIP/Postal Code"), max_length=20, blank=True, null=True)
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True)
    
    # Professional Information
    designation = models.CharField(_("Designation"), max_length=100, blank=True, null=True)
    department = models.CharField(_("Department"), max_length=100, blank=True, null=True)
    employee_id = models.CharField(_("Employee ID"), max_length=50, blank=True, null=True, unique=True)
    joining_date = models.DateField(_("Joining Date"), blank=True, null=True)
    
    # Additional Information
    bio = models.TextField(_("Bio"), blank=True, null=True)
    emergency_contact_name = models.CharField(_("Emergency Contact Name"), max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(_("Emergency Contact Phone"), max_length=20, blank=True, null=True)
    emergency_contact_relation = models.CharField(_("Emergency Contact Relation"), max_length=50, blank=True, null=True)
    
    # System Fields
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.company.name if self.company else 'No Company'}"
    
    def get_full_name(self):
        """Get user's full name"""
        return self.user.get_full_name() or self.user.username
    
    def get_age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year
            if today.month < self.date_of_birth.month or (today.month == self.date_of_birth.month and today.day < self.date_of_birth.day):
                age -= 1
            return age
        return None
    
    def get_full_address(self):
        """Get formatted full address"""
        address_parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.zip_code,
            self.country
        ]
        return ", ".join(filter(None, address_parts))


# Signal to automatically create UserProfile when User is created
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()


class Company(models.Model):
    """Represents a company in the multi-company system."""
    company_code = models.CharField(_("Company Code"), max_length=20, unique=True)
    name = models.CharField(_("Name"), max_length=100)
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    website = models.URLField(max_length=255, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True, help_text="e.g., VAT, EIN, GST")
    currency = models.CharField(max_length=10, default='USD', help_text="e.g., USD, EUR, GBP")
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    location_restricted = models.BooleanField(
        _("Location Restricted"),
        default=True,
        help_text=_("If enabled, employees must be within location radius to mark attendance")
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        ordering = ['name']

    def __str__(self):
        return self.name

    @classmethod
    def get_active_company(cls):
        """Return the first active company."""
        return cls.objects.filter(is_active=True).first()


class ProjectRole(models.Model):
    """প্রজেক্ট রোল সংজ্ঞা - হায়ারার্কি অনুযায়ী"""
    ROLE_CHOICES = [
        ('admin', _('Admin')),
        ('technical_lead', _('Technical Lead')),
        ('project_manager', _('Project Manager')),
        ('supervisor', _('Supervisor')),
        ('employee', _('Employee')),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)
    hierarchy_level = models.IntegerField(default=0, help_text="০=Admin, ১=Tech Lead, ২=PM, ৩=Supervisor, ৪=Employee")
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['hierarchy_level']
    
    def __str__(self):
        return f"{self.get_role_display()} (Level {self.hierarchy_level})"


class Project(models.Model):
    """প্রজেক্ট তথ্য এবং সেটআপ"""
    STATUS_CHOICES = [
        ('planning', _('Planning')),
        ('in_progress', _('In Progress')),
        ('on_hold', _('On Hold')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    
    # ✅ Changed to User model instead of Employee
    technical_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='led_projects',
        verbose_name=_("Technical Lead")
    )
    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='managed_projects',
        verbose_name=_("Project Manager")
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    total_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    spent_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def get_progress_percentage(self):
        """প্রজেক্টের অগ্রগতি শতাংশ"""
        total_tasks = self.tasks.count()
        if total_tasks == 0:
            return 0
        completed_tasks = self.tasks.filter(status='completed').count()
        return round((completed_tasks / total_tasks) * 100, 2)

    def get_task_distribution(self):
        """টাস্ক বিতরণ"""
        return {
            'total': self.tasks.count(),
            'todo': self.tasks.filter(status='todo').count(),
            'in_progress': self.tasks.filter(status='in_progress').count(),
            'on_hold': self.tasks.filter(status='on_hold').count(),
            'completed': self.tasks.filter(status='completed').count(),
        }

    def get_total_hours(self):
        """মোট ঘন্টা ব্যয়"""
        result = self.tasks.aggregate(total=Sum('actual_hours'))
        return result['total'] or Decimal('0')

    def get_budget_status(self):
        """বাজেট স্ট্যাটাস"""
        if not self.total_budget:
            return {'remaining': None, 'percentage_used': None, 'is_over_budget': False}
        
        remaining = self.total_budget - self.spent_budget
        percentage = (self.spent_budget / self.total_budget * 100) if self.total_budget > 0 else 0
        
        return {
            'remaining': remaining,
            'percentage_used': round(percentage, 2),
            'is_over_budget': self.spent_budget > self.total_budget
        }

    def get_overdue_tasks(self):
        """সময়মতো না হওয়া টাস্ক"""
        today = timezone.now().date()
        return self.tasks.filter(
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        ).count()

    def get_upcoming_tasks(self, days=7):
        """আগামী ৭ দিনের টাস্ক"""
        today = timezone.now().date()
        future_date = today + timedelta(days=days)
        return self.tasks.filter(
            due_date__range=[today, future_date],
            status__in=['todo', 'in_progress']
        ).order_by('due_date')

    def get_blocked_tasks(self):
        """ব্লক করা টাস্ক (সমস্যা আছে এমন)"""
        return self.tasks.filter(is_blocked=True)

    def get_team_members(self):
        """প্রজেক্টে নিয়োজিত সকল টিম মেম্বার"""
        from hr_payroll.models import Employee
        return Employee.objects.filter(
            id__in=self.tasks.values_list('assigned_to_id', flat=True).distinct()
        )

    def get_summary(self):
        """প্রজেক্ট সামারি - ড্যাশবোর্ডের জন্য"""
        return {
            'name': self.name,
            'status': self.get_status_display(),
            'progress': self.get_progress_percentage(),
            'tasks': self.get_task_distribution(),
            'overdue': self.get_overdue_tasks(),
            'blocked': self.get_blocked_tasks().count(),
            'budget': self.get_budget_status(),
            'total_hours': float(self.get_total_hours()),
            'days_remaining': (self.end_date - timezone.now().date()).days,
        }


class TaskChecklist(models.Model):
    """টাস্কের সাব-চেকলিস্ট আইটেম"""
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Task(models.Model):
    """টাস্ক ম্যানেজমেন্ট"""
    STATUS_CHOICES = [
        ('todo', _('To Do')),
        ('in_progress', _('In Progress')),
        ('on_hold', _('On Hold')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]
    
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    
    # ✅ Changed to User model
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_tasks'
    )
    # ✅ Keep Employee for assigned_to
    assigned_to = models.ForeignKey(
        'hr_payroll.Employee', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='my_tasks'
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    due_date = models.DateField()
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    # সমস্যা ট্র্যাকিং
    is_blocked = models.BooleanField(default=False)
    blocking_reason = models.TextField(blank=True, null=True)
    
    # চেকলিস্ট
    checklists = models.ManyToManyField(TaskChecklist, blank=True, related_name='tasks')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        ordering = ['due_date', '-priority', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.assigned_to}"

    def mark_completed(self):
        """টাস্ক সম্পন্ন চিহ্নিত করুন"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def mark_blocked(self, reason):
        """টাস্ক ব্লক করুন (সমস্যার কারণ সহ)"""
        self.is_blocked = True
        self.blocking_reason = reason
        self.status = 'on_hold'
        self.save()

    def unblock(self):
        """টাস্ক আনব্লক করুন"""
        self.is_blocked = False
        self.blocking_reason = None
        self.status = 'in_progress'
        self.save()

    def is_overdue(self):
        """ডেডলাইন পেরিয়ে গেছে?"""
        if self.status == 'completed':
            return False
        return timezone.now().date() > self.due_date

    def get_days_until_due(self):
        """ডেডলাইন পর্যন্ত কত দিন"""
        days = (self.due_date - timezone.now().date()).days
        return days

    def get_progress_percentage(self):
        """টাস্কের অগ্রগতি শতাংশ (চেকলিস্ট ভিত্তিতে)"""
        checklists = self.checklists.all().count()
        if checklists == 0:
            return 100 if self.status == 'completed' else 0
        completed = self.checklists.filter(is_completed=True).count()
        return round((completed / checklists) * 100, 2)

    def get_efficiency_ratio(self):
        """দক্ষতা অনুপাত (প্রকৃত ঘন্টা / অনুমানিত ঘন্টা)"""
        if self.estimated_hours == 0:
            return 0
        ratio = float(self.actual_hours) / float(self.estimated_hours)
        return round(ratio * 100, 2)


class TaskComment(models.Model):
    """টাস্কে মন্তব্য ট্র্যাকিং"""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    
    # ✅ Changed to User model
    commented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.commented_by} on {self.task.title}"


class ProjectMember(models.Model):
    """প্রজেক্টে কর্মচারীর ভূমিকা এবং দায়িত্ব"""
    ROLE_CHOICES = [
        ('technical_lead', _('Technical Lead')),
        ('project_manager', _('Project Manager')),
        ('supervisor', _('Supervisor')),
        ('employee', _('Employee')),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    
    # ✅ Keep Employee
    employee = models.ForeignKey(
        'hr_payroll.Employee',
        on_delete=models.CASCADE
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    # এই সদস্য কার অধীনে কাজ করে
    reporting_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates'
    )
    
    joined_date = models.DateField(auto_now_add=True)
    left_date = models.DateField(null=True, blank=True)
    
    class Meta:
        unique_together = ('project', 'employee')
        ordering = ['role', 'employee__name']

    def __str__(self):
        return f"{self.employee.name} - {self.get_role_display()}"

    def get_team(self):
        """এই সদস্যের অধীনের সকলকে পান"""
        return self.subordinates.filter(left_date__isnull=True)


class ProjectReport(models.Model):
    """প্রজেক্ট রিপোর্ট এবং অগ্রগতি ট্র্যাকিং"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    
    # ✅ Changed to User model
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True
    )
    
    report_date = models.DateField()
    
    # প্রগ্রেস ডেটা
    completed_tasks = models.IntegerField(default=0)
    pending_tasks = models.IntegerField(default=0)
    blocked_tasks = models.IntegerField(default=0)
    total_hours_logged = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # সমস্যা এবং পরিকল্পনা
    issues_summary = models.TextField(blank=True, null=True)
    planned_activities = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # বাজেট আপডেট
    budget_spent_this_period = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-report_date']
        verbose_name = _("Project Report")
        verbose_name_plural = _("Project Reports")

    def __str__(self):
        return f"Report: {self.project.name} - {self.report_date}"


class DailyTimeLog(models.Model):
    """প্রতিদিনের সময় লগ"""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    
    # ✅ Keep Employee
    logged_by = models.ForeignKey(
        'hr_payroll.Employee',
        on_delete=models.SET_NULL, 
        null=True
    )
    
    log_date = models.DateField()
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Daily Time Log")
        verbose_name_plural = _("Daily Time Logs")
        ordering = ['-log_date']

    def __str__(self):
        return f"{self.task.title} - {self.log_date} ({self.hours_worked}h)"