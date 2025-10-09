from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Company, Project, Task


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
        ('Logo & Status', {
            'fields': ('logo', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ('name', 'company', 'start_date', 'end_date', 'is_active', 'created_at')
    list_filter = ('company', 'is_active', 'start_date')
    search_fields = ('name', 'description', 'company__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Project Details', {
            'fields': ('name', 'description', 'company')
        }),
        ('Duration', {
            'fields': ('start_date', 'end_date')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ('title', 'employee', 'project', 'company', 'status', 'hours_spent', 'date')
    list_filter = ('status', 'company', 'project', 'date')
    search_fields = ('title', 'description', 'employee__name', 'project__name')
    readonly_fields = ('created_at', 'updated_at', 'date')
    
    fieldsets = (
        ('Task Information', {
            'fields': ('title', 'description', 'status')
        }),
        ('Relations', {
            'fields': ('company', 'project', 'employee')
        }),
        ('Work Details', {
            'fields': ('hours_spent', 'date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Ensure tasks are ordered by most recent first."""
        qs = super().get_queryset(request)
        return qs.select_related('company', 'project', 'employee').order_by('-date', '-created_at')
