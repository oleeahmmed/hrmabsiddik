from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta
from core.models import Project, Task, Company

@staff_member_required
def project_report_dashboard(request):
    """প্রজেক্ট রিপোর্ট ড্যাশবোর্ড"""
    # প্রজেক্ট ডাটা
    projects = Project.objects.select_related('company', 'owner', 'project_manager').prefetch_related('tasks')
    
    # সামগ্রিক স্ট্যাটিস্টিক্স
    total_projects = projects.count()
    active_projects = projects.filter(is_active=True).count()
    completed_projects = projects.filter(status='completed').count()
    overdue_projects = projects.filter(end_date__lt=timezone.now().date(), status__in=['planning', 'in_progress']).count()
    
    # বাজেট স্ট্যাটিস্টিক্স
    budget_stats = projects.aggregate(
        total_budget=Sum('total_budget'),
        spent_budget=Sum('spent_budget'),
    )
    
    # গড় বাজেট আলাদাভাবে calculate করুন
    if total_projects > 0:
        avg_budget = budget_stats['total_budget'] / total_projects if budget_stats['total_budget'] else 0
    else:
        avg_budget = 0
    
    budget_stats['avg_budget'] = avg_budget
    
    # প্রজেক্ট স্ট্যাটাস অনুযায়ী গণনা
    status_stats = projects.values('status').annotate(count=Count('id'))
    status_distribution = {stat['status']: stat['count'] for stat in status_stats}
    
    # প্রায়োরিটি অনুযায়ী গণনা
    priority_stats = projects.values('priority').annotate(count=Count('id'))
    priority_distribution = {stat['priority']: stat['count'] for stat in priority_stats}
    
    # টাস্ক স্ট্যাটিস্টিক্স
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(status='completed').count()
    overdue_tasks = Task.objects.filter(due_date__lt=timezone.now().date(), status__in=['todo', 'in_progress']).count()
    
    # সাম্প্রতিক প্রজেক্ট
    recent_projects = projects.order_by('-created_at')[:5]
    
    # 🔥 FIXED: কোম্পানি অনুযায়ী প্রজেক্ট - correct related name ব্যবহার করুন
    company_stats = Company.objects.annotate(
        project_count=Count('core_project_items'),  # 🔥 CHANGE: 'project_items' থেকে 'core_project_items'
        active_projects=Count('core_project_items', filter=Q(core_project_items__is_active=True))  # 🔥 CHANGE
    ).filter(project_count__gt=0)
    
    context = {
        'title': 'Project Reports Dashboard',
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'overdue_projects': overdue_projects,
        'budget_stats': budget_stats,
        'status_distribution': status_distribution,
        'priority_distribution': priority_distribution,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'recent_projects': recent_projects,
        'company_stats': company_stats,
    }
    
    return render(request, 'admin/project_reports.html', context)

@staff_member_required
def project_detailed_report(request):
    """ডিটেইল্ড প্রজেক্ট রিপোর্ট"""
    projects = Project.objects.select_related('company', 'owner', 'project_manager').prefetch_related('tasks').all()
    
    # ফিল্টারিং
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    company_filter = request.GET.get('company')
    
    if status_filter:
        projects = projects.filter(status=status_filter)
    if priority_filter:
        projects = projects.filter(priority=priority_filter)
    if company_filter:
        projects = projects.filter(company_id=company_filter)
    
    # প্রতিটি প্রজেক্টের জন্য progress calculate করুন
    for project in projects:
        project.calculated_progress = project.get_progress_percentage()
        project.calculated_task_distribution = project.get_task_distribution()
        project.calculated_budget_status = project.get_budget_status()
    
    context = {
        'title': 'Detailed Project Report',
        'projects': projects,
        'status_choices': Project.STATUS_CHOICES,
        'priority_choices': Project.PRIORITY_CHOICES,
        'companies': Company.objects.all(),
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'company': company_filter,
        }
    }
    
    return render(request, 'admin/project_detailed_report.html', context)

@staff_member_required
def task_performance_report(request):
    """টাস্ক পারফরমেন্স রিপোর্ট"""
    tasks = Task.objects.select_related('project', 'assigned_to', 'company').all()
    
    # ফিল্টারিং
    project_filter = request.GET.get('project')
    status_filter = request.GET.get('status')
    assigned_to_filter = request.GET.get('assigned_to')
    
    if project_filter:
        tasks = tasks.filter(project_id=project_filter)
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if assigned_to_filter:
        tasks = tasks.filter(assigned_to_id=assigned_to_filter)
    
    # পারফরমেন্স স্ট্যাটস - completion rate calculation ঠিক করুন
    total_tasks_count = tasks.count()
    completed_tasks_count = tasks.filter(status='completed').count()
    
    if total_tasks_count > 0:
        completion_rate = (completed_tasks_count / total_tasks_count) * 100
    else:
        completion_rate = 0
    
    performance_stats = {
        'total_tasks': total_tasks_count,
        'avg_estimated_hours': tasks.aggregate(avg=Avg('estimated_hours'))['avg'] or 0,
        'avg_actual_hours': tasks.aggregate(avg=Avg('actual_hours'))['avg'] or 0,
        'completion_rate': round(completion_rate, 2)
    }
    
    # ইউজার অনুযায়ী পারফরমেন্স
    from django.contrib.auth.models import User
    user_performance = User.objects.filter(
        my_tasks__isnull=False
    ).annotate(
        total_tasks=Count('my_tasks'),
        completed_tasks=Count('my_tasks', filter=Q(my_tasks__status='completed')),
        overdue_tasks=Count('my_tasks', filter=Q(my_tasks__due_date__lt=timezone.now().date()) & ~Q(my_tasks__status='completed'))
    ).filter(total_tasks__gt=0)
    
    context = {
        'title': 'Task Performance Report',
        'tasks': tasks,
        'performance_stats': performance_stats,
        'user_performance': user_performance,
        'projects': Project.objects.all(),
        'status_choices': Task.STATUS_CHOICES,
        'current_filters': {
            'project': project_filter,
            'status': status_filter,
            'assigned_to': assigned_to_filter,
        }
    }
    
    return render(request, 'admin/task_performance_report.html', context)