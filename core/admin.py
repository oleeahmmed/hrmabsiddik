from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.urls import path
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from datetime import datetime, timedelta
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


# ==================== PROJECT DASHBOARD VIEW ====================

from django.views import View
from django.utils.decorators import method_decorator

class ProjectDashboardView(View):
    """Custom Project Dashboard"""
    
    def get(self, request, *args, **kwargs):
        """Handle GET requests for Project Dashboard"""
        
        # Get base admin context
        context = {**admin.site.each_context(request)}
        
        # Get user's company if not superuser
        user_company = None
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            user_company = request.user.profile.company
        
        # Build queryset based on user permissions
        if request.user.is_superuser:
            projects_qs = Project.objects.all()
            tasks_qs = Task.objects.all()
            companies_qs = Company.objects.all()
            users_qs = User.objects.all()
        else:
            # Filter by user's company and permissions
            if hasattr(request.user, 'profile') and request.user.profile.company:
                projects_qs = Project.objects.filter(
                    company=request.user.profile.company
                ).filter(
                    models.Q(owner=request.user) |
                    models.Q(technical_lead=request.user) |
                    models.Q(project_manager=request.user) |
                    models.Q(supervisor=request.user)
                ).distinct()
                
                tasks_qs = Task.objects.filter(
                    company=request.user.profile.company
                ).filter(
                    models.Q(project__owner=request.user) |
                    models.Q(project__technical_lead=request.user) |
                    models.Q(project__project_manager=request.user) |
                    models.Q(project__supervisor=request.user) |
                    models.Q(owner=request.user) |
                    models.Q(assigned_to=request.user)
                ).distinct()
                
                companies_qs = Company.objects.filter(id=request.user.profile.company.id)
                users_qs = User.objects.filter(profile__company=request.user.profile.company)
            else:
                projects_qs = Project.objects.none()
                tasks_qs = Task.objects.none()
                companies_qs = Company.objects.none()
                users_qs = User.objects.none()
        
        # Project Statistics
        total_projects = projects_qs.count()
        active_projects = projects_qs.filter(is_active=True).count()
        completed_projects = projects_qs.filter(status='completed').count()
        in_progress_projects = projects_qs.filter(status='in_progress').count()
        planning_projects = projects_qs.filter(status='planning').count()
        on_hold_projects = projects_qs.filter(status='on_hold').count()
        
        # Task Statistics
        total_tasks = tasks_qs.count()
        completed_tasks = tasks_qs.filter(status='completed').count()
        in_progress_tasks = tasks_qs.filter(status='in_progress').count()
        todo_tasks = tasks_qs.filter(status='todo').count()
        blocked_tasks = tasks_qs.filter(is_blocked=True).count()
        
        # Overdue tasks
        today = timezone.now().date()
        overdue_tasks = tasks_qs.filter(
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        ).count()
        
        # Recent Data
        recent_projects = projects_qs.select_related(
            'company', 'owner', 'technical_lead', 'project_manager'
        ).order_by('-created_at')[:10]
        
        recent_tasks = tasks_qs.select_related(
            'project', 'owner', 'assigned_to', 'assigned_by'
        ).order_by('-created_at')[:15]
        
        recent_comments = TaskComment.objects.filter(
            task__in=tasks_qs
        ).select_related(
            'task', 'commented_by', 'owner'
        ).order_by('-created_at')[:10]
        
        # Project Status Distribution
        project_status_data = {
            'planning': planning_projects,
            'in_progress': in_progress_projects,
            'completed': completed_projects,
            'on_hold': on_hold_projects,
        }
        
        # Task Status Distribution
        task_status_data = {
            'todo': todo_tasks,
            'in_progress': in_progress_tasks,
            'completed': completed_tasks,
            'blocked': blocked_tasks,
        }
        
        # Priority Distribution
        high_priority_projects = projects_qs.filter(priority='high').count()
        critical_priority_projects = projects_qs.filter(priority='critical').count()
        high_priority_tasks = tasks_qs.filter(priority='high').count()
        critical_priority_tasks = tasks_qs.filter(priority='critical').count()
        
        # Team Statistics
        total_team_members = users_qs.count()
        active_team_members = users_qs.filter(is_active=True).count()
        
        # Budget Statistics (if available)
        total_budget = projects_qs.aggregate(
            total=models.Sum('total_budget')
        )['total'] or 0
        
        spent_budget = projects_qs.aggregate(
            spent=models.Sum('spent_budget')
        )['spent'] or 0
        
        # Weekly Progress Data (last 7 days)
        weekly_progress = []
        for i in range(7):
            date = today - timedelta(days=6-i)
            day_completed_tasks = tasks_qs.filter(
                completed_at__date=date
            ).count()
            day_created_tasks = tasks_qs.filter(
                created_at__date=date
            ).count()
            weekly_progress.append({
                'date': date,
                'completed': day_completed_tasks,
                'created': day_created_tasks,
                'day_name': date.strftime('%a')
            })
        
        # Top Performers (users with most completed tasks)
        top_performers = tasks_qs.filter(
            status='completed',
            assigned_to__isnull=False
        ).values(
            'assigned_to__username',
            'assigned_to__first_name',
            'assigned_to__last_name'
        ).annotate(
            completed_count=models.Count('id')
        ).order_by('-completed_count')[:5]
        
        # Upcoming Deadlines (next 7 days)
        next_week = today + timedelta(days=7)
        upcoming_deadlines = tasks_qs.filter(
            due_date__gte=today,
            due_date__lte=next_week,
            status__in=['todo', 'in_progress']
        ).select_related('project', 'assigned_to').order_by('due_date')[:10]
        
        # Project Progress Summary
        project_progress_summary = []
        for project in recent_projects[:5]:
            progress_data = {
                'project': project,
                'progress_percentage': project.get_progress_percentage(),
                'total_tasks': project.tasks.count(),
                'completed_tasks': project.tasks.filter(status='completed').count(),
                'overdue_tasks': project.get_overdue_tasks(),
                'budget_status': project.get_budget_status(),
            }
            project_progress_summary.append(progress_data)
        
        # Add all data to context
        context.update({
            'title': _('Project Management Dashboard'),
            'subtitle': _('Comprehensive overview of project operations'),
            'opts': Project._meta,
            
            # Project Stats
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'in_progress_projects': in_progress_projects,
            'planning_projects': planning_projects,
            'on_hold_projects': on_hold_projects,
            
            # Task Stats
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'todo_tasks': todo_tasks,
            'blocked_tasks': blocked_tasks,
            'overdue_tasks': overdue_tasks,
            
            # Priority Stats
            'high_priority_projects': high_priority_projects,
            'critical_priority_projects': critical_priority_projects,
            'high_priority_tasks': high_priority_tasks,
            'critical_priority_tasks': critical_priority_tasks,
            
            # Team Stats
            'total_team_members': total_team_members,
            'active_team_members': active_team_members,
            
            # Budget Stats
            'total_budget': total_budget,
            'spent_budget': spent_budget,
            'remaining_budget': total_budget - spent_budget,
            
            # Recent Data
            'recent_projects': recent_projects,
            'recent_tasks': recent_tasks,
            'recent_comments': recent_comments,
            'upcoming_deadlines': upcoming_deadlines,
            'project_progress_summary': project_progress_summary,
            'top_performers': top_performers,
            'weekly_progress': weekly_progress,
            
            # Chart Data
            'project_status_data': project_status_data,
            'task_status_data': task_status_data,
            
            # URLs
            'projects_url': 'admin:core_project_changelist',
            'tasks_url': 'admin:core_task_changelist',
            'comments_url': 'admin:core_taskcomment_changelist',
            'companies_url': 'admin:core_company_changelist',
            'users_url': 'admin:core_userprofile_changelist',
            
            'today': today,
            'user_company': user_company,
        })
        
        return render(request, 'admin/core/project_dashboard.html', context)


