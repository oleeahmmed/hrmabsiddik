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

                                    {
                        "title": _("My Custom Page"),
                        "icon": "rocket_launch",  # or "dashboard", "analytics", "speed"
                        "link": reverse_lazy("admin:custom-page"),
                        "permission": lambda request: request.user.is_staff,
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
                    "title": _("User Profiles"),
                    "icon": "account_circle",
                    "link": admin_changelist("core", "userprofile"),
                    "permission": lambda request: request.user.has_perm("core.view_userprofile"),
                },
                {
                    "title": _("Companies"),
                    "icon": "business",
                    "link": admin_changelist("core", "company"),
                    "permission": lambda request: request.user.has_perm("core.view_company"),
                },

                {
                    "title": _("Projects"),
                    "icon": "folder_special",
                    "link": admin_changelist("core", "project"),
                    "permission": lambda request: request.user.has_perm("core.view_project"),
                },
                {
                    "title": _("Tasks"),
                    "icon": "task",
                    "link": admin_changelist("core", "task"),
                    "permission": lambda request: request.user.has_perm("core.view_task"),
                },

                {
                    "title": _("Task Comments"),
                    "icon": "comment",
                    "link": admin_changelist("core", "taskcomment"),
                    "permission": lambda request: request.user.has_perm("core.view_taskcomment"),
                },
                {
                    "title": _("📊 Project Dashboard"),
                    "icon": "dashboard",
                    "link": "/core/project-reports/dashboard/",  # 🔥 CHANGE
                    "permission": lambda request: request.user.is_authenticated,
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
            "title": _("Employee Documents"),
            "icon": "folder_shared",
            "link": admin_changelist("hr_payroll", "employeedocument"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_employeedocument"),
        },
        {
            "title": _("Overtime Requests"),
            "icon": "access_time",
            "link": admin_changelist("hr_payroll", "overtime"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_overtime"),
        },
        {
            "title": _("Resignations"),
            "icon": "logout",
            "link": admin_changelist("hr_payroll", "resignation"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_resignation"),
        },
        {
            "title": _("Clearances"),
            "icon": "verified",
            "link": admin_changelist("hr_payroll", "clearance"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_clearance"),
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
{
    "title": _("Employee Management"),
    "separator": True,
    "collapsible": True,
    "items": [
        {
            "title": _("Notices"),
            "icon": "campaign",
            "link": admin_changelist("hr_payroll", "notice"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_notice"),
        },
        {
            "title": _("Recruitments"),
            "icon": "work_outline",
            "link": admin_changelist("hr_payroll", "recruitment"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_recruitment"),
        },
        {
            "title": _("Job Applications"),
            "icon": "description",
            "link": admin_changelist("hr_payroll", "jobapplication"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_jobapplication"),
        },
        {
            "title": _("Trainings"),
            "icon": "school",
            "link": admin_changelist("hr_payroll", "training"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_training"),
        },
        {
            "title": _("Training Enrollments"),
            "icon": "how_to_reg",
            "link": admin_changelist("hr_payroll", "trainingenrollment"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_trainingenrollment"),
        },
        {
            "title": _("Performance Reviews"),
            "icon": "assessment",
            "link": admin_changelist("hr_payroll", "performance"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_performance"),
        },
        {
            "title": _("Performance Goals"),
            "icon": "track_changes",
            "link": admin_changelist("hr_payroll", "performancegoal"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_performancegoal"),
        },

        {
            "title": _("Complaints"),
            "icon": "report_problem",
            "link": admin_changelist("hr_payroll", "complaint"),
            "permission": lambda request: request.user.has_perm("hr_payroll.view_complaint"),
        },
    ],
},


{
    "title": _("Payroll Management"),
    "separator": True,
    "collapsible": True,
    "items": [
        {
            "title": _("Salary Components"),
            "icon": "account_balance_wallet",
            "link": admin_changelist("payroll", "salarycomponent"),
            "permission": lambda request: request.user.has_perm("payroll.view_salarycomponent"),
        },
        {
            "title": _("Salary Structures"),
            "icon": "receipt_long",
            "link": admin_changelist("payroll", "employeesalarystructure"),
            "permission": lambda request: request.user.has_perm("payroll.view_employeesalarystructure"),
        },
        {
            "title": _("Salary Months"),
            "icon": "calendar_month",
            "link": admin_changelist("payroll", "salarymonth"),
            "permission": lambda request: request.user.has_perm("payroll.view_salarymonth"),
        },
        {
            "title": _("Employee Salaries"),
            "icon": "payments",
            "link": admin_changelist("payroll", "employeesalary"),
            "permission": lambda request: request.user.has_perm("payroll.view_employeesalary"),
        },
        {
            "title": _("Bonuses"),
            "icon": "celebration",
            "link": admin_changelist("payroll", "bonus"),
            "permission": lambda request: request.user.has_perm("payroll.view_bonus"),
        },
        {
            "title": _("Employee Advances"),
            "icon": "request_quote",
            "link": admin_changelist("payroll", "employeeadvance"),
            "permission": lambda request: request.user.has_perm("payroll.view_employeeadvance"),
        },
    ],
},

    ]


UNFOLD = {
    "SITE_TITLE": "Ezydream Hrm",
    "SITE_HEADER": "Ezydream Hrm",
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