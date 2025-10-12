from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Min, Max, Avg, Sum
from django.utils import timezone
from django.urls import reverse, reverse_lazy
from datetime import datetime, date, timedelta
from django.utils.dateparse import parse_date, parse_datetime
from django.core.cache import cache
from django.conf import settings

import json
import logging
import csv
import threading
from collections import defaultdict
from decimal import Decimal

from ..models import ZkDevice, AttendanceLog, Employee, Attendance, Shift, Department, Designation, Holiday, LeaveApplication,LeaveBalance
from ..zkteco_device_manager import ZKTecoDeviceManager
from core.models import Company
from ..forms import ZkDeviceForm
logger = logging.getLogger(__name__)
class CompanyAccessMixin:
    """Mixin to provide company access in class-based views"""
    
    def get_company(self):
        """Get company for the current user"""
        try:
            company = Company.objects.first()
            if company:
                return company
            return None
        except Exception as e:
            logger.error(f"Error getting company: {str(e)}")
            return None
    
    def dispatch(self, request, *args, **kwargs):
        """Check company access before processing request"""
        self.company = self.get_company()
        if not self.company and not self.bypass_company_check():
            messages.error(request, "No company access found.")
            return redirect('zkteco:login')
        return super().dispatch(request, *args, **kwargs)
    
    def bypass_company_check(self):
        """Override in subclasses to bypass company check for specific views"""
        return False
    
    def get_context_data(self, **kwargs):
        """Add company to context"""
        context = super().get_context_data(**kwargs)
        context['company'] = self.company
        return context


# ==================== AUTH VIEWS ====================

class LoginView(View):
    """Custom login view"""
    template_name = 'auth/login.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('zkteco:home')
        return render(request, self.template_name)
    
    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                next_url = request.GET.get('next', 'zkteco:home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please provide both username and password.')
        
        return render(request, self.template_name)


