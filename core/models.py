from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


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


class Project(models.Model):
    """Represents a project under a company."""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        verbose_name=_("Company"),
        null=True,
        blank=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_projects",
        verbose_name=_("Owner"),
    )
    name = models.CharField(_("Project Name"), max_length=200)
    description = models.TextField(_("Description"), blank=True, null=True)
    start_date = models.DateField(_("Start Date"), blank=True, null=True)
    end_date = models.DateField(_("End Date"), blank=True, null=True)
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ['-created_at']

    def __str__(self):
        company_name = self.company.name if self.company else "No Company"
        return f"{self.name} ({company_name})"

    def save(self, *args, **kwargs):
        """Automatically set company if not provided."""
        if not self.company_id:
            active_company = Company.get_active_company()
            if active_company:
                self.company = active_company
        super().save(*args, **kwargs)


class Task(models.Model):
    """Represents a daily task done by an employee under a project."""
    STATUS_CHOICES = [
        ('todo', _('To Do')),
        ('in_progress', _('In Progress')),
        ('done', _('Done')),
    ]

    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        verbose_name=_("Company"),
        null=True,
        blank=True
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, verbose_name=_("Project"))
    employee = models.ForeignKey(
        'hr_payroll.Employee', 
        on_delete=models.SET_NULL, 
        verbose_name=_("Employee"), 
        null=True, 
        blank=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_tasks",
        verbose_name=_("Owner"),
    )

    title = models.CharField(_("Task Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True, null=True)
    date = models.DateField(_("Date of Task"), default=timezone.now)
    hours_spent = models.DecimalField(_("Hours Spent"), max_digits=5, decimal_places=2, default=0.00)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='todo')

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        ordering = ['-date', '-created_at']

    def __str__(self):
        employee_name = self.employee.name if self.employee else "Unassigned"
        return f"{employee_name} - {self.project.name} ({self.title})"

    def save(self, *args, **kwargs):
        """Automatically set company if not provided."""
        if not self.company_id:
            # Try to get company from project first
            if self.project and self.project.company:
                self.company = self.project.company
            else:
                # Fallback to active company
                active_company = Company.get_active_company()
                if active_company:
                    self.company = active_company
        super().save(*args, **kwargs)