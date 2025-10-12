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
from .views import attendance_log_reports

from .views import hourly_attendance
from .views import device_views
from .views import attendance_views
from .views import payroll_views
from .views import payroll_advanced_views
from .views import payroll_generation_views
from .views import shift_views
from .views import roster_views
from .views import holiday_views
from .views import complaint_views
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

    # ==================== ATTENDANCE LOG REPORTS (Enhanced Views) ====================


    # Daily Attendance Report from AttendanceLog
    # path('log-reports/daily/', 
    #     attendance_log_reports.DailyAttendanceLogReportView.as_view(), 
    #     name='daily_attendance_log_report'),

    # # Monthly Attendance Report from AttendanceLog
    # path('log-reports/monthly/', 
    #     attendance_log_reports.MonthlyAttendanceLogReportView.as_view(), 
    #     name='monthly_attendance_log_report'),

    # # Employee Monthly Detail Report
    # path('log-reports/employee-detail/', 
    #     attendance_log_reports.EmployeeMonthlyDetailReportView.as_view(), 
    #     name='employee_monthly_detail_report'),

    # # Payroll Summary Report
    # path('log-reports/payroll-summary/', 
    #     attendance_log_reports.EmployeePayrollSummaryReportView.as_view(), 
    #     name='payroll_summary_report'),

    # # Export Reports
    # path('log-reports/export/', 
    #     attendance_log_reports.ExportAttendanceReportView.as_view(), 
    #     name='export_attendance_report'),
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
# # ==================== PAYROLL MANAGEMENT URLS ====================

# # Payroll Dashboard
# path('payroll/', payroll_views.PayrollDashboardView.as_view(), name='payroll_dashboard'),

# # ==================== PAYROLL CYCLE URLS ====================
# # List, Create, Detail, Update, Delete
# path('payroll/cycles/', payroll_views.PayrollCycleListView.as_view(), name='payroll_cycle_list'),
# path('payroll/cycles/create/', payroll_views.PayrollCycleCreateView.as_view(), name='payroll_cycle_create'),
# path('payroll/cycles/<int:pk>/', payroll_views.PayrollCycleDetailView.as_view(), name='payroll_cycle_detail'),
# path('payroll/cycles/<int:pk>/update/', payroll_views.PayrollCycleUpdateView.as_view(), name='payroll_cycle_update'),
# path('payroll/cycles/<int:pk>/delete/', payroll_views.PayrollCycleDeleteView.as_view(), name='payroll_cycle_delete'),

# # Cycle Actions
# path('payroll/cycles/<int:cycle_id>/approve/', payroll_views.payroll_cycle_approve, name='payroll_cycle_approve'),
# path('payroll/cycles/<int:cycle_id>/export/', payroll_views.payroll_export_csv, name='payroll_export_csv'),
# path('payroll/cycles/<int:cycle_id>/export-bank/', payroll_views.payroll_export_bank_format, name='payroll_export_bank'),
# path('payroll/cycles/<int:cycle_id>/validate/', payroll_advanced_views.payroll_validate_cycle, name='payroll_validate_cycle'),

# # ==================== PAYROLL RECORD URLS ====================
# path('payroll/records/<int:pk>/', payroll_views.PayrollRecordDetailView.as_view(), name='payroll_record_detail'),
# path('payroll/records/<int:pk>/update/', payroll_views.PayrollRecordUpdateView.as_view(), name='payroll_record_update'),

# # Record Payment Actions
# path('payroll/records/<int:record_id>/mark-paid/', payroll_views.payroll_mark_paid, name='payroll_mark_paid'),
# path('payroll/records/bulk-mark-paid/', payroll_views.payroll_bulk_mark_paid, name='payroll_bulk_mark_paid'),

# # Salary Slip
# path('payroll/records/<int:record_id>/salary-slip/', payroll_advanced_views.PayrollSalarySlipView.as_view(), name='payroll_salary_slip'),
# path('payroll/records/<int:record_id>/send-email/', payroll_advanced_views.payroll_send_salary_slip_email, name='payroll_send_salary_slip'),
# path('payroll/salary-slips/bulk-generate/', payroll_advanced_views.BulkSalarySlipGenerateView.as_view(), name='payroll_bulk_salary_slips'),
# path('payroll/salary-slips/bulk-send/', payroll_advanced_views.payroll_bulk_send_salary_slips, name='payroll_bulk_send_slips'),

# # ==================== PAYROLL TEMPLATE URLS ====================
# path('payroll/templates/', payroll_views.PayrollTemplateListView.as_view(), name='payroll_template_list'),
# path('payroll/templates/create/', payroll_views.PayrollTemplateCreateView.as_view(), name='payroll_template_create'),
# path('payroll/templates/<int:pk>/update/', payroll_views.PayrollTemplateUpdateView.as_view(), name='payroll_template_update'),
# path('payroll/templates/<int:pk>/delete/', payroll_views.PayrollTemplateDeleteView.as_view(), name='payroll_template_delete'),

# # ==================== PAYROLL ADJUSTMENT URLS ====================
# path('payroll/adjustments/add/<int:record_id>/', payroll_views.payroll_add_adjustment, name='payroll_add_adjustment'),
# path('payroll/adjustments/<int:adjustment_id>/delete/', payroll_views.payroll_delete_adjustment, name='payroll_delete_adjustment'),

# # ==================== PAYROLL PAYMENT URLS ====================
# path('payroll/payments/', payroll_views.PayrollPaymentListView.as_view(), name='payroll_payment_list'),

# # ==================== PAYROLL GENERATION URLS ====================
# path('payroll/preview/', payroll_views.payroll_preview, name='payroll_preview'),
# path('payroll/generate/', payroll_views.payroll_generate_records, name='payroll_generate_records'),

# # ==================== PAYROLL REPORTS & ANALYTICS URLS ====================
# path('payroll/reports/', payroll_views.PayrollReportsView.as_view(), name='payroll_reports'),
# path('payroll/comparison/', payroll_advanced_views.PayrollComparisonView.as_view(), name='payroll_comparison'),
# path('payroll/budget/', payroll_advanced_views.PayrollBudgetView.as_view(), name='payroll_budget'),
# path('payroll/audit-log/', payroll_advanced_views.PayrollAuditLogView.as_view(), name='payroll_audit_log'),

# # ==================== EMPLOYEE PAYROLL HISTORY ====================
# path('payroll/employee/<int:employee_id>/history/', payroll_advanced_views.EmployeePayrollHistoryView.as_view(), name='employee_payroll_history'),

# # ==================== PAYROLL CALCULATION APIS ====================
# path('api/payroll/calculate-tax/', payroll_advanced_views.payroll_calculate_tax, name='payroll_calculate_tax'),
# path('api/payroll/calculate-pf/', payroll_advanced_views.payroll_calculate_provident_fund, name='payroll_calculate_pf'),
# path('api/payroll/calculate-bonus/', payroll_advanced_views.payroll_calculate_bonus, name='payroll_calculate_bonus'),
# path('api/payroll/statistics/', payroll_advanced_views.payroll_get_statistics, name='payroll_get_statistics'),



    # ==================== PAYROLL MANAGEMENT ====================
    path('payroll/', payroll_generation_views.payroll_generation_dashboard, name='payroll_dashboard'),
    path('payroll/preview/', payroll_generation_views.payroll_preview, name='payroll_preview'),
    path('payroll/generate/', payroll_generation_views.payroll_generate_records, name='payroll_generate_records'),
    
    # Payroll Cycles
    path('payroll/cycles/', payroll_generation_views.payroll_cycle_list, name='payroll_cycle_list'),
    path('payroll/cycles/<int:cycle_id>/', payroll_generation_views.payroll_cycle_detail, name='payroll_cycle_detail'),
    path('payroll/cycles/<int:cycle_id>/export/', payroll_generation_views.payroll_export_csv, name='payroll_export_csv'),
    
    # Payroll Record Management
    path('payroll/records/<int:record_id>/mark-paid/', payroll_generation_views.payroll_mark_paid, name='payroll_mark_paid'),

]