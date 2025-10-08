from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy
from django.utils.functional import lazy
from django.conf import settings
# Optional helper (উপরে রেখে দিন)
from django.urls import reverse_lazy

def admin_changelist(app_label, model_name):
    return reverse_lazy(f"admin:{app_label}_{model_name}_changelist")

static_lazy = lazy(static, str)

def get_navigation_for_user(request):
    """Return navigation for sidebar"""
    return [
        {
            "title": _("Data And Analytics"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Dashboard"),
                    "icon": "dashboard",
                    "link": "/admin/",
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
        {
            "title": _("Authentication"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Users"),
                    "icon": "people",
                    "link": "/admin/auth/user/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Groups"),
                    "icon": "group",
                    "link": "/admin/auth/group/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Permissions"),
                    "icon": "lock",
                    "link": "/admin/auth/permission/",
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
        {
            "title": _("Core Management"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Companies"),
                    "icon": "business",
                    "link": "/admin/core/company/",
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
        {
            "title": _("HR & Payroll"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Departments"),
                    "icon": "corporate_fare",
                    "link": "/admin/hr_payroll/department/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Designations"),
                    "icon": "work",
                    "link": "/admin/hr_payroll/designation/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Employees"),
                    "icon": "people",
                    "link": "/admin/hr_payroll/employee/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Employee Separations"),
                    "icon": "exit_to_app",
                    "link": "/admin/hr_payroll/employeeseparation/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Shifts"),
                    "icon": "event",
                    "link": "/admin/hr_payroll/shift/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Rosters"),
                    "icon": "calendar_today",
                    "link": "/admin/hr_payroll/roster/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Roster Assignments"),
                    "icon": "assignment_ind",
                    "link": "/admin/hr_payroll/rosterassignment/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Holidays"),
                    "icon": "event_available",
                    "link": "/admin/hr_payroll/holiday/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Leave Types"),
                    "icon": "beach_access",
                    "link": "/admin/hr_payroll/leavetype/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Leave Balances"),
                    "icon": "account_balance",
                    "link": "/admin/hr_payroll/leavebalance/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Leave Applications"),
                    "icon": "request_page",
                    "link": "/admin/hr_payroll/leaveapplication/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("ZK Devices"),
                    "icon": "devices",
                    "link": "/admin/hr_payroll/zkdevice/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Attendance Logs"),
                    "icon": "fingerprint",
                    "link": "/admin/hr_payroll/attendancelog/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Attendance"),
                    "icon": "check_circle",
                    "link": "/admin/hr_payroll/attendance/",
                    "permission": lambda request: request.user.is_superuser,
                },
                # NEW: Attendance Configuration
                {
                    "title": _("Attendance Configuration"),
                    "icon": "settings",
                    "link": "/admin/hr_payroll/attendanceprocessorconfiguration/",
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
        {
            "title": _("Location Management"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Locations"),
                    "icon": "location_on",
                    "link": "/admin/hr_payroll/location/",
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("User Locations"),
                    "icon": "person_pin_circle",
                    "link": "/admin/hr_payroll/userlocation/",
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },

{
    "title": _("Mobile Attendance"),
    "separator": True,
    "collapsible": True,
    "items": [
        {
            "title": _("Mobile Dashboard"),
            "icon": "smartphone",
            "link": "/admin/hr_payroll/attendancelog/mobile-attendance/",
            "permission": lambda request: request.user.is_authenticated,
        },
        {
            "title": _("Attendance Logs"),
            "icon": "list_alt",
            "link": "/admin/hr_payroll/attendancelog/",
            "permission": lambda request: request.user.is_superuser,
        },
        {
            "title": _("Locations"),
            "icon": "location_on",
            "link": "/admin/hr_payroll/location/",
            "permission": lambda request: request.user.is_superuser,
        },
        {
            "title": _("User Locations"),
            "icon": "person_pin_circle",
            "link": "/admin/hr_payroll/userlocation/",
            "permission": lambda request: request.user.is_superuser,
        },
    ],
},

# ---- Add this block inside the returned list from get_navigation_for_user ----
{
    "title": _("Payroll"),
    "separator": True,
    "collapsible": True,
    "items": [
        {
            "title": _("Payroll Templates"),
            "icon": "rule",
            "link": admin_changelist("hr_payroll", "payrolltemplate"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_payrolltemplate"),
        },
        {
            "title": _("Payroll Cycles"),
            "icon": "schedule",
            "link": admin_changelist("hr_payroll", "payrollcycle"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_payrollcycle"),
        },
        {
            "title": _("Payroll Records"),
            "icon": "receipt_long",
            "link": admin_changelist("hr_payroll", "payrollrecord"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_payrollrecord"),
        },
        {
            "title": _("Adjustments"),
            "icon": "tune",
            "link": admin_changelist("hr_payroll", "payrolladjustment"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_payrolladjustment"),
        },
        {
            "title": _("Payments"),
            "icon": "payments",
            "link": admin_changelist("hr_payroll", "payrollpayment"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_payrollpayment"),
        },
    ],
}

    ]


UNFOLD = {
    "SITE_TITLE": "Kreatech ERP",
    "SITE_HEADER": "Kreatech ERP",
    "SITE_LOGO": static_lazy("images/logo/logo.svg"),
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "ENVIRONMENT": "config.settings.unfold_admin.environment_callback",
    "LOGIN": {
        "image": static_lazy("images/login-bg.jpg"),
        "redirect_after": lambda request: "/",
    },
    "COLORS": {
        "primary": {
            "50": "oklch(0.97 0.013 240)",
            "100": "oklch(0.93 0.024 240)",
            "200": "oklch(0.86 0.055 240)",
            "300": "oklch(0.78 0.108 240)",
            "400": "oklch(0.69 0.155 240)",
            "500": "oklch(0.58 0.191 240)",
            "600": "oklch(0.49 0.204 240)",
            "700": "oklch(0.42 0.195 240)",
            "800": "oklch(0.35 0.155 240)",
            "900": "oklch(0.28 0.108 240)",
        },
        "secondary": {
            "50": "oklch(0.98 0.003 240)",
            "100": "oklch(0.96 0.006 240)",
            "200": "oklch(0.90 0.011 240)",
            "300": "oklch(0.83 0.017 240)",
            "400": "oklch(0.64 0.015 240)",
            "500": "oklch(0.49 0.013 240)",
            "600": "oklch(0.37 0.013 240)",
            "700": "oklch(0.28 0.013 240)",
            "800": "oklch(0.19 0.013 240)",
            "900": "oklch(0.13 0.013 240)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": get_navigation_for_user,
    },
    "THEME": "light",
}


def environment_callback(request):
    """Show environment indicator"""
    return ["Development", "success"] if settings.DEBUG else ["Production", "danger"]