class LogoutView(LoginRequiredMixin, View):
    """Custom logout view"""
    
    def get(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('zkteco:login')
    
    def post(self, request):
        return self.get(request)


# ==================== STAFF HOME DASHBOARD ====================


class StaffHomeDashboardView(LoginRequiredMixin, PermissionRequiredMixin, CompanyAccessMixin, TemplateView):
    """Staff dashboard with comprehensive statistics and management features"""
    template_name = 'auth/staff_dashboard.html'
    permission_required = 'zkteco.view_attendance'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.company
        today = timezone.now().date()
        
        # Get comprehensive statistics for staff
        total_devices = ZkDevice.objects.filter(company=company).count()
        active_devices = ZkDevice.objects.filter(company=company, is_active=True).count()
        inactive_devices = total_devices - active_devices
        
        active_employees = Employee.objects.filter(company=company, is_active=True)
        total_employees = active_employees.count()
        
        # Today's detailed attendance calculation
        employees_on_leave_today = LeaveApplication.objects.filter(
            employee__company=company,
            status='A',
            start_date__lte=today,
            end_date__gte=today
        ).select_related('employee', 'leave_type')
        
        employees_with_logs_today = AttendanceLog.objects.filter(
            employee__company=company,
            timestamp__date=today
        ).values('employee_id').annotate(first_in=Min('timestamp'), last_out=Max('timestamp'))
        
        # Create sets for faster lookups
        leave_employee_ids = set(leave.employee_id for leave in employees_on_leave_today)
        present_employee_ids = set(log['employee_id'] for log in employees_with_logs_today)
        
        # Get detailed lists
        today_leave_list = employees_on_leave_today
        
        today_present_list = []
        for log in employees_with_logs_today:
            try:
                employee = active_employees.get(id=log['employee_id'])
                today_present_list.append({
                    'employee': employee,
                    'first_check_in': log['first_in'],
                    'last_check_out': log['last_out']
                })
            except Employee.DoesNotExist:
                continue
        
        # Absent employees (not present and not on leave)
        absent_employee_ids = set(active_employees.values_list('id', flat=True)) - present_employee_ids - leave_employee_ids
        today_absent_list = active_employees.filter(id__in=absent_employee_ids)
        
        # Counts
        today_present = len(present_employee_ids)
        today_leave = len(leave_employee_ids)
        today_absent = len(absent_employee_ids)
        
        attendance_rate = round((today_present / total_employees * 100) if total_employees > 0 else 0, 1)
        
        # Today's late comers (enhanced)
        todays_late_comers = []
        for log_data in employees_with_logs_today:
            try:
                employee = active_employees.select_related('default_shift').get(id=log_data['employee_id'])
                if employee.default_shift and log_data['first_in']:
                    shift_start_time = employee.default_shift.start_time
                    grace_minutes = employee.default_shift.grace_time or 0
                    
                    shift_start_datetime = timezone.make_aware(datetime.combine(today, shift_start_time))
                    grace_deadline = shift_start_datetime + timedelta(minutes=grace_minutes)
                    
                    if log_data['first_in'] > grace_deadline:
                        late_minutes = (log_data['first_in'] - grace_deadline).total_seconds() / 60
                        todays_late_comers.append({
                            'employee': employee,
                            'check_in': log_data['first_in'],
                            'shift_start': shift_start_time,
                            'late_minutes': int(late_minutes)
                        })
            except Employee.DoesNotExist:
                continue

        # Today's early leavers (enhanced)
        todays_early_leavers = []
        for log_data in employees_with_logs_today:
            try:
                employee = active_employees.select_related('default_shift').get(id=log_data['employee_id'])
                if employee.default_shift and log_data['last_out']:
                    shift_end_time = employee.default_shift.end_time
                    shift_end_datetime = timezone.make_aware(datetime.combine(today, shift_end_time))
                    
                    if log_data['last_out'] < shift_end_datetime:
                        early_minutes = (shift_end_datetime - log_data['last_out']).total_seconds() / 60
                        todays_early_leavers.append({
                            'employee': employee,
                            'check_out': log_data['last_out'],
                            'shift_end': shift_end_time,
                            'early_minutes': int(early_minutes)
                        })
            except Employee.DoesNotExist:
                continue

        # Pending leave approvals
        pending_leaves = LeaveApplication.objects.filter(
            employee__company=company, status='P'
        ).select_related('employee', 'leave_type').order_by('created_at')[:10]

        # Monthly statistics
        monthly_leaves = LeaveApplication.objects.filter(
            employee__company=company,
            status='A',
            start_date__month=today.month,
            start_date__year=today.year
        ).count()
        
        # Upcoming holidays
        upcoming_holidays = Holiday.objects.filter(
            company=company, date__gte=today
        ).order_by('date')[:5]
        
        # Department statistics
        total_shifts = Shift.objects.filter(company=company).count()
        departments = Department.objects.filter(company=company).annotate(
            employee_count=Count('employee', filter=Q(employee__is_active=True))
        )[:6]
        
        # Weekly attendance trend
        dates, present_counts, absent_counts = [], [], []
        for i in range(6, -1, -1):
            date_obj = today - timedelta(days=i)
            dates.append(date_obj.strftime('%a'))
            
            day_present_count = AttendanceLog.objects.filter(
                employee__company=company, timestamp__date=date_obj
            ).values('employee_id').distinct().count()
            
            day_leave_count = LeaveApplication.objects.filter(
                employee__company=company, status='A', start_date__lte=date_obj, end_date__gte=date_obj
            ).values('employee_id').distinct().count()
            
            day_absent_count = total_employees - day_present_count - day_leave_count
            present_counts.append(day_present_count)
            absent_counts.append(max(0, day_absent_count))

        dept_names = [dept.name for dept in departments]
        dept_counts = [dept.employee_count for dept in departments]
        
        # Log statistics
        total_logs = AttendanceLog.objects.filter(device__company=company).count()
        today_logs = AttendanceLog.objects.filter(
            device__company=company, timestamp__date=today
        ).count()
        
        recent_logs = AttendanceLog.objects.filter(
            device__company=company
        ).select_related(
            'employee', 
            'device'
        ).prefetch_related(
            'employee__department',
            'employee__designation'
        ).order_by('-timestamp')[:10]
        
        # System health
        system_health = round((active_devices / total_devices * 100) if total_devices > 0 else 100, 0)
        
        # Last sync time
        last_device_sync = ZkDevice.objects.filter(
            company=company, last_synced__isnull=False
        ).order_by('-last_synced').first()
        
        last_sync = "Never"
        if last_device_sync and last_device_sync.last_synced:
            time_diff = timezone.now() - last_device_sync.last_synced
            seconds = time_diff.total_seconds()
            if seconds < 60: 
                last_sync = "Just now"
            elif seconds < 3600: 
                last_sync = f"{int(seconds / 60)}m ago"
            else: 
                last_sync = f"{int(seconds / 3600)}h ago"

        # Compile statistics
        stats = {
            'total_devices': total_devices,
            'active_devices': active_devices,
            'inactive_devices': inactive_devices,
            'total_employees': total_employees,
            'today_present': today_present,
            'today_absent': today_absent,
            'today_leave': today_leave,
            'attendance_rate': attendance_rate,
            'monthly_leaves': monthly_leaves,
            'total_shifts': total_shifts,
            'total_logs': total_logs,
            'today_logs': today_logs,
            'system_health': system_health,
            'last_sync': last_sync,
            'pending_leaves_count': pending_leaves.count(),
            'late_comers_count': len(todays_late_comers),
            'early_leavers_count': len(todays_early_leavers),
        }
        
        # Add all context data
        context.update({
            'stats': stats,
            'today_leave_list': today_leave_list,
            'today_present_list': today_present_list,
            'today_absent_list': today_absent_list,
            'recent_logs': recent_logs,
            'pending_leaves': pending_leaves,
            'upcoming_holidays': upcoming_holidays,
            'departments': departments,
            'today': today,
            'attendance_dates': dates,
            'present_counts': present_counts,
            'absent_counts': absent_counts,
            'dept_names': dept_names,
            'dept_counts': dept_counts,
            'todays_late_comers': todays_late_comers,
            'todays_early_leavers': todays_early_leavers,
            'is_staff': True,
        })
        
        return context

# ==================== USER HOME DASHBOARD ====================

class UserHomeDashboardView(LoginRequiredMixin, CompanyAccessMixin, TemplateView):
    """User dashboard with personalized attendance and leave information"""
    template_name = 'auth/user_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.company
        today = timezone.now().date()
        
        # Get current user's employee record
        try:
            employee = Employee.objects.get(user=self.request.user, company=company, is_active=True)
        except Employee.DoesNotExist:
            employee = None
            messages.warning(self.request, "No employee record found for your user account.")
        
        if employee:
            # Get today's attendance logs for the user
            today_logs = AttendanceLog.objects.filter(
                employee=employee,
                timestamp__date=today
            ).order_by('timestamp')
            
            # Get check-in and check-out times
            check_in = today_logs.filter(attendance_type='IN').first()
            check_out = today_logs.filter(attendance_type='OUT').last()
            
            # Calculate work hours if both check-in and check-out exist
            work_hours = 0
            if check_in and check_out:
                time_diff = check_out.timestamp - check_in.timestamp
                work_hours = round(time_diff.total_seconds() / 3600, 2)
            
            # Get user's recent attendance (last 7 days)
            recent_attendance = []
            for i in range(6, -1, -1):
                date_obj = today - timedelta(days=i)
                day_logs = AttendanceLog.objects.filter(
                    employee=employee,
                    timestamp__date=date_obj
                ).order_by('timestamp')
                
                day_check_in = day_logs.filter(attendance_type='IN').first()
                day_check_out = day_logs.filter(attendance_type='OUT').last()
                
                day_work_hours = 0
                if day_check_in and day_check_out:
                    time_diff = day_check_out.timestamp - day_check_in.timestamp
                    day_work_hours = round(time_diff.total_seconds() / 3600, 2)
                
                # Check if it's a weekend
                is_weekend = date_obj.weekday() in [5, 6]  # 5=Saturday, 6=Sunday
                
                # Check if it's a holiday
                is_holiday = Holiday.objects.filter(company=company, date=date_obj).exists()
                
                status = 'Present' if day_logs.exists() else 'Absent'
                if is_holiday:
                    status = 'Holiday'
                elif is_weekend:
                    status = 'Weekend'
                
                recent_attendance.append({
                    'date': date_obj,
                    'check_in': day_check_in.timestamp if day_check_in else None,
                    'check_out': day_check_out.timestamp if day_check_out else None,
                    'work_hours': day_work_hours,
                    'status': status,
                    'is_weekend': is_weekend,
                    'is_holiday': is_holiday
                })
            
            # Get user's leave information
            leave_applications = LeaveApplication.objects.filter(
                employee=employee
            ).select_related('leave_type').order_by('-created_at')[:5]
            
            # Get leave balances
            leave_balances = LeaveBalance.objects.filter(employee=employee).select_related('leave_type')
            
            # Get upcoming holidays
            upcoming_holidays = Holiday.objects.filter(
                company=company, date__gte=today
            ).order_by('date')[:5]
            
            # Get user's shift information
            user_shift = employee.default_shift
            shift_info = None
            if user_shift:
                shift_info = {
                    'name': user_shift.name,
                    'start_time': user_shift.start_time,
                    'end_time': user_shift.end_time,
                    'break_time': user_shift.break_time
                }
            
            context.update({
                'employee': employee,
                'today_check_in': check_in,
                'today_check_out': check_out,
                'today_work_hours': work_hours,
                'recent_attendance': recent_attendance,
                'leave_applications': leave_applications,
                'leave_balances': leave_balances,
                'upcoming_holidays': upcoming_holidays,
                'shift_info': shift_info,
                'today': today,
            })
        else:
            context.update({
                'employee': None,
                'recent_attendance': [],
                'leave_applications': [],
                'leave_balances': [],
                'upcoming_holidays': [],
            })
        
        context.update({
            'is_staff': False,
        })
        
        return context


# ==================== HOME VIEW DISPATCHER ====================

class HomeView(LoginRequiredMixin, View):
    """Dispatcher view that redirects to appropriate dashboard based on user role"""
    
    def get(self, request):
        if request.user.is_staff or request.user.has_perm('zkteco.view_attendance'):
            return redirect('zkteco:staff_home')
        else:
            return redirect('zkteco:user_home')