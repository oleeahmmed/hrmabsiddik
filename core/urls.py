from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Main Dashboard
    path('', views.MainDashboardView.as_view(), name='main_dashboard'),
    
    # User Profile URLs
    path('profiles/', views.UserProfileListView.as_view(), name='userprofile_list'),
    path('profiles/create/', views.UserProfileCreateView.as_view(), name='userprofile_create'),
    path('profiles/<int:pk>/', views.UserProfileDetailView.as_view(), name='userprofile_detail'),
    path('profiles/<int:pk>/update/', views.UserProfileUpdateView.as_view(), name='userprofile_update'),
    path('profiles/<int:pk>/delete/', views.UserProfileDeleteView.as_view(), name='userprofile_delete'),
    path('my-profile/', views.MyProfileView.as_view(), name='my_profile'),
    path('my-profile/update/', views.MyProfileUpdateView.as_view(), name='my_profile_update'),
    
    # Company URLs
    path('companies/', views.CompanyListView.as_view(), name='company_list'),
    path('companies/create/', views.CompanyCreateView.as_view(), name='company_create'),
    path('companies/<int:pk>/', views.CompanyDetailView.as_view(), name='company_detail'),
    path('companies/<int:pk>/update/', views.CompanyUpdateView.as_view(), name='company_update'),
    path('companies/<int:pk>/delete/', views.CompanyDeleteView.as_view(), name='company_delete'),
    
    # Project Role URLs
    path('project-roles/', views.ProjectRoleListView.as_view(), name='projectrole_list'),
    path('project-roles/create/', views.ProjectRoleCreateView.as_view(), name='projectrole_create'),
    path('project-roles/<int:pk>/', views.ProjectRoleDetailView.as_view(), name='projectrole_detail'),
    path('project-roles/<int:pk>/update/', views.ProjectRoleUpdateView.as_view(), name='projectrole_update'),
    path('project-roles/<int:pk>/delete/', views.ProjectRoleDeleteView.as_view(), name='projectrole_delete'),
    
    # Project URLs
    path('projects/', views.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/update/', views.ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('projects/<int:pk>/dashboard/', views.ProjectDetailDashboardView.as_view(), name='project_dashboard'),
    path('projects/<int:pk>/export/', views.ExportProjectReportView.as_view(), name='project_export'),
    
    # Task URLs
    path('tasks/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update/', views.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/quick-update/', views.TaskQuickUpdateView.as_view(), name='task_quick_update'),
    
    # Task Comment URLs
    path('task-comments/', views.TaskCommentListView.as_view(), name='taskcomment_list'),
    path('task-comments/create/', views.TaskCommentCreateView.as_view(), name='taskcomment_create'),
    path('task-comments/<int:pk>/', views.TaskCommentDetailView.as_view(), name='taskcomment_detail'),
    path('task-comments/<int:pk>/update/', views.TaskCommentUpdateView.as_view(), name='taskcomment_update'),
    path('task-comments/<int:pk>/delete/', views.TaskCommentDeleteView.as_view(), name='taskcomment_delete'),
    
    
    # ==================== TASK CHECKLIST URLs ====================
    path('task-checklists/', views.TaskChecklistListView.as_view(), name='taskchecklist_list'),
    path('task-checklists/create/', views.TaskChecklistCreateView.as_view(), name='taskchecklist_create'),
    path('task-checklists/<int:pk>/', views.TaskChecklistDetailView.as_view(), name='taskchecklist_detail'),
    path('task-checklists/<int:pk>/edit/', views.TaskChecklistUpdateView.as_view(), name='taskchecklist_update'),
    path('task-checklists/<int:pk>/delete/', views.TaskChecklistDeleteView.as_view(), name='taskchecklist_delete'),

    # ==================== DAILY TIME LOG URLs ====================
    path('time-logs/', views.DailyTimeLogListView.as_view(), name='dailytimelog_list'),
    path('time-logs/create/', views.DailyTimeLogCreateView.as_view(), name='dailytimelog_create'),
    path('time-logs/<int:pk>/', views.DailyTimeLogDetailView.as_view(), name='dailytimelog_detail'),
    path('time-logs/<int:pk>/edit/', views.DailyTimeLogUpdateView.as_view(), name='dailytimelog_update'),
    path('time-logs/<int:pk>/delete/', views.DailyTimeLogDeleteView.as_view(), name='dailytimelog_delete'),
]