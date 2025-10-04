from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum, Avg, Min, Max, F, ExpressionWrapper, fields
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.core.paginator import Paginator
from decimal import Decimal
import csv

from ..models import Attendance, Employee, Department, Shift, Holiday, LeaveApplication
from core.models import Company

import logging
logger = logging.getLogger(__name__)


class AttendanceListView(LoginRequiredMixin, ListView):
    """
    Enhanced Attendance List View with advanced filtering, search, and export
    """
    model = Attendance
    template_name = 'zkteco/attendance_list.html'
    context_object_name = 'attendances'
    paginate_by = 50
    
    def get_company(self):
        """Get company from request - modify based on your auth system"""
        try:
            return Company.objects.first()
        except Exception as e:
            logger.error(f"Error getting company: {str(e)}")
            return None
    
    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Attendance.objects.none()
        
        queryset = Attendance.objects.filter(
            employee__company=company
        ).select_related(
            'employee', 
            'employee__department', 
            'employee__designation',
            'shift'
        ).order_by('-date', 'employee__name')
        
        # Apply filters
        queryset = self.apply_filters(queryset)
        
        return queryset
    
    def apply_filters(self, queryset):
        """Apply all filters from GET parameters"""
        # Date filters
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        date_range = self.request.GET.get('date_range')
        
        # Handle predefined date ranges
        today = timezone.now().date()
        if date_range:
            if date_range == 'today':
                start_date = end_date = today.isoformat()
            elif date_range == 'yesterday':
                yesterday = today - timedelta(days=1)
                start_date = end_date = yesterday.isoformat()
            elif date_range == 'this_week':
                start_of_week = today - timedelta(days=today.weekday())
                start_date = start_of_week.isoformat()
                end_date = today.isoformat()
            elif date_range == 'last_week':
                start_of_last_week = today - timedelta(days=today.weekday() + 7)
                end_of_last_week = start_of_last_week + timedelta(days=6)
                start_date = start_of_last_week.isoformat()
                end_date = end_of_last_week.isoformat()
            elif date_range == 'this_month':
                start_date = today.replace(day=1).isoformat()
                end_date = today.isoformat()
            elif date_range == 'last_month':
                first_day_this_month = today.replace(day=1)
                last_day_last_month = first_day_this_month - timedelta(days=1)
                first_day_last_month = last_day_last_month.replace(day=1)
                start_date = first_day_last_month.isoformat()
                end_date = last_day_last_month.isoformat()
        
        if start_date:
            try:
                queryset = queryset.filter(date__gte=datetime.strptime(start_date, '%Y-%m-%d').date())
            except ValueError:
                pass
        
        if end_date:
            try:
                queryset = queryset.filter(date__lte=datetime.strptime(end_date, '%Y-%m-%d').date())
            except ValueError:
                pass
        
        # Employee filter
        employee_id = self.request.GET.get('employee')
        if employee_id and employee_id.isdigit():
            queryset = queryset.filter(employee_id=int(employee_id))
        
        # Department filter
        department_id = self.request.GET.get('department')
        if department_id and department_id.isdigit():
            queryset = queryset.filter(employee__department_id=int(department_id))
        
        # Shift filter
        shift_id = self.request.GET.get('shift')
        if shift_id and shift_id.isdigit():
            queryset = queryset.filter(shift_id=int(shift_id))
        
        # Status filter
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Overtime filter
        overtime_filter = self.request.GET.get('overtime')
        if overtime_filter == 'yes':
            queryset = queryset.filter(overtime_hours__gt=0)
        elif overtime_filter == 'no':
            queryset = queryset.filter(overtime_hours=0)
        
        # Search filter
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(employee__name__icontains=search) |
                Q(employee__employee_id__icontains=search) |
                Q(employee__department__name__icontains=search)
            )
        
        return queryset
    
    def get_report_name(self):
        """Generate dynamic report name based on filters"""
        filters = []
        
        # Date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        date_range = self.request.GET.get('date_range')
        
        if date_range:
            date_labels = {
                'today': "Today's",
                'yesterday': "Yesterday's",
                'this_week': "This Week's",
                'last_week': "Last Week's",
                'this_month': "This Month's",
                'last_month': "Last Month's"
            }
            filters.append(date_labels.get(date_range, ''))
        elif start_date and end_date:
            filters.append(f"{start_date} to {end_date}")
        elif start_date:
            filters.append(f"From {start_date}")
        elif end_date:
            filters.append(f"Until {end_date}")
        
        # Department
        department_id = self.request.GET.get('department')
        if department_id and department_id.isdigit():
            try:
                dept = Department.objects.get(id=int(department_id))
                filters.append(f"{dept.name} Department")
            except Department.DoesNotExist:
                pass
        
        # Employee
        employee_id = self.request.GET.get('employee')
        if employee_id and employee_id.isdigit():
            try:
                emp = Employee.objects.get(id=int(employee_id))
                filters.append(f"{emp.name}")
            except Employee.DoesNotExist:
                pass
        
        # Status
        status = self.request.GET.get('status')
        if status:
            status_labels = {
                'P': 'Present',
                'A': 'Absent',
                'L': 'Leave',
                'H': 'Holiday',
                'W': 'Weekly Off'
            }
            filters.append(f"{status_labels.get(status, '')} Records")
        
        # Shift
        shift_id = self.request.GET.get('shift')
        if shift_id and shift_id.isdigit():
            try:
                shift = Shift.objects.get(id=int(shift_id))
                filters.append(f"{shift.name} Shift")
            except Shift.DoesNotExist:
                pass
        
        if filters:
            return " - ".join(filters) + " Attendance Report"
        else:
            return "Attendance Report"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.get_company()
        
        # Get filter options
        context['employees'] = Employee.objects.filter(
            company=company, is_active=True
        ).order_by('name')
        
        context['departments'] = Department.objects.filter(
            company=company
        ).order_by('name')
        
        context['shifts'] = Shift.objects.filter(
            company=company
        ).order_by('name')
        
        # Statistics
        queryset = self.get_queryset()
        context['total_records'] = queryset.count()
        
        stats = queryset.aggregate(
            total_present=Count('id', filter=Q(status='P')),
            total_absent=Count('id', filter=Q(status='A')),
            total_leave=Count('id', filter=Q(status='L')),
            total_holiday=Count('id', filter=Q(status='H')),
            total_overtime_hours=Sum('overtime_hours'),
        )
        
        # Calculate work hours from check_in and check_out times
        total_work_hours = 0
        for att in queryset:
            if att.check_in_time and att.check_out_time:
                delta = att.check_out_time - att.check_in_time
                total_work_hours += delta.total_seconds() / 3600
        
        stats['total_work_hours'] = round(total_work_hours, 2)
        stats['avg_work_hours'] = round(total_work_hours / queryset.count(), 2) if queryset.count() > 0 else 0
        
        context['stats'] = stats
        
        # Date range stats
        context['date_stats'] = queryset.aggregate(
            earliest=Min('date'),
            latest=Max('date')
        )
        
        # Current filter values
        context['current_filters'] = {
            'employee': self.request.GET.get('employee', ''),
            'department': self.request.GET.get('department', ''),
            'shift': self.request.GET.get('shift', ''),
            'status': self.request.GET.get('status', ''),
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'date_range': self.request.GET.get('date_range', ''),
            'search': self.request.GET.get('search', ''),
            'overtime': self.request.GET.get('overtime', ''),
        }
        
        context['company'] = company
        context['report_name'] = self.get_report_name()
        
        # Status choices
        context['status_choices'] = [
            ('P', 'Present'),
            ('A', 'Absent'),
            ('L', 'Leave'),
            ('H', 'Holiday'),
            ('W', 'Weekly Off'),
        ]
        
        return context


class AttendanceDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view of a single attendance record
    """
    model = Attendance
    template_name = 'zkteco/attendance_detail.html'
    context_object_name = 'attendance'
    
    def get_queryset(self):
        company = Company.objects.first()
        return Attendance.objects.filter(
            employee__company=company
        ).select_related(
            'employee',
            'employee__department',
            'employee__designation',
            'shift'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        attendance = self.object
        
        # Get related attendance records (same employee, nearby dates)
        context['nearby_records'] = Attendance.objects.filter(
            employee=attendance.employee,
            date__gte=attendance.date - timedelta(days=7),
            date__lte=attendance.date + timedelta(days=7)
        ).exclude(id=attendance.id).order_by('-date')[:10]
        
        # Get employee's monthly stats
        month_start = attendance.date.replace(day=1)
        if attendance.date.month == 12:
            month_end = attendance.date.replace(year=attendance.date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = attendance.date.replace(month=attendance.date.month + 1, day=1) - timedelta(days=1)
        
        monthly_records = Attendance.objects.filter(
            employee=attendance.employee,
            date__gte=month_start,
            date__lte=month_end
        )
        
        monthly_stats = monthly_records.aggregate(
            total_days=Count('id'),
            present_days=Count('id', filter=Q(status='P')),
            absent_days=Count('id', filter=Q(status='A')),
            leave_days=Count('id', filter=Q(status='L')),
            total_overtime=Sum('overtime_hours'),
        )
        
        # Calculate total work hours manually
        total_work_hours = 0
        for rec in monthly_records:
            if rec.check_in_time and rec.check_out_time:
                delta = rec.check_out_time - rec.check_in_time
                total_work_hours += delta.total_seconds() / 3600
        
        monthly_stats['total_work_hours'] = round(total_work_hours, 2)
        
        context['monthly_stats'] = monthly_stats
        
        return context


class AttendanceCreateView(LoginRequiredMixin, CreateView):
    """
    Create new attendance record
    """
    model = Attendance
    template_name = 'zkteco/attendance_form.html'
    # <CHANGE> Only use fields that exist in the Attendance model
    fields = [
        'employee', 'date', 'shift', 'check_in_time', 'check_out_time',
        'status', 'overtime_hours'
    ]
    success_url = reverse_lazy('zkteco:attendance_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Attendance Record'
        context['button_text'] = 'Create Record'
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Attendance record created successfully!')
        return super().form_valid(form)


class AttendanceUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update existing attendance record
    """
    model = Attendance
    template_name = 'zkteco/attendance_form.html'
    # <CHANGE> Fixed FieldError - only use fields that exist in Attendance model
    fields = [
        'employee', 'date', 'shift', 'check_in_time', 'check_out_time',
        'status', 'overtime_hours'
    ]
    success_url = reverse_lazy('zkteco:attendance_list')
    
    def get_queryset(self):
        company = Company.objects.first()
        return Attendance.objects.filter(employee__company=company)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Attendance Record'
        context['button_text'] = 'Update Record'
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Attendance record updated successfully!')
        return super().form_valid(form)


class AttendanceDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete attendance record with confirmation
    """
    model = Attendance
    template_name = 'zkteco/attendance_confirm_delete.html'
    success_url = reverse_lazy('zkteco:attendance_list')
    
    def get_queryset(self):
        company = Company.objects.first()
        return Attendance.objects.filter(employee__company=company)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Attendance record deleted successfully!')
        return super().delete(request, *args, **kwargs)


class AttendanceExportCSVView(LoginRequiredMixin, ListView):
    """
    Export attendance records to CSV
    """
    model = Attendance
    
    def get_queryset(self):
        company = Company.objects.first()
        queryset = Attendance.objects.filter(
            employee__company=company
        ).select_related('employee', 'employee__department', 'shift')
        
        # Apply filters
        view = AttendanceListView()
        view.request = self.request
        return view.apply_filters(queryset)
    
    def render_to_response(self, context):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        
        writer.writerow([
            'Employee ID', 'Employee Name', 'Department', 'Date', 'Day',
            'Shift', 'Check In', 'Check Out', 'Status',
            'Work Hours', 'Overtime Hours'
        ])
        
        # Write data
        for attendance in self.get_queryset():
            writer.writerow([
                attendance.employee.employee_id,
                attendance.employee.name,
                attendance.employee.department.name if attendance.employee.department else '',
                attendance.date.strftime('%Y-%m-%d'),
                attendance.date.strftime('%A'),
                attendance.shift.name if attendance.shift else '',
                attendance.check_in_time.strftime('%H:%M:%S') if attendance.check_in_time else '',
                attendance.check_out_time.strftime('%H:%M:%S') if attendance.check_out_time else '',
                attendance.get_status_display(),
                attendance.work_hours,
                float(attendance.overtime_hours) if attendance.overtime_hours else 0,
            ])
        
        return response
