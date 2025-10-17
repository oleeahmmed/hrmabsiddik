from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.urls import path
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from django.http import HttpResponseRedirect
from .models import (
    Company, UserProfile, Project, Task, TaskComment
)


# ==================== COMPANY ADMIN ====================

class CompanySubsidiaryInline(TabularInline):
    model = Company
    fk_name = 'parent'
    extra = 0
    fields = ['company_code', 'name', 'city', 'country', 'is_active']
    readonly_fields = ['company_code', 'name', 'city', 'country']
    show_change_link = True
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = [
        'company_code', 'name', 'parent', 'city', 'country', 
        'level', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'country', 'level', 'created_at']
    search_fields = ['company_code', 'name', 'city', 'country']
    readonly_fields = ['level', 'created_at', 'updated_at']
    list_select_related = ['parent']
    inlines = [CompanySubsidiaryInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'company_code', 'name', 'parent', 'is_active'
            )
        }),
        (_('Address Information'), {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'state', 'zip_code', 'country'
            )
        }),
        (_('Contact Information'), {
            'fields': (
                'phone_number', 'email', 'website'
            )
        }),
        (_('Business Information'), {
            'fields': (
                'tax_id', 'registration_number', 'currency'
            )
        }),
        (_('Settings'), {
            'fields': (
                'logo', 'location_restricted'
            )
        }),
        (_('Metadata'), {
            'fields': (
                'level', 'created_at', 'updated_at'
            )
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent')


# ==================== USER PROFILE ADMIN ====================

@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = [
        'user', 'company', 'designation', 'department', 
        'employee_id', 'is_active', 'created_at'
    ]
    list_filter = ['company', 'is_active', 'gender', 'department', 'created_at']
    search_fields = [
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'employee_id', 'designation', 'department'
    ]
    readonly_fields = ['created_at', 'updated_at']
    list_select_related = ['user', 'company']
    autocomplete_fields = ['user', 'company']
    
    fieldsets = (
        (_('Core Information'), {
            'fields': (
                'user', 'company', 'is_active'
            )
        }),
        (_('Personal Information'), {
            'fields': (
                'phone_number', 'date_of_birth', 'gender', 'profile_picture'
            )
        }),
        (_('Address Information'), {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'state', 'zip_code', 'country'
            )
        }),
        (_('Professional Information'), {
            'fields': (
                'designation', 'department', 'employee_id', 'joining_date'
            )
        }),
        (_('Metadata'), {
            'fields': (
                'created_at', 'updated_at'
            )
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'company')



# ==================== TASK INLINE ====================

class TaskInline(TabularInline):
    model = Task
    extra = 1
    fields = ['title', 'assigned_to', 'status', 'priority', 'due_date', 'is_blocked']
    readonly_fields = ['created_at']
    show_change_link = True


# ==================== PROJECT ADMIN ====================

@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = [
        'name', 'company', 'status', 'priority', 'start_date', 
        'end_date', 'progress_percentage', 'is_active'
    ]
    list_filter = ['company', 'status', 'priority', 'is_active', 'start_date']
    search_fields = ['name', 'description', 'company__name']
    readonly_fields = [
        'created_at', 'updated_at', 'progress_percentage', 
        'task_distribution', 'total_hours', 'budget_status', 
        'overdue_tasks_count', 'auto_report_data'
    ]
    list_select_related = ['company', 'owner', 'technical_lead', 'project_manager']
    autocomplete_fields = ['company', 'owner', 'technical_lead', 'project_manager']
    inlines = [TaskInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'name', 'description', 'company', 'owner'
            )
        }),
        (_('Leadership'), {
            'fields': (
                'technical_lead', 'project_manager'
            )
        }),
        (_('Status & Priority'), {
            'fields': (
                'status', 'priority', 'is_active'
            )
        }),
        (_('Timeline'), {
            'fields': (
                'start_date', 'end_date'
            )
        }),
        (_('Budget'), {
            'fields': (
                'total_budget', 'spent_budget'
            )
        }),
        (_('Project Analytics'), {
            'fields': (
                'progress_percentage', 'task_distribution', 
                'total_hours', 'budget_status', 'overdue_tasks_count',
                'auto_report_data'
            )
        }),
        (_('Metadata'), {
            'fields': (
                'created_at', 'updated_at'
            )
        }),
    )
    
    def progress_percentage(self, obj):
        return f"{obj.get_progress_percentage()}%"
    progress_percentage.short_description = _('Progress')
    
    def task_distribution(self, obj):
        dist = obj.get_task_distribution()
        return f"Total: {dist['total']}, Completed: {dist['completed']}, In Progress: {dist['in_progress']}"
    task_distribution.short_description = _('Task Distribution')
    
    def total_hours(self, obj):
        return f"{obj.get_total_hours()} hours"
    total_hours.short_description = _('Total Hours')
    
    def budget_status(self, obj):
        status = obj.get_budget_status()
        if status['remaining'] is None:
            return "No budget set"
        return f"Remaining: {status['remaining']} ({status['percentage_used']}% used)"
    budget_status.short_description = _('Budget Status')
    
    def overdue_tasks_count(self, obj):
        return obj.get_overdue_tasks()
    overdue_tasks_count.short_description = _('Overdue Tasks')
    
    def auto_report_data(self, obj):
        report_data = obj.get_auto_report_data()
        return f"""
        Progress: {report_data['progress_percentage']}% | 
        Tasks: {report_data['task_summary']['completed']}/{report_data['task_summary']['total']} Completed |
        Hours: {report_data['total_hours']} | 
        Overdue: {report_data['overdue_tasks']}
        """
    auto_report_data.short_description = _('Auto Report Summary')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'owner', 'technical_lead', 'project_manager'
        )


