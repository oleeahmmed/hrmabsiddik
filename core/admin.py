from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Company

@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = ('company_code', 'name', 'city', 'country', 'is_active', 'created_at')
    list_filter = ('is_active', 'country', 'created_at')
    search_fields = ('company_code', 'name', 'city', 'email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company_code', 'name')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'state', 'zip_code', 'country')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'email', 'website')
        }),
        ('Business Information', {
            'fields': ('tax_id', 'currency')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )