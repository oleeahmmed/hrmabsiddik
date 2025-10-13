from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.http import JsonResponse
from django.urls import path
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.filters.admin import RangeDateFilter

from .models import (
    UserProfile, Company, ProjectRole, Project, Task,
    TaskChecklist, TaskComment, ProjectMember, ProjectReport, DailyTimeLog
)


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = [
        'get_user_info',
        'company', 
        'employee_id', 
        'designation',
        'department',
        'is_active_toggle',
        'created_at'
    ]
    list_filter = [
        'is_active', 
        'gender', 
        'company',
        'designation',
        'department'
    ]
    search_fields = [
        'user__username', 
        'user__email', 
        'user__first_name', 
        'user__last_name', 
        'employee_id', 
        'phone_number',
        'designation',
        'department'
    ]
    readonly_fields = [
        'created_at', 
        'updated_at', 
        'age_display', 
        'full_address_display'
    ]
    list_per_page = 25
    date_hierarchy = 'created_at'
    
    # Tabbed fieldsets
    def get_fieldsets(self, request, obj=None):
        return [
            (_("User & Company"), {
                'fields': ('user', 'company', 'is_active'),
                'classes': ['tab'],
            }),
            (_("Personal Information"), {
                'fields': (
                    'phone_number', 
                    'date_of_birth', 
                    'age_display', 
                    'gender', 
                    'profile_picture', 
                    'bio'
                ),
                'classes': ['tab'],
            }),
            (_("Address Information"), {
                'fields': (
                    'address_line1', 
                    'address_line2', 
                    'city', 
                    'state', 
                    'zip_code', 
                    'country', 
                    'full_address_display'
                ),
                'classes': ['tab'],
            }),
            (_("Professional Information"), {
                'fields': (
                    'designation', 
                    'department', 
                    'employee_id', 
                    'joining_date'
                ),
                'classes': ['tab'],
            }),
            (_("Emergency Contact"), {
                'fields': (
                    'emergency_contact_name', 
                    'emergency_contact_phone', 
                    'emergency_contact_relation'
                ),
                'classes': ['tab'],
            }),
            (_("System Information"), {
                'fields': ('created_at', 'updated_at'),
                'classes': ['tab'],
            }),
        ]

    @display(description=_("User"))
    def get_user_info(self, obj):
        """Display user information with avatar"""
        full_name = obj.user.get_full_name() or obj.user.username
        email = obj.user.email
        
        if obj.profile_picture:
            avatar = f'<img src="{obj.profile_picture.url}" class="w-10 h-10 rounded-full mr-3" />'
        else:
            initial = full_name[0].upper()
            avatar = f'''
                <div class="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center text-white font-bold mr-3">
                    {initial}
                </div>
            '''
        
        return format_html(
            '''
            <div class="flex items-center">
                {}
                <div>
                    <div class="font-medium text-gray-900">{}</div>
                    <div class="text-sm text-gray-500">{}</div>
                </div>
            </div>
            ''',
            format_html(avatar),
            full_name,
            email
        )

    @display(description=_("Status"))
    def is_active_toggle(self, obj):
        """Display toggle button for active/inactive status"""
        if obj.is_active:
            return format_html(
                '''
                <button type="button" 
                        onclick="toggleUserStatus({pk})"
                        class="inline-flex items-center px-3 py-1.5 border border-transparent text-xs 
                               font-medium rounded-md text-white bg-green-600 hover:bg-green-700 
                               focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 
                               transition-colors duration-200">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Active
                </button>
                <script>
                if (typeof toggleUserStatus === 'undefined') {{
                    function toggleUserStatus(pk) {{
                        const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
                        
                        fetch('/admin/core/userprofile/' + pk + '/toggle-status/', {{
                            method: 'POST',
                            headers: {{
                                'X-CSRFToken': csrftoken,
                                'Content-Type': 'application/json',
                            }},
                        }})
                        .then(response => response.json())
                        .then(data => {{
                            if (data.success) {{
                                location.reload();
                            }} else {{
                                alert('Error: ' + (data.error || 'Unknown error'));
                            }}
                        }})
                        .catch(error => {{
                            console.error('Error:', error);
                            alert('Failed to toggle status');
                        }});
                    }}
                }}
                </script>
                ''',
                pk=obj.pk
            )
        else:
            return format_html(
                '''
                <button type="button" 
                        onclick="toggleUserStatus({pk})"
                        class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs 
                               font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 
                               focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 
                               transition-colors duration-200">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                    Inactive
                </button>
                <script>
                if (typeof toggleUserStatus === 'undefined') {{
                    function toggleUserStatus(pk) {{
                        const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
                        
                        fetch('/admin/core/userprofile/' + pk + '/toggle-status/', {{
                            method: 'POST',
                            headers: {{
                                'X-CSRFToken': csrftoken,
                                'Content-Type': 'application/json',
                            }},
                        }})
                        .then(response => response.json())
                        .then(data => {{
                            if (data.success) {{
                                location.reload();
                            }} else {{
                                alert('Error: ' + (data.error || 'Unknown error'));
                            }}
                        }})
                        .catch(error => {{
                            console.error('Error:', error);
                            alert('Failed to toggle status');
                        }});
                    }}
                }}
                </script>
                ''',
                pk=obj.pk
            )

    @display(description=_("Age"))
    def age_display(self, obj):
        """Display calculated age"""
        age = obj.get_age()
        if age:
            return format_html('<span class="font-medium">{} years</span>', age)
        return format_html('<span class="text-gray-400">N/A</span>')

    @display(description=_("Full Address"))
    def full_address_display(self, obj):
        """Display formatted full address"""
        address = obj.get_full_address()
        if address:
            return format_html('<div class="text-sm">{}</div>', address)
        return format_html('<span class="text-gray-400">No address provided</span>')

    def get_urls(self):
        """Add custom URL for toggle status"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pk>/toggle-status/',
                self.admin_site.admin_view(self.toggle_status_view),
                name='core_userprofile_toggle_status'
            ),
        ]
        return custom_urls + urls

    def toggle_status_view(self, request, pk):
        """Handle toggle status AJAX request"""
        if request.method != 'POST':
            return JsonResponse({
                'success': False, 
                'error': 'Method not allowed'
            }, status=405)
        
        try:
            user_profile = UserProfile.objects.get(pk=pk)
            user_profile.is_active = not user_profile.is_active
            user_profile.save()
            
            return JsonResponse({
                'success': True,
                'is_active': user_profile.is_active,
                'message': f'Profile status updated to {"Active" if user_profile.is_active else "Inactive"}'
            })
        except UserProfile.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'User profile not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    # Keep bulk actions only
    @action(description=_("✓ Activate selected profiles"))
    def activate_profiles(self, request, queryset):
        """Bulk activate user profiles"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            _(f"{updated} profile(s) activated successfully.")
        )

    @action(description=_("✗ Deactivate selected profiles"))
    def deactivate_profiles(self, request, queryset):
        """Bulk deactivate user profiles"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _(f"{updated} profile(s) deactivated successfully.")
        )

    @action(description=_("📧 Send welcome email to selected"))
    def send_welcome_email(self, request, queryset):
        """Send welcome email to selected profiles"""
        count = 0
        for profile in queryset:
            if profile.user.email:
                # Add your email sending logic here
                count += 1
        
        self.message_user(
            request,
            _(f"Welcome email sent to {count} user(s).")
        )

    @action(description=_("📊 Export selected profiles"))
    def export_profiles(self, request, queryset):
        """Export selected profiles to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="user_profiles.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Username', 'Email', 'Employee ID', 'Designation', 
            'Department', 'Phone', 'Company', 'Status'
        ])
        
        for profile in queryset:
            writer.writerow([
                profile.user.username,
                profile.user.email,
                profile.employee_id or '',
                profile.designation or '',
                profile.department or '',
                profile.phone_number or '',
                profile.company.name if profile.company else '',
                'Active' if profile.is_active else 'Inactive'
            ])
        
        return response

    actions = [
        'activate_profiles', 
        'deactivate_profiles',
        'send_welcome_email',
        'export_profiles'
    ]
