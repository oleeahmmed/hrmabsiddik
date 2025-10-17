# zkteco/urls.py
from django.urls import path
from .views import dashboard_views
from . import attendance_log_views
from . import simple_attendance_generation_views
from .views import location_views
from .views import employee_views

from .views import employee_document_views

from .views import leave_views
from .views import attendance_config_views
from .views import attendance_reports

from .views import hourly_attendance
from .views import device_views
from .views import attendance_views

from .views import shift_views
from .views import roster_views
from .views import holiday_views
from .views import complaint_views
from .views import overtime_views

app_name = 'zkteco'

urlpatterns = [
    # ==================== AUTHENTICATION VIEWS ====================
    path('', dashboard_views.HomeView.as_view(), name='home'),
    path('staff-dashboard/', dashboard_views.StaffHomeDashboardView.as_view(), name='staff_home'),
    path('user-dashboard/', dashboard_views.UserHomeDashboardView.as_view(), name='user_home'),
    path('login/', dashboard_views.LoginView.as_view(), name='login'),
    path('logout/', dashboard_views.LogoutView.as_view(), name='logout'),
    
    # ==================== DEVICE MANAGEMENT VIEWS ====================
    path('devices/', device_views.DeviceListView.as_view(), name='device_list'),
    path('devices/add/', device_views.DeviceCreateView.as_view(), name='device_add'),
    path('devices/<int:device_id>/edit/', device_views.DeviceUpdateView.as_view(), name='device_edit'),
    path('devices/<int:device_id>/detail/', device_views.DeviceDetailView.as_view(), name='device_detail'),
    path('devices/<int:device_id>/delete/', device_views.DeviceDeleteView.as_view(), name='device_delete'),
    
    # Device Management AJAX API Endpoints
    path('api/devices/<int:device_id>/toggle-status/', device_views.DeviceToggleStatusView.as_view(), name='device_toggle_status'),
    path('api/test-connections/', device_views.TestConnectionsView.as_view(), name='test_connections'),
    
    # User Management AJAX API Endpoints  
    path('api/fetch-users/', device_views.FetchUsersDataView.as_view(), name='fetch_users_data'),
    path('api/import-users/', device_views.ImportUsersDataView.as_view(), name='import_users_data'),
    path('api/clear-device-data/', device_views.ClearDeviceDataView.as_view(), name='clear_device_data'),
    
    # Attendance Log Management
    path('attendance-logs/', attendance_log_views.AttendanceLogListView.as_view(), name='attendance_log_list'),
    path('attendance-logs/create/', attendance_log_views.AttendanceLogCreateView.as_view(), name='attendance_log_create'),
    path('attendance-logs/<int:pk>/', attendance_log_views.AttendanceLogDetailView.as_view(), name='attendance_log_detail'),
    path('attendance-logs/<int:pk>/edit/', attendance_log_views.AttendanceLogUpdateView.as_view(), name='attendance_log_update'),
    path('attendance-logs/<int:pk>/delete/', attendance_log_views.AttendanceLogDeleteView.as_view(), name='attendance_log_delete'),
    
    # Attendance Log Management AJAX API Endpoints (now class-based)
    path('api/fetch-attendance/', attendance_log_views.FetchAttendanceDataView.as_view(), name='fetch_attendance_data'),
    path('api/import-attendance/', attendance_log_views.ImportAttendanceDataView.as_view(), name='import_attendance_data'),
    
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
    path('reports/employee-monthly/', attendance_reports.employee_monthly_attendance, name='employee_monthly_attendance'),
    path('reports/payroll-summary/', attendance_reports.payroll_summary_report, name='payroll_summary_report'),

    # Shift Management URLs
    path('shifts/', shift_views.ShiftListView.as_view(), name='shift_list'),
    path('shifts/create/', shift_views.ShiftCreateView.as_view(), name='shift_create'),
    path('shifts/<int:pk>/', shift_views.ShiftDetailView.as_view(), name='shift_detail'),
    path('shifts/<int:pk>/update/', shift_views.ShiftUpdateView.as_view(), name='shift_update'),
    path('shifts/<int:pk>/delete/', shift_views.ShiftDeleteView.as_view(), name='shift_delete'),
    # Roster URLs
    path('rosters/', roster_views.RosterListView.as_view(), name='roster_list'),
    path('roster/create/', roster_views.RosterCreateView.as_view(), name='roster_create'),
    path('roster/<int:pk>/', roster_views.RosterDetailView.as_view(), name='roster_detail'),
    path('roster/<int:pk>/update/', roster_views.RosterUpdateView.as_view(), name='roster_update'),
    path('roster/<int:pk>/delete/', roster_views.RosterDeleteView.as_view(), name='roster_delete'),
    # ==================== OVERTIME MANAGEMENT ====================
    path('overtime/', overtime_views.OvertimeListView.as_view(), name='overtime_list'),
    path('overtime/create/', overtime_views.OvertimeCreateView.as_view(), name='overtime_create'),
    path('overtime/<int:pk>/', overtime_views.OvertimeDetailView.as_view(), name='overtime_detail'),
    path('overtime/<int:pk>/update/', overtime_views.OvertimeUpdateView.as_view(), name='overtime_update'),
    path('overtime/<int:pk>/delete/', overtime_views.OvertimeDeleteView.as_view(), name='overtime_delete'),
    path('overtime/<int:pk>/status/', overtime_views.OvertimeStatusChangeView.as_view(), name='overtime_status_change'),

    # Overtime Status Change API
    path('api/overtime/<int:pk>/change-status/', overtime_views.OvertimeStatusChangeView.as_view(), name='overtime_change_status'),
    # ==================== HOLIDAY MANAGEMENT URLS ====================
    path('holidays/', holiday_views.HolidayListView.as_view(), name='holiday_list'),
    path('holidays/create/', holiday_views.HolidayCreateView.as_view(), name='holiday_create'),
    path('holidays/<int:pk>/', holiday_views.HolidayDetailView.as_view(), name='holiday_detail'),
    path('holidays/<int:pk>/update/', holiday_views.HolidayUpdateView.as_view(), name='holiday_update'),
    path('holidays/<int:pk>/delete/', holiday_views.HolidayDeleteView.as_view(), name='holiday_delete'),   
    # Roster Day URLs
    path('roster-days/', shift_views.RosterDayListView.as_view(), name='roster_day_list'),
    path('roster-days/create/', shift_views.RosterDayCreateView.as_view(), name='roster_day_create'),
    path('roster-days/<int:pk>/', shift_views.RosterDayDetailView.as_view(), name='roster_day_detail'),
    path('roster-days/<int:pk>/update/', shift_views.RosterDayUpdateView.as_view(), name='roster_day_update'),
    path('roster-days/<int:pk>/delete/', shift_views.RosterDayDeleteView.as_view(), name='roster_day_delete'),
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
    path('api/get-user-attendance/', location_views.GetUserAttendanceLogsView.as_view(), name='get_user_attendance'),
    
    # ==================== ATTENDANCE LOG URLS ====================
    path('attendance-logs/', location_views.AttendanceLogListView.as_view(), name='attendance_log_list'),
    path('attendance-logs/<int:pk>/', location_views.AttendanceLogDetailView.as_view(), name='attendance_log_detail'),
    
    # ==================== EMPLOYEE CRUD ====================
    path('employees/', employee_views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/create/', employee_views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/', employee_views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<int:pk>/update/', employee_views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<int:pk>/delete/', employee_views.EmployeeDeleteView.as_view(), name='employee_delete'),

    # Employee Document URLs
    path('employee-documents/', employee_document_views.EmployeeDocumentListView.as_view(), name='employee_document_list'),
    path('employee-documents/create/', employee_document_views.EmployeeDocumentCreateView.as_view(), name='employee_document_create'),
    path('employee-documents/<int:pk>/', employee_document_views.EmployeeDocumentDetailView.as_view(), name='employee_document_detail'),
    path('employee-documents/<int:pk>/edit/', employee_document_views.EmployeeDocumentUpdateView.as_view(), name='employee_document_update'),
    path('employee-documents/<int:pk>/delete/', employee_document_views.EmployeeDocumentDeleteView.as_view(), name='employee_document_delete'),

    # ==================== LEAVE MANAGEMENT ====================
    # Leave Management URLs
    path('leaves/', leave_views.LeaveListView.as_view(), name='leave_list'),
    path('leaves/create/', leave_views.LeaveCreateView.as_view(), name='leave_create'),
    path('leaves/<int:pk>/', leave_views.LeaveDetailView.as_view(), name='leave_detail'),
    path('leaves/<int:pk>/update/', leave_views.LeaveUpdateView.as_view(), name='leave_update'),
    path('leaves/<int:pk>/delete/', leave_views.LeaveDeleteView.as_view(), name='leave_delete'),
    path('leaves/<int:pk>/status/', leave_views.LeaveStatusChangeView.as_view(), name='leave_status_change'),
    
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
    
    # ==================== ATTENDANCE MANAGEMENT ====================
    path('attendance/', attendance_views.AttendanceListView.as_view(), name='attendance_list'),
    path('attendance/create/', attendance_views.AttendanceCreateView.as_view(), name='attendance_create'),
    path('attendance/<int:pk>/', attendance_views.AttendanceDetailView.as_view(), name='attendance_detail'),
    path('attendance/<int:pk>/update/', attendance_views.AttendanceUpdateView.as_view(), name='attendance_update'),
    path('attendance/<int:pk>/delete/', attendance_views.AttendanceDeleteView.as_view(), name='attendance_delete'),
    path('attendance/export/', attendance_views.AttendanceExportCSVView.as_view(), name='attendance_export'),

    # ==================== COMPLAINT MANAGEMENT URLS ====================
    path('complaints/', complaint_views.ComplaintListView.as_view(), name='complaint_list'),
    path('complaints/create/', complaint_views.ComplaintCreateView.as_view(), name='complaint_create'),
    path('complaints/<int:pk>/', complaint_views.ComplaintDetailView.as_view(), name='complaint_detail'),
    path('complaints/<int:pk>/update/', complaint_views.ComplaintUpdateView.as_view(), name='complaint_update'),
    path('complaints/<int:pk>/delete/', complaint_views.ComplaintDeleteView.as_view(), name='complaint_delete'),




]