# Add custom URLs for Project Dashboard
def get_project_admin_urls():
    """Get custom URLs for Project admin"""
    from django.urls import path
    return [
        path('project-dashboard/', 
             admin.site.admin_view(ProjectDashboardView.as_view()), 
             name='core_project_dashboard'),
    ]

# Get the original admin URLs and add our custom one
original_get_urls = admin.site.get_urls

def custom_get_urls():
    custom_urls = get_project_admin_urls()
    return custom_urls + original_get_urls()

admin.site.get_urls = custom_get_urls

from django.db import models
from django.contrib.auth.models import User

# ==================== TASK INLINE ====================

class TaskInline(TabularInline):
    model = Task
    extra = 1
    fields = ['title', 'assigned_to', 'status', 'priority', 'due_date', 'is_blocked']
    readonly_fields = ['created_at']
    show_change_link = True
    
    def get_queryset(self, request):
        """Filter tasks in inline based on user permissions"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        # Regular users can only see tasks they have permission for
        if hasattr(request.user, 'profile') and request.user.profile.company:
            return qs.filter(
                models.Q(project__owner=request.user) |
                models.Q(project__technical_lead=request.user) |
                models.Q(project__project_manager=request.user) |
                models.Q(project__supervisor=request.user) |
                models.Q(owner=request.user) |
                models.Q(assigned_to=request.user)
            ).distinct()
        return qs.none()
    
    def has_add_permission(self, request, obj):
        """Allow adding tasks in inline only if user has permission"""
        if not obj:
            return False
            
        if request.user.is_superuser:
            return True
            
        # Check if user is linked to this project
        return (
            obj.owner == request.user or
            obj.technical_lead == request.user or
            obj.project_manager == request.user or
            obj.supervisor == request.user
        )
    
    def has_change_permission(self, request, obj=None):
        """Allow changing tasks in inline based on permissions"""
        if not obj:
            return False
            
        if request.user.is_superuser:
            return True
            
        # Check if user has permission to edit this task
        if obj:
            return (
                obj.project.owner == request.user or
                obj.owner == request.user or
                obj.assigned_to == request.user or
                obj.project.technical_lead == request.user or
                obj.project.project_manager == request.user or
                obj.project.supervisor == request.user
            )
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deleting tasks in inline only for project/task owners"""
        if not obj:
            return False
            
        if request.user.is_superuser:
            return True
            
        # Only project owner or task owner can delete
        if obj:
            return (
                obj.project.owner == request.user or
                obj.owner == request.user
            )
        return False

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
        'company', 'owner', 'created_at', 'updated_at', 'progress_percentage', 
        'task_distribution', 'total_hours', 'budget_status', 
        'overdue_tasks_count', 'auto_report_data'
    ]
    list_select_related = ['company', 'owner', 'technical_lead', 'project_manager']
    autocomplete_fields = ['technical_lead', 'project_manager', 'supervisor']
    inlines = [TaskInline]
    
    fieldsets = (
        (_('📋 Basic Information'), {
            'fields': (
                'name', 'description', 
                'technical_lead', 'project_manager', 'supervisor',
                'status', 'priority', 'is_active'
            ),
            'classes': ('tab',),
        }),
        (_('📅 Timeline & Budget'), {
            'fields': (
                'start_date', 'end_date',
                'total_budget', 'spent_budget'
            ),
            'classes': ('tab',),
        }),
        (_('📊 Analytics & Metadata'), {
            'fields': (
                'progress_percentage', 'task_distribution', 
                'total_hours', 'budget_status', 'overdue_tasks_count',
                'auto_report_data', 'created_at', 'updated_at'
            ),
            'classes': ('tab',),
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        """Make company and owner readonly for existing objects"""
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing object
            if 'company' not in readonly_fields:
                readonly_fields.append('company')
            if 'owner' not in readonly_fields:
                readonly_fields.append('owner')
        return readonly_fields
    
    def has_module_permission(self, request):
        """Allow access to project module"""
        return True
    
    def has_view_permission(self, request, obj=None):
        """Allow viewing projects"""
        if request.user.is_superuser:
            return True
            
        if hasattr(request.user, 'profile') and request.user.profile.company:
            return True
        return False
    
    def has_add_permission(self, request):
        """Allow adding projects"""
        if request.user.is_superuser:
            return True
            
        # Regular users can add projects if they have a company profile
        return hasattr(request.user, 'profile') and request.user.profile.company
    
    def has_change_permission(self, request, obj=None):
        """Allow editing projects"""
        if request.user.is_superuser:
            return True
            
        if obj is None:
            return True
            
        # Users can edit projects they own or are linked to
        return (
            obj.owner == request.user or
            obj.technical_lead == request.user or
            obj.project_manager == request.user or
            obj.supervisor == request.user
        )
    
    def has_delete_permission(self, request, obj=None):
        """Allow deleting projects only for owners"""
        if request.user.is_superuser:
            return True
            
        if obj is None:
            return True
            
        # Only project owner can delete
        return obj.owner == request.user
    
    def save_model(self, request, obj, form, change):
        """Auto-set company and owner from user's profile when creating"""
        if not change:  # Only for new objects
            if hasattr(request.user, 'profile'):
                obj.company = request.user.profile.company
                obj.owner = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Filter projects by user's permissions"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs.select_related('company', 'owner', 'technical_lead', 'project_manager')
        
        # Filter by user's company and permissions
        if hasattr(request.user, 'profile') and request.user.profile.company:
            return qs.filter(
                company=request.user.profile.company
            ).filter(
                models.Q(owner=request.user) |
                models.Q(technical_lead=request.user) |
                models.Q(project_manager=request.user) |
                models.Q(supervisor=request.user)
            ).distinct().select_related('company', 'owner', 'technical_lead', 'project_manager')
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices based on user's company"""
        if db_field.name in ['technical_lead', 'project_manager', 'supervisor']:
            # Only show users from the same company
            if hasattr(request.user, 'profile') and request.user.profile.company:
                kwargs["queryset"] = User.objects.filter(
                    profile__company=request.user.profile.company
                ).select_related('profile')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
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
    list_filter = ['company', 'project', 'status', 'priority', 'is_blocked']
    search_fields = ['title', 'project__name', 'assigned_to__username']
    readonly_fields = ['company', 'owner', 'created_at', 'updated_at', 'is_overdue_safe']
    autocomplete_fields = ['project', 'assigned_to', 'assigned_by']
    inlines = [TaskCommentInline]

    fieldsets = (
        (_('Required'), {
            'fields': ['title', 'project', 'assigned_to', 'status', 'due_date'],
            'classes': ('tab',),
        }),
        (_('Optional'), {
            'fields': ['description', 'assigned_by', 'estimated_hours', 'actual_hours', 'is_blocked', 'blocking_reason'],
            'classes': ('tab',),
        }),
        (_('Metadata'), {
            'fields': ['company', 'owner', 'is_overdue_safe', 'created_at', 'updated_at'],
            'classes': ('tab',),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Set readonly fields based on permissions"""
        readonly_fields = list(super().get_readonly_fields(request, obj))
        
        if obj:  # Editing existing object
            # Make company and owner readonly for existing tasks
            if 'company' not in readonly_fields:
                readonly_fields.append('company')
            if 'owner' not in readonly_fields:
                readonly_fields.append('owner')
            
            # Check if user has permission to edit/delete
            if not self.has_change_permission(request, obj) and not request.user.is_superuser:
                # Make all fields readonly if no permission
                readonly_fields.extend([
                    'title', 'description', 'project', 'assigned_to', 'status',
                    'priority', 'due_date', 'estimated_hours', 'actual_hours',
                    'is_blocked', 'blocking_reason', 'assigned_by'
                ])
        
        return readonly_fields

    def has_add_permission(self, request):
        """Allow users to add tasks if they are linked to any project"""
        if request.user.is_superuser:
            return True
        
        # Check if user is linked to any project (technical_lead, project_manager, supervisor, or owner)
        if hasattr(request.user, 'profile') and request.user.profile.company:
            user_projects = Project.objects.filter(
                company=request.user.profile.company
            ).filter(
                models.Q(technical_lead=request.user) |
                models.Q(project_manager=request.user) |
                models.Q(supervisor=request.user) |
                models.Q(owner=request.user)
            )
            return user_projects.exists()
        return False

    def has_change_permission(self, request, obj=None):
        """Allow edit only for project owner or task owner"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return True
        
        # Check if user is project owner or task owner
        is_project_owner = obj.project.owner == request.user
        is_task_owner = obj.owner == request.user
        is_assigned_to = obj.assigned_to == request.user
        
        # Allow project leadership team to edit tasks in their projects
        is_project_leadership = (
            obj.project.technical_lead == request.user or
            obj.project.project_manager == request.user or
            obj.project.supervisor == request.user
        )
        
        return is_project_owner or is_task_owner or is_assigned_to or is_project_leadership

    def has_delete_permission(self, request, obj=None):
        """Allow delete only for project owner or task owner"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return True
        
        # Only project owner or task owner can delete
        is_project_owner = obj.project.owner == request.user
        is_task_owner = obj.owner == request.user
        
        return is_project_owner or is_task_owner

    def save_model(self, request, obj, form, change):
        """Auto-set company, owner, and assigned_by when creating"""
        if not change:  # Only for new objects
            # Auto-set company from project
            if obj.project and not obj.company:
                obj.company = obj.project.company
            
            # Auto-set owner from current user
            if not obj.owner:
                obj.owner = request.user
            
            # Auto-set assigned_by from current user if not set
            if not obj.assigned_by:
                obj.assigned_by = request.user
        
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        """Filter tasks based on user's permissions"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.select_related('project', 'company', 'owner', 'assigned_to', 'assigned_by')
        
        # Regular users can only see tasks from their company
        if hasattr(request.user, 'profile') and request.user.profile.company:
            company_tasks = qs.filter(company=request.user.profile.company)
            
            # Users can see tasks where they are:
            # - Project owner/leadership, OR
            # - Task owner, OR  
            # - Assigned to the task
            user_visible_tasks = company_tasks.filter(
                models.Q(project__owner=request.user) |
                models.Q(project__technical_lead=request.user) |
                models.Q(project__project_manager=request.user) |
                models.Q(project__supervisor=request.user) |
                models.Q(owner=request.user) |
                models.Q(assigned_to=request.user)
            ).distinct()
            
            return user_visible_tasks.select_related('project', 'company', 'owner', 'assigned_to', 'assigned_by')
        
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices based on user's permissions"""
        if db_field.name == 'project':
            # Only show projects where user is linked
            if hasattr(request.user, 'profile') and request.user.profile.company:
                kwargs["queryset"] = Project.objects.filter(
                    company=request.user.profile.company
                ).filter(
                    models.Q(technical_lead=request.user) |
                    models.Q(project_manager=request.user) |
                    models.Q(supervisor=request.user) |
                    models.Q(owner=request.user)
                )
        
        elif db_field.name in ['assigned_to', 'assigned_by']:
            # Only show users from the same company
            if hasattr(request.user, 'profile') and request.user.profile.company:
                kwargs["queryset"] = User.objects.filter(
                    profile__company=request.user.profile.company
                ).select_related('profile')
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def is_overdue_safe(self, obj):
        try:
            return obj.is_overdue()
        except (TypeError, AttributeError):
            return False
    is_overdue_safe.boolean = True
    is_overdue_safe.short_description = _('Is Overdue')



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