# ==================== TASK COMMENT INLINE ====================

class TaskCommentInline(TabularInline):
    model = TaskComment
    extra = 1
    fields = ['commented_by', 'comment', 'created_at']
    readonly_fields = ['created_at']


# ==================== TASK ADMIN ====================

@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = [
        'title', 'project', 'assigned_to', 'status', 'priority', 
        'due_date', 'is_blocked', 'is_overdue', 'created_at'
    ]
    list_filter = [
        'company', 'project', 'status', 'priority', 'is_blocked', 
        'due_date', 'created_at'
    ]
    search_fields = [
        'title', 'description', 'project__name', 
        'assigned_to__username', 'assigned_to__email'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'completed_at', 
        'is_overdue', 'days_until_due'
    ]
    list_select_related = [
        'company', 'project', 'owner', 'assigned_by', 'assigned_to'
    ]
    autocomplete_fields = [
        'company', 'project', 'owner', 'assigned_by', 'assigned_to'
    ]
    inlines = [TaskCommentInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'title', 'description', 'project', 'company', 'owner'
            )
        }),
        (_('Assignment'), {
            'fields': (
                'assigned_by', 'assigned_to'
            )
        }),
        (_('Status & Priority'), {
            'fields': (
                'status', 'priority', 'is_blocked', 'blocking_reason'
            )
        }),
        (_('Timeline & Hours'), {
            'fields': (
                'due_date', 'estimated_hours', 'actual_hours'
            )
        }),
        (_('Completion'), {
            'fields': (
                'completed_at',
            )
        }),
        (_('Task Status'), {
            'fields': (
                'is_overdue', 'days_until_due'
            )
        }),
        (_('Metadata'), {
            'fields': (
                'created_at', 'updated_at'
            )
        }),
    )
    
    def is_overdue(self, obj):
        return obj.is_overdue()
    is_overdue.boolean = True
    is_overdue.short_description = _('Is Overdue')
    
    def days_until_due(self, obj):
        return obj.get_days_until_due()
    days_until_due.short_description = _('Days Until Due')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'project', 'owner', 'assigned_by', 'assigned_to'
        )


# ==================== TASK COMMENT ADMIN ====================

@admin.register(TaskComment)
class TaskCommentAdmin(ModelAdmin):
    list_display = ['task', 'commented_by', 'comment_preview', 'created_at']
    list_filter = ['company', 'created_at']
    search_fields = [
        'comment', 'task__title', 'commented_by__username', 'commented_by__email'
    ]
    readonly_fields = ['created_at', 'updated_at']
    list_select_related = ['company', 'task', 'owner', 'commented_by']
    autocomplete_fields = ['company', 'task', 'owner', 'commented_by']
    
    def comment_preview(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_preview.short_description = _('Comment')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'company', 'task', 'owner', 'commented_by'
        )


# ==================== PROJECT REPORT ADMIN ====================

class ProjectReportAdmin(ModelAdmin):
    """প্রজেক্ট রিপোর্ট এডমিন ক্লাস"""
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('reports/', self.admin_site.admin_view(self.report_dashboard), name='project_reports_dashboard'),
        ]
        return custom_urls + urls
    
    def report_dashboard(self, request):
        """রিপোর্ট ড্যাশবোর্ড রিডাইরেক্ট"""
        from django.urls import reverse
        return HttpResponseRedirect(reverse('core:project_report_dashboard'))
    
    @display(description=_('📊 Project Reports'))
    def project_reports_link(self, obj=None):
        return ""


# Admin site-এ রিপোর্ট লিঙ্ক যোগ করুন
def add_project_reports_link(request):
    """এডমিন সাইটে রিপোর্ট মেনু যোগ করুন"""
    return {
        'project_reports_url': '/admin/project-reports/dashboard/'
    }
