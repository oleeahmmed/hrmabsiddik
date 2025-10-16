from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


# ==================== BASE MODELS ====================

class TimeStampedModel(models.Model):
    """Abstract base model with timestamp fields"""
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        abstract = True


class OwnedModel(models.Model):
    """Abstract base model with owner and company"""
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_owned",
        verbose_name=_("Owner")
    )
    company = models.ForeignKey(
        'Company',
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_items",
        verbose_name=_("Company")
    )
    
    class Meta:
        abstract = True
    
    def clean(self):
        """Validate that owner belongs to the company"""
        if self.owner and self.company:
            if not hasattr(self.owner, 'profile') or self.owner.profile.company != self.company:
                raise ValidationError({
                    'owner': _('Owner must belong to the selected company.')
                })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)



class Company(TimeStampedModel):
    """
    Multi-level Company Model with Parent-Child Hierarchy
    Supports unlimited nesting of companies (subsidiaries)
    """
    # Basic Information
    company_code = models.CharField(
        _("Company Code"), 
        max_length=20, 
        unique=True,
        db_index=True,
        help_text=_("Unique identifier for the company")
    )
    name = models.CharField(_("Company Name"), max_length=200, db_index=True)
    
    # Hierarchy Support
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subsidiaries',
        verbose_name=_("Parent Company"),
        help_text=_("Leave empty for root company")
    )
    
    # Address Information
    address_line1 = models.CharField(_("Address Line 1"), max_length=255, blank=True)
    address_line2 = models.CharField(_("Address Line 2"), max_length=255, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    state = models.CharField(_("State/Province"), max_length=100, blank=True)
    zip_code = models.CharField(_("ZIP/Postal Code"), max_length=20, blank=True)
    country = models.CharField(_("Country"), max_length=100, default='Bangladesh')
    
    # Contact Information
    phone_number = models.CharField(_("Phone Number"), max_length=20, blank=True)
    email = models.EmailField(_("Email"), max_length=255, blank=True)
    website = models.URLField(_("Website"), max_length=255, blank=True)
    
    # Business Information
    tax_id = models.CharField(
        _("Tax ID"), 
        max_length=50, 
        blank=True,
        help_text=_("VAT/EIN/GST/TIN Number")
    )
    registration_number = models.CharField(
        _("Registration Number"),
        max_length=50,
        blank=True
    )
    currency = models.CharField(
        _("Currency"),
        max_length=10,
        default='BDT',
        help_text=_("e.g., BDT, USD, EUR")
    )
    
    # Settings
    logo = models.ImageField(_("Logo"), upload_to='company_logos/', blank=True, null=True)
    location_restricted = models.BooleanField(
        _("Location Restricted"),
        default=True,
        help_text=_("If enabled, employees must be within location radius for attendance")
    )
    
    # Hierarchy Level (auto-calculated)
    level = models.PositiveIntegerField(_("Hierarchy Level"), default=0, editable=False)
    
    # Status
    is_active = models.BooleanField(_("Is Active"), default=True, db_index=True)
    
    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['company_code']),
            models.Index(fields=['parent', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.company_code})"
    
    def clean(self):
        """Validate company data"""
        super().clean()
        
        # Prevent circular reference
        if self.parent:
            if self.parent == self:
                raise ValidationError({'parent': _('A company cannot be its own parent.')})
            
            # Check for circular hierarchy
            parent = self.parent
            visited = {self}
            while parent:
                if parent in visited:
                    raise ValidationError({
                        'parent': _('Circular reference detected in company hierarchy.')
                    })
                visited.add(parent)
                parent = parent.parent
        
        # Validate company code format
        if not self.company_code.isalnum():
            raise ValidationError({
                'company_code': _('Company code must contain only letters and numbers.')
            })
    
    def save(self, *args, **kwargs):
        # Calculate hierarchy level
        self.level = self._calculate_level()
        self.full_clean()
        super().save(*args, **kwargs)
    
    def _calculate_level(self):
        """Calculate the hierarchy level of this company"""
        if not self.parent:
            return 0
        level = 0
        parent = self.parent
        while parent:
            level += 1
            parent = parent.parent
        return level
    
    def get_all_subsidiaries(self, include_self=True):
        """Get all subsidiaries recursively"""
        subsidiaries = list(self.subsidiaries.all())
        for sub in self.subsidiaries.all():
            subsidiaries.extend(sub.get_all_subsidiaries(include_self=False))
        
        if include_self:
            return [self] + subsidiaries
        return subsidiaries
    
    def get_root_company(self):
        """Get the root company in the hierarchy"""
        if not self.parent:
            return self
        return self.parent.get_root_company()
    
    def get_hierarchy_path(self):
        """Get the full hierarchy path as a list"""
        path = [self]
        parent = self.parent
        while parent:
            path.insert(0, parent)
            parent = parent.parent
        return path
    
    def get_hierarchy_display(self):
        """Get hierarchy as a string (e.g., 'Root > Sub1 > Sub2')"""
        return " > ".join([c.name for c in self.get_hierarchy_path()])
    
    @classmethod
    def get_active_company(cls):
        """Return the first active company"""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_root_companies(cls):
        """Get all root companies (companies without parent)"""
        return cls.objects.filter(parent__isnull=True, is_active=True)
    
