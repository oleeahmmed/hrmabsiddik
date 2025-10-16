from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta

from .base_views import CompanyRequiredMixin, CompanyFilterMixin, CommonContextMixin
from ..models import Project, Task, UserProfile, Company


class MainDashboardView(CompanyRequiredMixin, TemplateView):
    """Main Dashboard with Company Stats - No specific permission required"""
    template_name = 'core/main_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        user_company = user.profile.company
        
        # Get company hierarchy
        company_ids = [c.id for c in user_company.get_all_subsidiaries(include_self=True)]
        
        # Quick stats
        context['user_company'] = user_company
        context['hierarchy_path'] = user_company.get_hierarchy_path()
        context['subsidiaries'] = user_company.subsidiaries.filter(is_active=True)
        
        # Statistics
        total_projects = Project.objects.filter(company__id__in=company_ids)
        total_tasks = Task.objects.filter(company__id__in=company_ids)
        
        context['stats'] = {
            'total_companies': len(company_ids),
            'total_projects': total_projects.count(),
            'active_projects': total_projects.filter(is_active=True).count(),
            'total_tasks': total_tasks.count(),
            'completed_tasks': total_tasks.filter(status='completed').count(),
            'overdue_tasks': total_tasks.filter(
                due_date__lt=timezone.now().date(),
                status__in=['todo', 'in_progress']
            ).count(),
            'total_users': UserProfile.objects.filter(
                company__id__in=company_ids,
                is_active=True
            ).count(),
        }
        
        # User-specific stats
        context['my_stats'] = {
            'managed_projects': total_projects.filter(
                project_manager=user
            ).count(),
            'led_projects': total_projects.filter(
                technical_lead=user
            ).count(),
            'assigned_tasks': total_tasks.filter(
                assigned_to=user,
                status__in=['todo', 'in_progress']
            ).count(),
        }
        
        # Recent activities
        context['recent_projects'] = total_projects.order_by('-created_at')[:5]
        context['upcoming_tasks'] = total_tasks.filter(
            due_date__gte=timezone.now().date(),
            status__in=['todo', 'in_progress']
        ).order_by('due_date')[:10]
        
        # Permissions for UI
        context['perms'] = {
            'can_add_project': user.has_perm('core.add_project'),
            'can_add_task': user.has_perm('core.add_task'),
            'can_add_company': user.has_perm('core.add_company'),
            'can_view_projects': user.has_perm('core.view_project'),
            'can_view_tasks': user.has_perm('core.view_task'),
            'can_view_reports': user.has_perm('core.view_projectreport'),
        }
        
        return context


class ProjectDashboardView(CompanyFilterMixin, TemplateView):
    """Project Management Dashboard - No specific permission required"""
    template_name = 'core/project_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get company projects
        company_ids = self.get_user_companies(include_subsidiaries=True)
        projects = Project.objects.filter(
            company__id__in=company_ids,
            is_active=True
        ).select_related('company', 'technical_lead', 'project_manager')
        
        today = timezone.now().date()
        week_end = today + timedelta(days=7)
        
        # Project summaries
        project_summaries = []
        for project in projects:
            project_summaries.append({
                'id': project.id,
                'name': project.name,
                'company': project.company.name,
                'status': project.get_status_display(),
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
                'hours': float(project.get_total_hours()),
                'days_left': (project.end_date - today).days,
            })
        
        # Upcoming and overdue tasks
        all_tasks = Task.objects.filter(company__id__in=company_ids)
        
        context.update({
            'projects': projects,
            'project_summaries': project_summaries,
            'upcoming_tasks': all_tasks.filter(
                due_date__range=[today, week_end],
                status__in=['todo', 'in_progress']
            ).select_related('project', 'assigned_to').order_by('due_date')[:10],
            'overdue_tasks': all_tasks.filter(
                due_date__lt=today,
                status__in=['todo', 'in_progress']
            ).count(),
            'blocked_tasks': all_tasks.filter(is_blocked=True).count(),
            'stats': {
                'total_projects': projects.count(),
                'total_tasks': all_tasks.count(),
                'completed_tasks': all_tasks.filter(status='completed').count(),
                'total_hours': float(
                    all_tasks.aggregate(Sum('actual_hours'))['actual_hours__sum'] or 0
                ),
            },
            'perms': {
                'can_add_project': self.request.user.has_perm('core.add_project'),
                'can_edit_project': self.request.user.has_perm('core.change_project'),
            }
        })
        
        return context


class MyTasksView(CompanyRequiredMixin, TemplateView):
    """My Tasks Dashboard - No specific permission required"""
    template_name = 'core/my_tasks.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        my_tasks = Task.objects.filter(
            assigned_to=user
        ).select_related('project', 'company')
        
        today = timezone.now().date()
        
        # Tasks I've assigned to others
        assigned_by_me = Task.objects.filter(
            assigned_by=user
        ).select_related('project', 'assigned_to')
        
        context.update({
            'todo_tasks': my_tasks.filter(status='todo').order_by('due_date'),
            'in_progress_tasks': my_tasks.filter(
                status='in_progress'
            ).order_by('due_date'),
            'completed_tasks': my_tasks.filter(
                status='completed'
            ).order_by('-completed_at')[:10],
            'overdue_tasks': my_tasks.filter(
                due_date__lt=today,
                status__in=['todo', 'in_progress']
            ),
            'blocked_tasks': my_tasks.filter(is_blocked=True),
            'assigned_by_me': assigned_by_me.order_by('-created_at')[:10],
            'stats': {
                'total': my_tasks.count(),
                'todo': my_tasks.filter(status='todo').count(),
                'in_progress': my_tasks.filter(status='in_progress').count(),
                'completed': my_tasks.filter(status='completed').count(),
                'overdue': my_tasks.filter(
                    due_date__lt=today,
                    status__in=['todo', 'in_progress']
                ).count(),
                'blocked': my_tasks.filter(is_blocked=True).count(),
            },
            'perms': {
                'can_add_task': user.has_perm('core.add_task'),
                'can_edit_task': user.has_perm('core.change_task'),
            }
        })
        
        return context


class MyProjectsView(CompanyRequiredMixin, TemplateView):
    """My Projects Dashboard - Projects I manage or lead"""
    template_name = 'core/my_projects.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Projects where I'm project manager
        managed_projects = Project.objects.filter(
            project_manager=self.request.user,
            is_active=True
        ).select_related('company', 'technical_lead')
        
        # Projects where I'm technical lead
        led_projects = Project.objects.filter(
            technical_lead=self.request.user,
            is_active=True
        ).select_related('company', 'project_manager')
        
        # Get statistics for managed projects
        managed_summaries = []
        for project in managed_projects:
            managed_summaries.append({
                'project': project,
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
            })
        
        # Get statistics for led projects
        led_summaries = []
        for project in led_projects:
            led_summaries.append({
                'project': project,
                'progress': project.get_progress_percentage(),
                'task_dist': project.get_task_distribution(),
                'overdue': project.get_overdue_tasks(),
                'blocked': project.get_blocked_tasks().count(),
                'budget': project.get_budget_status(),
            })
        
        context.update({
            'managed_projects': managed_projects,
            'led_projects': led_projects,
            'managed_summaries': managed_summaries,
            'led_summaries': led_summaries,
            'stats': {
                'total_managed': managed_projects.count(),
                'total_led': led_projects.count(),
                'total_projects': managed_projects.count() + led_projects.count(),
            },
            'perms': {
                'can_edit_project': self.request.user.has_perm('core.change_project'),
                'can_add_task': self.request.user.has_perm('core.add_task'),
            }
        })
        
        return context