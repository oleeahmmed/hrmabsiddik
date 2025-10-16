from django.urls import path

# Import all views directly from their files
from .views.dashboard_views import MainDashboardView, ProjectDashboardView, MyTasksView, MyProjectsView
from .views.company_views import (
    CompanyListView, CompanyListAllView, CompanyCreateView,
    CompanyDetailView, CompanyUpdateView, CompanyDeleteView, CompanyPrintView
)
from .views.userprofile_views import (
    UserProfileListView, UserProfileListAllView, UserProfileCreateView,
    UserProfileDetailView, UserProfileUpdateView, UserProfileDeleteView, UserProfilePrintView,
    MyProfileView, MyProfileUpdateView
)
from .views.project_views import (
    ProjectListView, ProjectListAllView, ProjectCreateView,
    ProjectDetailView, ProjectUpdateView, ProjectDeleteView, ProjectPrintView
)
from .views.task_views import (
    TaskListView, TaskListAllView, TaskCreateView,
    TaskDetailView, TaskUpdateView, TaskDeleteView, TaskPrintView
)
from .views.taskcomment_views import (
    TaskCommentListView, TaskCommentListAllView, TaskCommentCreateView,
    TaskCommentDetailView, TaskCommentUpdateView, TaskCommentDeleteView
)

from .views.project_reports import (
    project_report_dashboard,
    project_detailed_report,
    task_performance_report
)


app_name = 'core'

urlpatterns = [
    # ==================== DASHBOARD URLs ====================
    path('', MainDashboardView.as_view(), name='main_dashboard'),
    path('project-dashboard/', ProjectDashboardView.as_view(), name='project_dashboard'),
    path('my-tasks/', MyTasksView.as_view(), name='my_tasks'),
    path('my-projects/', MyProjectsView.as_view(), name='my_projects'),
    
    # ==================== COMPANY URLs ====================
    path('companies/', CompanyListView.as_view(), name='company_list'),
    path('companies/all/', CompanyListAllView.as_view(), name='company_list_all'),
    path('companies/create/', CompanyCreateView.as_view(), name='company_create'),
    path('companies/<int:pk>/', CompanyDetailView.as_view(), name='company_detail'),
    path('companies/<int:pk>/update/', CompanyUpdateView.as_view(), name='company_update'),
    path('companies/<int:pk>/delete/', CompanyDeleteView.as_view(), name='company_delete'),
    path('companies/<int:pk>/print/', CompanyPrintView.as_view(), name='company_print'),
    
    # ==================== USER PROFILE URLs ====================
    path('profiles/', UserProfileListView.as_view(), name='userprofile_list'),
    path('profiles/all/', UserProfileListAllView.as_view(), name='userprofile_list_all'),
    path('profiles/create/', UserProfileCreateView.as_view(), name='userprofile_create'),
    path('profiles/<int:pk>/', UserProfileDetailView.as_view(), name='userprofile_detail'),
    path('profiles/<int:pk>/update/', UserProfileUpdateView.as_view(), name='userprofile_update'),
    path('profiles/<int:pk>/delete/', UserProfileDeleteView.as_view(), name='userprofile_delete'),
    path('profiles/<int:pk>/print/', UserProfilePrintView.as_view(), name='userprofile_print'),
    
    # ==================== MY PROFILE URLs ====================
    path('my-profile/', MyProfileView.as_view(), name='my_profile'),
    path('my-profile/update/', MyProfileUpdateView.as_view(), name='my_profile_update'),
    
    # ==================== PROJECT URLs ====================
    path('projects/', ProjectListView.as_view(), name='project_list'),
    path('projects/all/', ProjectListAllView.as_view(), name='project_list_all'),
    path('projects/create/', ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/update/', ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<int:pk>/delete/', ProjectDeleteView.as_view(), name='project_delete'),
    path('projects/<int:pk>/print/', ProjectPrintView.as_view(), name='project_print'),
    
    # ==================== TASK URLs ====================
    path('tasks/', TaskListView.as_view(), name='task_list'),
    path('tasks/all/', TaskListAllView.as_view(), name='task_list_all'),
    path('tasks/create/', TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update/', TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/print/', TaskPrintView.as_view(), name='task_print'),
    
    # ==================== TASK COMMENT URLs ====================
    path('task-comments/', TaskCommentListView.as_view(), name='taskcomment_list'),
    path('task-comments/all/', TaskCommentListAllView.as_view(), name='taskcomment_list_all'),
    path('task-comments/create/', TaskCommentCreateView.as_view(), name='taskcomment_create'),
    path('task-comments/<int:pk>/', TaskCommentDetailView.as_view(), name='taskcomment_detail'),
    path('task-comments/<int:pk>/update/', TaskCommentUpdateView.as_view(), name='taskcomment_update'),
    path('task-comments/<int:pk>/delete/', TaskCommentDeleteView.as_view(), name='taskcomment_delete'),


    # Project Reports URLs - core/ prefix সহ
    path('project-reports/dashboard/', project_report_dashboard, name='project_report_dashboard'),
    path('project-reports/detailed/', project_detailed_report, name='project_detailed_report'),
    path('project-reports/task-performance/', task_performance_report, name='task_performance_report'),
    
    ]