class UserProfile(TimeStampedModel):
    """Extended User Profile - Mandatory Company Association"""
    GENDER_CHOICES = [
        ('male', _('Male')),
        ('female', _('Female')),
        ('other', _('Other')),
    ]
    
    # Core Fields
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_("User")
    )
    company = models.ForeignKey(
        'Company',
        on_delete=models.PROTECT,
        related_name='user_profiles',
        verbose_name=_("Company"),
        help_text=_("User must be associated with a company")
    )
    
    # Personal Information
    phone_number = models.CharField(_("Phone Number"), max_length=20, blank=True)
    date_of_birth = models.DateField(_("Date of Birth"), blank=True, null=True)
    gender = models.CharField(_("Gender"), max_length=10, choices=GENDER_CHOICES, blank=True)
    profile_picture = models.ImageField(
        _("Profile Picture"),
        upload_to='user_profiles/',
        blank=True,
        null=True
    )
    
    # Address Information
    address_line1 = models.CharField(_("Address Line 1"), max_length=255, blank=True)
    address_line2 = models.CharField(_("Address Line 2"), max_length=255, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    state = models.CharField(_("State/Province"), max_length=100, blank=True)
    zip_code = models.CharField(_("ZIP/Postal Code"), max_length=20, blank=True)
    country = models.CharField(_("Country"), max_length=100, blank=True)
    
    # Professional Information
    designation = models.CharField(_("Designation"), max_length=100, blank=True)
    department = models.CharField(_("Department"), max_length=100, blank=True)
    employee_id = models.CharField(
        _("Employee ID"),
        max_length=50,
        blank=True,
        unique=True,
        null=True
    )
    joining_date = models.DateField(_("Joining Date"), blank=True, null=True)
    
    # Additional Information
    bio = models.TextField(_("Bio"), blank=True)
    emergency_contact_name = models.CharField(
        _("Emergency Contact Name"),
        max_length=100,
        blank=True
    )
    emergency_contact_phone = models.CharField(
        _("Emergency Contact Phone"),
        max_length=20,
        blank=True
    )
    emergency_contact_relation = models.CharField(
        _("Emergency Contact Relation"),
        max_length=50,
        blank=True
    )
    
    # Status
    is_active = models.BooleanField(_("Is Active"), default=True, db_index=True)
    
    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['employee_id']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} - {self.company.name}"
    
    def clean(self):
        """Validate user profile data"""
        super().clean()
        
        # Ensure company is set
        if not self.company:
            raise ValidationError({
                'company': _('User must be associated with a company.')
            })
        
        # Validate employee_id uniqueness within company
        if self.employee_id:
            existing = UserProfile.objects.filter(
                employee_id=self.employee_id,
                company=self.company
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({
                    'employee_id': _('Employee ID must be unique within the company.')
                })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_full_name(self):
        """Get user's full name"""
        return self.user.get_full_name() or self.user.username
    
    def get_age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year
            if today.month < self.date_of_birth.month or \
               (today.month == self.date_of_birth.month and today.day < self.date_of_birth.day):
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

# ==================== PROJECT ROLE MODEL ====================

class ProjectRole(models.Model):
    """Project Roles - Hierarchy based"""
    ROLE_CHOICES = [
        ('admin', _('Admin')),
        ('technical_lead', _('Technical Lead')),
        ('project_manager', _('Project Manager')),
        ('supervisor', _('Supervisor')),
        ('employee', _('Employee')),
    ]
    
    role = models.CharField(
        _("Role"),
        max_length=20,
        choices=ROLE_CHOICES,
        unique=True
    )
    hierarchy_level = models.IntegerField(
        _("Hierarchy Level"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("0=Admin, 1=Tech Lead, 2=PM, 3=Supervisor, 4=Employee")
    )
    description = models.TextField(_("Description"), blank=True)
    
    class Meta:
        ordering = ['hierarchy_level']
        verbose_name = _("Project Role")
        verbose_name_plural = _("Project Roles")
    
    def __str__(self):
        return f"{self.get_role_display()} (Level {self.hierarchy_level})"


# ==================== PROJECT MODEL ====================

class Project(OwnedModel, TimeStampedModel):
    """Project Management with Company Ownership"""
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
    
    # Leadership
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
    
    # Basic Information
    name = models.CharField(_("Project Name"), max_length=255, db_index=True)
    description = models.TextField(_("Description"), blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='planning',
        db_index=True
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    
    # Timeline
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    
    # Budget
    total_budget = models.DecimalField(
        _("Total Budget"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    spent_budget = models.DecimalField(
        _("Spent Budget"),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Status
    is_active = models.BooleanField(_("Is Active"), default=True, db_index=True)
    
    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['company', 'is_active', 'status']),
            models.Index(fields=['owner', 'company']),
        ]
        unique_together = [['company', 'name']]
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    def clean(self):
        """Validate project data"""
        super().clean()
        
        # Validate dates
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({
                    'end_date': _('End date cannot be before start date.')
                })
        
        # Validate budget
        if self.total_budget and self.spent_budget:
            if self.spent_budget > self.total_budget:
                raise ValidationError({
                    'spent_budget': _('Spent budget cannot exceed total budget.')
                })
        
        # Validate leadership belongs to company
        if self.technical_lead and self.company:
            if not hasattr(self.technical_lead, 'profile') or \
               self.technical_lead.profile.company != self.company:
                raise ValidationError({
                    'technical_lead': _('Technical Lead must belong to the same company.')
                })
        
        if self.project_manager and self.company:
            if not hasattr(self.project_manager, 'profile') or \
               self.project_manager.profile.company != self.company:
                raise ValidationError({
                    'project_manager': _('Project Manager must belong to the same company.')
                })
    
    def get_progress_percentage(self):
        """Calculate project progress"""
        total_tasks = self.tasks.count()
        if total_tasks == 0:
            return 0
        completed_tasks = self.tasks.filter(status='completed').count()
        return round((completed_tasks / total_tasks) * 100, 2)
    
    def get_task_distribution(self):
        """Get task distribution by status"""
        return {
            'total': self.tasks.count(),
            'todo': self.tasks.filter(status='todo').count(),
            'in_progress': self.tasks.filter(status='in_progress').count(),
            'on_hold': self.tasks.filter(status='on_hold').count(),
            'completed': self.tasks.filter(status='completed').count(),
        }
    
    def get_total_hours(self):
        """Calculate total hours spent"""
        result = self.tasks.aggregate(total=Sum('actual_hours'))
        return result['total'] or Decimal('0')
    
    def get_budget_status(self):
        """Get budget status"""
        if not self.total_budget:
            return {
                'remaining': None,
                'percentage_used': None,
                'is_over_budget': False
            }
        
        remaining = self.total_budget - self.spent_budget
        percentage = (self.spent_budget / self.total_budget * 100) if self.total_budget > 0 else 0
        
        return {
            'remaining': remaining,
            'percentage_used': round(percentage, 2),
            'is_over_budget': self.spent_budget > self.total_budget
        }
    
    def get_overdue_tasks(self):
        """Get count of overdue tasks"""
        today = timezone.now().date()
        return self.tasks.filter(
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        ).count()
    
    def get_upcoming_tasks(self, days=7):
        """Get upcoming tasks within specified days"""
        today = timezone.now().date()
        future_date = today + timedelta(days=days)
        return self.tasks.filter(
            due_date__range=[today, future_date],
            status__in=['todo', 'in_progress']
        ).order_by('due_date')
    
    def get_auto_report_data(self):
        """Generate automatic report data (no model needed)"""
        task_dist = self.get_task_distribution()
        budget_status = self.get_budget_status()
        
        return {
            'project_name': self.name,
            'report_date': timezone.now().date(),
            'progress_percentage': self.get_progress_percentage(),
            'task_summary': task_dist,
            'total_hours': self.get_total_hours(),
            'budget_status': budget_status,
            'overdue_tasks': self.get_overdue_tasks(),
            'upcoming_tasks': self.get_upcoming_tasks().count(),
        }


# ==================== TASK MODEL ====================

class Task(OwnedModel, TimeStampedModel):
    """Task Management with Company Ownership"""
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
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name=_("Project")
    )
    
    # Assignment
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        verbose_name=_("Assigned By")
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='my_tasks',
        verbose_name=_("Assigned To")
    )
    
    # Basic Information
    title = models.CharField(_("Task Title"), max_length=255, db_index=True)
    description = models.TextField(_("Description"), blank=True)
    
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='todo',
        db_index=True
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    
    # Timeline & Hours
    due_date = models.DateField(_("Due Date"))
    estimated_hours = models.DecimalField(
        _("Estimated Hours"),
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    actual_hours = models.DecimalField(
        _("Actual Hours"),
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Blocking
    is_blocked = models.BooleanField(_("Is Blocked"), default=False)
    blocking_reason = models.TextField(_("Blocking Reason"), blank=True)
    
    # Completion
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        ordering = ['due_date', '-priority', '-created_at']
        indexes = [
            models.Index(fields=['company', 'status', 'due_date']),
            models.Index(fields=['project', 'assigned_to']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.assigned_to}"
    
    def clean(self):
        """Validate task data"""
        super().clean()
        
        # Ensure project belongs to same company
        if self.project and self.company:
            if self.project.company != self.company:
                raise ValidationError({
                    'project': _('Project must belong to the same company.')
                })
        
        # Validate assigned users belong to company
        if self.assigned_to and self.company:
            if not hasattr(self.assigned_to, 'profile') or \
               self.assigned_to.profile.company != self.company:
                raise ValidationError({
                    'assigned_to': _('Assigned user must belong to the same company.')
                })
        
        if self.assigned_by and self.company:
            if not hasattr(self.assigned_by, 'profile') or \
               self.assigned_by.profile.company != self.company:
                raise ValidationError({
                    'assigned_by': _('Assigning user must belong to the same company.')
                })
    
    def mark_completed(self):
        """Mark task as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_blocked(self, reason):
        """Mark task as blocked"""
        self.is_blocked = True
        self.blocking_reason = reason
        self.status = 'on_hold'
        self.save()
    
    def unblock(self):
        """Unblock task"""
        self.is_blocked = False
        self.blocking_reason = ''
        self.status = 'in_progress'
        self.save()
    
    def is_overdue(self):
        """Check if task is overdue"""
        if self.status == 'completed':
            return False
        return timezone.now().date() > self.due_date
    
    def get_days_until_due(self):
        """Get days until due date"""
        return (self.due_date - timezone.now().date()).days


# Auto-assign company from project
@receiver(pre_save, sender=Task)
def auto_assign_task_company(sender, instance, **kwargs):
    """Automatically assign company from project"""
    if instance.project and not instance.company_id:
        instance.company = instance.project.company
    if instance.project and not instance.owner_id:
        instance.owner = instance.project.owner


# ==================== TASK COMMENT MODEL ====================

class TaskComment(OwnedModel, TimeStampedModel):
    """Task Comments with Company Ownership"""
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_("Task")
    )
    commented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='task_comments',
        verbose_name=_("Commented By")
    )
    comment = models.TextField(_("Comment"))
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Task Comment")
        verbose_name_plural = _("Task Comments")
    
    def __str__(self):
        return f"Comment by {self.commented_by} on {self.task.title}"


# Auto-assign company from task
@receiver(pre_save, sender=TaskComment)
def auto_assign_comment_company(sender, instance, **kwargs):
    """Automatically assign company from task"""
    if instance.task and not instance.company_id:
        instance.company = instance.task.company
    if instance.task and not instance.owner_id:
        instance.owner = instance.task.owner