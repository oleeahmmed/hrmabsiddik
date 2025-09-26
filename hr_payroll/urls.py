# zkteco/urls.py
from django.urls import path
from . import device_views, attendance_log_views, attendance_generation_views_enhanced, hourly_attendance

app_name = 'zkteco'

urlpatterns = [
    # ==================== AUTHENTICATION VIEWS ====================
    path('', device_views.device_list, name='home'),  # Redirect to device list as home
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
    # path('api/clear-device-data/', device_views.clear_device_data, name='clear_device_data'),
    
    # User Management AJAX API Endpoints  
    path('api/fetch-users/', device_views.fetch_users_data, name='fetch_users_data'),
    path('api/import-users/', device_views.import_users_data, name='import_users_data'),
    
    # ==================== ATTENDANCE LOG VIEWS ====================
    path('attendance-logs/', attendance_log_views.attendance_logs, name='attendance_logs'),
    
    # Attendance Log Management AJAX API Endpoints
    path('api/fetch-attendance/', attendance_log_views.fetch_attendance_data, name='fetch_attendance_data'),
    path('api/import-attendance/', attendance_log_views.import_attendance_data, name='import_attendance_data'),
    path('api/attendance-analytics/', attendance_log_views.get_attendance_analytics, name='get_attendance_analytics'),
    
    # ==================== ENHANCED ATTENDANCE GENERATION VIEWS ====================
    path('attendance-generation/', attendance_generation_views_enhanced.attendance_generation, name='attendance_generation'),
    
    # Enhanced Attendance Generation AJAX API Endpoints
    path('api/generate-attendance/', attendance_generation_views_enhanced.generate_attendance_records, name='generate_attendance_records'),
    path('api/attendance-generation-preview/', attendance_generation_views_enhanced.attendance_generation_preview, name='attendance_generation_preview'),
    path('api/bulk-delete-attendance/', attendance_generation_views_enhanced.bulk_delete_attendance_records, name='bulk_delete_attendance_records'),
    path('api/export-preview-data/', attendance_generation_views_enhanced.export_preview_data, name='export_preview_data'),

    # ==================== HOURLY ATTENDANCE REPORT VIEWS ====================
    # Main hourly attendance report view
    path('hourly-report/', hourly_attendance.hourly_attendance_report, name='hourly_attendance_report'),

    # Detailed view for a specific employee
    path('hourly-report/<int:employee_id>/<str:month_year>/', hourly_attendance.hourly_attendance_detail, name='hourly_attendance_detail'),

    # Export report (CSV/Excel)
    path('hourly-report/export/', hourly_attendance.export_hourly_report, name='export_hourly_report'),
]