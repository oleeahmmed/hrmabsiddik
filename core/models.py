from django.db import models
from django.utils.translation import gettext_lazy as _


    #Core Apps
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
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        ordering = ['name']

    def __str__(self):
        return self.name    