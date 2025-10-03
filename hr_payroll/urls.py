# zkteco/urls.py
from django.urls import path
from . import  attendance_log_views, attendance_generation_views_enhanced
from . import simple_attendance_generation_views
from .views import location_views
from .views import employee_views
from .views import leave_views
from .views import attendance_config_views
from .views import attendance_reports
from .views import hourly_attendance,device_views
app_name = 'zkteco'

urlpatterns = [
    # ==================== AUTHENTICATION VIEWS ====================
    path('', device_views.home_dashboard, name='home'),
    path('login/', device_views.login_view, name='login'),
    path('logout/', device_views.logout_view, name='logout'),
    
    # ==================== DEVICE MANAGEMENT VIEWS ====================
    path('devices/', device_views.device_list, name='device_list'),
    path('devices/add/', device_views.device_add, name='device_add'),
    path('devices/<int:device_id>/edit/', device_views.device_edit, name='device_edit'),
    path('devices/<int:device_id>/detail/', device_views.device_detail, name='device_detail'),
    path('devices/<int:device_id>/delete/', device_views.device_delete, name='device_delete'),
    
    # Device Management AJAX API Endpoints
    path('api/devices/<int:device_id>/toggle-status/', device_views.device_toggle_status, name='device_toggle_status'),
    path('api/test-connections/', device_views.test_connections, name='test_connections'),
    
    # User Management AJAX API Endpoints  
    path('api/fetch-users/', device_views.fetch_users_data, name='fetch_users_data'),
    path('api/import-users/', device_views.import_users_data, name='import_users_data'),
    
    # ==================== ATTENDANCE LOG VIEWS ====================
    path('attendance-logs/', attendance_log_views.attendance_logs, name='attendance_logs'),
    
    # Attendance Log Management AJAX API Endpoints
    path('api/fetch-attendance/', attendance_log_views.fetch_attendance_data, name='fetch_attendance_data'),
    path('api/import-attendance/', attendance_log_views.import_attendance_data, name='import_attendance_data'),
    path('api/attendance-analytics/', attendance_log_views.get_attendance_analytics, name='get_attendance_analytics'),
    
    # ==================== HOURLY ATTENDANCE REPORT VIEWS ====================
    path('hourly-report/', hourly_attendance.hourly_attendance_report, name='hourly_attendance_report'),
    path('hourly-report/<int:employee_id>/<str:month_year>/', hourly_attendance.hourly_attendance_detail, name='hourly_attendance_detail'),
    path('hourly-report/export/', hourly_attendance.export_hourly_report, name='export_hourly_report'),

    # ==================== SIMPLE ATTENDANCE GENERATION ====================
    path('simple-attendance/', simple_attendance_generation_views.simple_attendance_generation, name='simple_attendance_generation'),
    path('simple-attendance/preview/', simple_attendance_generation_views.simple_attendance_preview, name='simple_attendance_preview'),
    path('simple-attendance/generate/', simple_attendance_generation_views.simple_generate_records, name='simple_generate_records'),
    path('simple-attendance/export/', simple_attendance_generation_views.simple_export_csv, name='simple_export_csv'),

    # ==================== ATTENDANCE REPORTS VIEWS ====================
    path('reports/', attendance_reports.reports_dashboard, name='attendance_reports_main'),
    path('reports/daily/', attendance_reports.daily_attendance_report, name='daily_attendance_report'),
    path('reports/monthly/', attendance_reports.monthly_attendance_summary, name='monthly_attendance_report'),
    path('reports/overtime/', attendance_reports.overtime_payment_report, name='overtime_payment_report'),
    path('reports/hourly-wage/', attendance_reports.hourly_wage_report, name='hourly_wage_report'),
    path('reports/leave-absence/', attendance_reports.leave_absence_report, name='leave_absence_report'),
    path('reports/late-early/', attendance_reports.late_early_report, name='late_early_report'),
    path('reports/payroll/', attendance_reports.payroll_summary_report, name='payroll_summary_report'),
    path('reports/department-analytics/', attendance_reports.department_analytics_report, name='department_analytics_report'),
    path('reports/shift-compliance/', attendance_reports.shift_roster_compliance_report, name='shift_compliance_report'),
    path('reports/employee-performance/', attendance_reports.employee_performance_report, name='employee_performance_report'),

    # ==================== LOCATION URLS ====================
    path('locations/', location_views.LocationListView.as_view(), name='location_list'),
    path('locations/create/', location_views.LocationCreateView.as_view(), name='location_create'),
    path('locations/<int:pk>/', location_views.LocationDetailView.as_view(), name='location_detail'),
    path('locations/<int:pk>/update/', location_views.LocationUpdateView.as_view(), name='location_update'),
    path('locations/<int:pk>/delete/', location_views.LocationDeleteView.as_view(), name='location_delete'),
    
    # ==================== USER LOCATION URLS ====================
    path('user-locations/', location_views.UserLocationListView.as_view(), name='user_location_list'),
    path('user-locations/create/', location_views.UserLocationCreateView.as_view(), name='user_location_create'),
    path('user-locations/<int:pk>/update/', location_views.UserLocationUpdateView.as_view(), name='user_location_update'),
    path('user-locations/<int:pk>/delete/', location_views.UserLocationDeleteView.as_view(), name='user_location_delete'),
    
    # ==================== MOBILE ATTENDANCE URLS ====================
    path('mobile-attendance/', location_views.MobileAttendanceView.as_view(), name='mobile_attendance'),
    path('api/get-locations/', location_views.GetLocationsView.as_view(), name='get_locations'),
    path('api/mark-attendance/', location_views.MarkAttendanceView.as_view(), name='mark_attendance'),
    
    # ==================== ATTENDANCE LOG URLS ====================
    path('attendance-logs/', location_views.AttendanceLogListView.as_view(), name='attendance_log_list'),
    path('attendance-logs/<int:pk>/', location_views.AttendanceLogDetailView.as_view(), name='attendance_log_detail'),
    
    # ==================== EMPLOYEE CRUD ====================
    path('employees/', employee_views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/create/', employee_views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/', employee_views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<int:pk>/update/', employee_views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<int:pk>/delete/', employee_views.EmployeeDeleteView.as_view(), name='employee_delete'),
    
    # ==================== LEAVE MANAGEMENT ====================
    path('leaves/', leave_views.LeaveListView.as_view(), name='leave_list'),
    path('leaves/create/', leave_views.LeaveCreateView.as_view(), name='leave_create'),
    path('leaves/<int:pk>/', leave_views.LeaveDetailView.as_view(), name='leave_detail'),
    path('leaves/<int:pk>/update/', leave_views.LeaveUpdateView.as_view(), name='leave_update'),
    path('leaves/<int:pk>/delete/', leave_views.LeaveDeleteView.as_view(), name='leave_delete'),
    
    # Leave Status Change API
    path('api/leaves/<int:pk>/change-status/', leave_views.LeaveStatusChangeView.as_view(), name='leave_change_status'),
   
    # ==================== ATTENDANCE PROCESSOR CONFIGURATION ====================
    path('attendance-configs/', attendance_config_views.AttendanceConfigListView.as_view(), name='config_list'),
    path('attendance-configs/create/', attendance_config_views.AttendanceConfigCreateView.as_view(), name='config_create'),
    path('attendance-configs/<int:pk>/', attendance_config_views.AttendanceConfigDetailView.as_view(), name='config_detail'),
    path('attendance-configs/<int:pk>/update/', attendance_config_views.AttendanceConfigUpdateView.as_view(), name='config_update'),
    path('attendance-configs/<int:pk>/delete/', attendance_config_views.AttendanceConfigDeleteView.as_view(), name='config_delete'),
    
    # Attendance Config API Endpoints
    path('api/attendance-configs/<int:pk>/toggle-status/', attendance_config_views.AttendanceConfigToggleStatusView.as_view(), name='config_toggle_status'),
    path('api/attendance-configs/<int:pk>/duplicate/', attendance_config_views.AttendanceConfigDuplicateView.as_view(), name='config_duplicate'),
]