@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = ['name', 'company_code', 'city', 'country', 'location_restricted', 'is_active']
    list_filter = ['is_active', 'location_restricted', 'country', ('created_at', RangeDateFilter)]
    search_fields = ['name', 'company_code', 'email', 'tax_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_("Basic Information"), {
            'fields': ('company_code', 'name', 'logo', 'is_active')
        }),
        (_("Contact Information"), {
            'fields': ('phone_number', 'email', 'website')
        }),
        (_("Address"), {
            'fields': ('address_line1', 'address_line2', 'city', 'state', 'zip_code', 'country')
        }),
        (_("Business Details"), {
            'fields': ('tax_id', 'currency', 'location_restricted')
        }),
        (_("System Information"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ProjectRole)
class ProjectRoleAdmin(ModelAdmin):
    list_display = ['get_role_display', 'hierarchy_level', 'role']
    list_filter = ['role', 'hierarchy_level']
    search_fields = ['role', 'description']
    ordering = ['hierarchy_level']


class TaskInline(TabularInline):
    model = Task
    extra = 0
    fields = ['title', 'assigned_to', 'status', 'priority', 'due_date', 'estimated_hours']
    show_change_link = True


class ProjectMemberInline(TabularInline):
    model = ProjectMember
    extra = 0
    fields = ['employee', 'role', 'reporting_to', 'joined_date']
    show_change_link = True


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ['name', 'company', 'status_badge', 'priority_badge', 'progress_display', 
                    'start_date', 'end_date', 'technical_lead', 'project_manager']
    list_filter = ['status', 'priority', 'company', 'is_active', ('start_date', RangeDateFilter)]
    search_fields = ['name', 'description', 'company__name']
    readonly_fields = ['created_at', 'updated_at', 'progress_display', 'task_stats', 'budget_info']
    inlines = [ProjectMemberInline, TaskInline]
    
    fieldsets = (
        (_("Project Information"), {
            'fields': ('company', 'name', 'description', 'status', 'priority', 'is_active')
        }),
        (_("Team"), {
            'fields': ('technical_lead', 'project_manager')
        }),
        (_("Timeline"), {
            'fields': ('start_date', 'end_date')
        }),
        (_("Budget"), {
            'fields': ('total_budget', 'spent_budget', 'budget_info')
        }),
        (_("Statistics"), {
            'fields': ('progress_display', 'task_stats'),
            'classes': ('collapse',)
        }),
        (_("System Information"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @display(description=_("Status"), label=True)
    def status_badge(self, obj):
        colors = {
            'planning': 'info',
            'in_progress': 'warning',
            'on_hold': 'danger',
            'completed': 'success',
            'cancelled': 'danger'
        }
        return colors.get(obj.status, 'default')

    @display(description=_("Priority"), label=True)
    def priority_badge(self, obj):
        colors = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'danger'
        }
        return colors.get(obj.priority, 'default')

    @display(description=_("Progress"))
    def progress_display(self, obj):
        progress = obj.get_progress_percentage()
        return format_html(
            '<div style="width:100px;background:#f0f0f0;border-radius:4px;height:20px;">'
            '<div style="width:{}%;background:#4CAF50;height:20px;border-radius:4px;text-align:center;color:white;font-size:12px;line-height:20px;">{:.0f}%</div>'
            '</div>',
            progress, progress
        )

    @display(description=_("Task Statistics"))
    def task_stats(self, obj):
        stats = obj.get_task_distribution()
        return format_html(
            '<strong>Total:</strong> {} | '
            '<span style="color:#2196F3;">To Do: {}</span> | '
            '<span style="color:#FF9800;">In Progress: {}</span> | '
            '<span style="color:#F44336;">On Hold: {}</span> | '
            '<span style="color:#4CAF50;">Completed: {}</span>',
            stats['total'], stats['todo'], stats['in_progress'], 
            stats['on_hold'], stats['completed']
        )

    @display(description=_("Budget Information"))
    def budget_info(self, obj):
        budget = obj.get_budget_status()
        if budget['remaining'] is None:
            return _("No budget set")
        
        color = '#F44336' if budget['is_over_budget'] else '#4CAF50'
        return format_html(
            '<span style="color:{};">Remaining: ${:,.2f} ({:.1f}% used)</span>',
            color, budget['remaining'], budget['percentage_used']
        )


class TaskChecklistInline(TabularInline):
    model = Task.checklists.through
    extra = 0


class TaskCommentInline(TabularInline):
    model = TaskComment
    extra = 0
    fields = ['commented_by', 'comment', 'created_at']
    readonly_fields = ['created_at']


class DailyTimeLogInline(TabularInline):
    model = DailyTimeLog
    extra = 0
    fields = ['log_date', 'hours_worked', 'description']


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ['title', 'project', 'assigned_to', 'status_badge', 'priority_badge', 
                    'due_date', 'is_overdue_display', 'progress_display']
    list_filter = ['status', 'priority', 'project', 'is_blocked', ('due_date', RangeDateFilter)]
    search_fields = ['title', 'description', 'project__name', 'assigned_to__name']
    readonly_fields = ['created_at', 'updated_at', 'completed_at', 'is_overdue_display', 
                       'progress_display', 'efficiency_display']
    inlines = [DailyTimeLogInline, TaskCommentInline]
    
    fieldsets = (
        (_("Task Information"), {
            'fields': ('project', 'title', 'description', 'status', 'priority')
        }),
        (_("Assignment"), {
            'fields': ('assigned_by', 'assigned_to')
        }),
        (_("Timeline"), {
            'fields': ('due_date', 'estimated_hours', 'actual_hours', 'is_overdue_display')
        }),
        (_("Blocking"), {
            'fields': ('is_blocked', 'blocking_reason'),
            'classes': ('collapse',)
        }),
        (_("Progress"), {
            'fields': ('progress_display', 'efficiency_display'),
            'classes': ('collapse',)
        }),
        (_("System Information"), {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    @display(description=_("Status"), label=True)
    def status_badge(self, obj):
        colors = {
            'todo': 'info',
            'in_progress': 'warning',
            'on_hold': 'danger',
            'completed': 'success',
            'cancelled': 'danger'
        }
        return colors.get(obj.status, 'default')

    @display(description=_("Priority"), label=True)
    def priority_badge(self, obj):
        colors = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'danger'
        }
        return colors.get(obj.priority, 'default')

    @display(description=_("Overdue"), boolean=True)
    def is_overdue_display(self, obj):
        return obj.is_overdue()

    @display(description=_("Progress"))
    def progress_display(self, obj):
        progress = obj.get_progress_percentage()
        return format_html('{:.1f}%', progress)

    @display(description=_("Efficiency"))
    def efficiency_display(self, obj):
        efficiency = obj.get_efficiency_ratio()
        color = '#F44336' if efficiency > 100 else '#4CAF50'
        return format_html('<span style="color:{};">{:.1f}%</span>', color, efficiency)


@admin.register(TaskChecklist)
class TaskChecklistAdmin(ModelAdmin):
    list_display = ['title', 'is_completed', 'completed_at', 'created_at']
    list_filter = ['is_completed', ('created_at', RangeDateFilter)]
    search_fields = ['title']
    readonly_fields = ['created_at']


@admin.register(TaskComment)
class TaskCommentAdmin(ModelAdmin):
    list_display = ['task', 'commented_by', 'comment_preview', 'created_at']
    list_filter = [('created_at', RangeDateFilter), 'commented_by']
    search_fields = ['comment', 'task__title']
    readonly_fields = ['created_at']

    @display(description=_("Comment"))
    def comment_preview(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment


@admin.register(ProjectMember)
class ProjectMemberAdmin(ModelAdmin):
    list_display = ['employee', 'project', 'role', 'reporting_to', 'joined_date']
    list_filter = ['role', 'project', ('joined_date', RangeDateFilter)]
    search_fields = ['employee__name', 'project__name']
    
    fieldsets = (
        (_("Assignment"), {
            'fields': ('project', 'employee', 'role')
        }),
        (_("Reporting"), {
            'fields': ('reporting_to',)
        }),
        (_("Timeline"), {
            'fields': ('joined_date', 'left_date')
        }),
    )


@admin.register(ProjectReport)
class ProjectReportAdmin(ModelAdmin):
    list_display = ['project', 'report_date', 'reported_by', 'completed_tasks', 
                    'pending_tasks', 'blocked_tasks', 'total_hours_logged']
    list_filter = [('report_date', RangeDateFilter), 'project', 'reported_by']
    search_fields = ['project__name', 'issues_summary', 'notes']
    readonly_fields = ['created_at']
    
    fieldsets = (
        (_("Report Information"), {
            'fields': ('project', 'reported_by', 'report_date')
        }),
        (_("Progress Data"), {
            'fields': ('completed_tasks', 'pending_tasks', 'blocked_tasks', 'total_hours_logged')
        }),
        (_("Budget"), {
            'fields': ('budget_spent_this_period',)
        }),
        (_("Details"), {
            'fields': ('issues_summary', 'planned_activities', 'notes')
        }),
        (_("System Information"), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(DailyTimeLog)
class DailyTimeLogAdmin(ModelAdmin):
    list_display = ['task', 'logged_by', 'log_date', 'hours_worked', 'description_preview']
    list_filter = [('log_date', RangeDateFilter), 'logged_by', 'task__project']
    search_fields = ['task__title', 'logged_by__name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_("Log Information"), {
            'fields': ('task', 'logged_by', 'log_date', 'hours_worked')
        }),
        (_("Description"), {
            'fields': ('description',)
        }),
        (_("System Information"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @display(description=_("Description"))
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description