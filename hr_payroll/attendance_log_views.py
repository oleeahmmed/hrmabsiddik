# attendance_log_views.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django import forms
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
import json
import logging
from datetime import datetime

from .models import AttendanceLog, Employee, ZkDevice, Location
from .zkteco_device_manager import ZKTecoDeviceManager
from core.models import Company

logger = logging.getLogger(__name__)

# Add CompanyAccessMixin
class CompanyAccessMixin:
    """Mixin to provide company access in class-based views"""
    
    def get_company(self):
        """Get company for the current user"""
        try:
            # Try to get company from user's employee record
            employee = Employee.objects.filter(user=self.request.user).first()
            if employee:
                return employee.company
            
            # Fallback: get first company (for staff/admin users)
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
            return JsonResponse({
                'success': False, 
                'error': 'No company access found. Please ensure your user account is linked to an employee record.'
            }, status=403)
        return super().dispatch(request, *args, **kwargs)
    
    def bypass_company_check(self):
        """Override in subclasses to bypass company check for specific views"""
        return False

# ==================== Attendance Log Management ====================

class AttendanceLogFilterForm(forms.Form):
    """Form for filtering attendance logs in the list view"""
    
    SOURCE_TYPE_CHOICES = [
        ('', _('All Sources')),
        ('ZK', _('ZKTeco Device')),
        ('MN', _('Manual')),
        ('MB', _('Mobile')),
    ]
    
    ATTENDANCE_TYPE_CHOICES = [
        ('', _('All Types')),
        ('IN', _('Check-in')),
        ('OUT', _('Check-out')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search by employee name or ID...',
        }),
        label=_('Search')
    )
    
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        required=False,
        empty_label=_('All Employees'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Employee')
    )
    
    device = forms.ModelChoiceField(
        queryset=ZkDevice.objects.filter(is_active=True),
        required=False,
        empty_label=_('All Devices'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Device')
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True),
        required=False,
        empty_label=_('All Locations'),
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Location')
    )
    source_type = forms.ChoiceField(
        choices=SOURCE_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Source Type')
    )
    
    attendance_type = forms.ChoiceField(
        choices=ATTENDANCE_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'input',
        }),
        label=_('Attendance Type')
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('From Date')
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'input',
            'type': 'date',
        }),
        label=_('To Date')
    )

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)
        
        if employee:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=employee.company,
                is_active=True
            ).order_by('name')
            self.fields['device'].queryset = ZkDevice.objects.filter(
                company=employee.company,
                is_active=True
            ).order_by('name')


class AttendanceLogForm(forms.ModelForm):
    """ModelForm for AttendanceLog with proper validation"""
    
    class Meta:
        model = AttendanceLog
        fields = ['employee', 'device', 'timestamp', 'source_type', 'attendance_type', 'location', 'location_name', 'latitude', 'longitude']
        widgets = {
            'employee': forms.Select(attrs={'class': 'input'}),
            'device': forms.Select(attrs={'class': 'input'}),
            'timestamp': forms.DateTimeInput(attrs={
                'class': 'input',
                'type': 'datetime-local'
            }),
            'source_type': forms.Select(attrs={'class': 'input'}),
            'attendance_type': forms.Select(attrs={'class': 'input'}),
            'location': forms.Select(attrs={'class': 'input'}),
            'location_name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Enter location name or device info...'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.00000001',
                'placeholder': '23.810331'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'input',
                'step': '0.00000001',
                'placeholder': '90.412521'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets based on user's employee record
        if user:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=user)
                
                # Filter employees by company
                self.fields['employee'].queryset = Employee.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
                
                # Filter devices by company
                self.fields['device'].queryset = ZkDevice.objects.filter(
                    company=employee.company,
                    is_active=True
                ).order_by('name')
                
            except Employee.DoesNotExist:
                self.fields['employee'].queryset = Employee.objects.none()
                self.fields['device'].queryset = ZkDevice.objects.none()


class AttendanceLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = AttendanceLog
    template_name = 'attendancelog/attendance_log_list.html'
    context_object_name = 'attendance_logs'
    paginate_by = 10
    permission_required = 'zkteco.view_attendancelog'
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.select_related('employee', 'device', 'location')
        
        # Regular users see only logs from their company
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except:
                queryset = queryset.none()
        
        # Apply filters
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            self.filter_form = AttendanceLogFilterForm(self.request.GET, employee=employee)
        except:
            self.filter_form = AttendanceLogFilterForm(self.request.GET)
        
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            
            if data.get('search'):
                queryset = queryset.filter(
                    Q(employee__name__icontains=data['search']) |
                    Q(employee__employee_id__icontains=data['search']) |
                    Q(device__name__icontains=data['search'])
                )
            
            if data.get('employee'):
                queryset = queryset.filter(employee=data['employee'])
            
            if data.get('device'):
                queryset = queryset.filter(device=data['device'])
            
            if data.get('source_type'):
                queryset = queryset.filter(source_type=data['source_type'])
            
            if data.get('attendance_type'):
                queryset = queryset.filter(attendance_type=data['attendance_type'])
            
            if data.get('date_from'):
                queryset = queryset.filter(timestamp__date__gte=data['date_from'])
            
            if data.get('date_to'):
                queryset = queryset.filter(timestamp__date__lte=data['date_to'])
        
        return queryset.order_by('-timestamp')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        queryset = self.get_queryset()
        context['total_logs'] = queryset.count()
        context['device_count'] = queryset.values('device').distinct().count()
        context['employee_count'] = queryset.values('employee').distinct().count()
        context['mobile_count'] = queryset.filter(source_type='MB').count()
        context['filter_form'] = self.filter_form
        
        return context


class AttendanceLogCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendancelog/attendance_log_form.html'
    success_url = reverse_lazy('core:attendance_log_list')
    permission_required = 'zkteco.add_attendancelog'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            from hr_payroll.models import Employee
            employee = Employee.objects.get(user=self.request.user)
            
            # Set default source type if not provided
            if not form.instance.source_type:
                form.instance.source_type = 'MN'  # Manual
            
            messages.success(self.request, _('Attendance log created successfully!'))
            return super().form_valid(form)
            
        except Employee.DoesNotExist:
            messages.error(self.request, _('No employee profile found for your account.'))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class AttendanceLogUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendancelog/attendance_log_form.html'
    success_url = reverse_lazy('core:attendance_log_list')
    permission_required = 'zkteco.change_attendancelog'
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except:
                queryset = queryset.none()
        return queryset
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, _('Attendance log updated successfully!'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class AttendanceLogDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = AttendanceLog
    template_name = 'attendancelog/attendance_log_confirm_delete.html'
    success_url = reverse_lazy('core:attendance_log_list')
    permission_required = 'zkteco.delete_attendancelog'
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.all()
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except:
                queryset = queryset.none()
        return queryset
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Attendance log deleted successfully!'))
        return super().delete(request, *args, **kwargs)


class AttendanceLogDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = AttendanceLog
    template_name = 'attendancelog/attendance_log_detail.html'
    context_object_name = 'attendance_log'
    permission_required = 'zkteco.view_attendancelog'
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.select_related('employee', 'device', 'location')
        if not self.request.user.is_staff:
            try:
                from hr_payroll.models import Employee
                employee = Employee.objects.get(user=self.request.user)
                queryset = queryset.filter(employee__company=employee.company)
            except:
                queryset = queryset.none()
        return queryset


# FIXED: Added CompanyAccessMixin to these views
class FetchAttendanceDataView(LoginRequiredMixin, CompanyAccessMixin, View):
    """Class-based view to fetch attendance data from selected devices (preview before import)"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            device_ids = data.get('device_ids', [])
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            if not device_ids:
                return JsonResponse({'success': False, 'error': 'No devices selected'})
            
            # Use company from mixin
            if not self.company:
                return JsonResponse({
                    'success': False, 
                    'error': 'No company access found. Please ensure your user account is linked to an employee record.'
                })
            
            devices = ZkDevice.objects.filter(id__in=device_ids, company=self.company)
            device_list = []
            
            for device in devices:
                device_data = {
                    'ip': device.ip_address,
                    'port': device.port,
                    'id': device.id,
                    'name': device.name,
                    'password': device.password if device.password else 0
                }
                device_list.append(device_data)
            
            # Convert string dates to date objects
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
            
            # Use the device manager directly
            device_manager = ZKTecoDeviceManager()
            attendance_data, fetch_results = device_manager.get_multiple_attendance_data(
                device_list, start_date_obj, end_date_obj
            )
            
            # Process and format the data with duplicate checking
            formatted_data = []
            for record in attendance_data:
                # Find matching employee
                employee = Employee.objects.filter(
                    Q(zkteco_id=record['zkteco_id']) | Q(employee_id=record['zkteco_id']),
                    company=self.company
                ).first()
                
                # Check if already imported (duplicate check)
                is_imported = False
                if employee:
                    is_imported = AttendanceLog.objects.filter(
                        employee=employee,
                        timestamp=record['timestamp'],
                        device__ip_address=record['device_ip']
                    ).exists()
                
                formatted_record = {
                    'device_name': record['device_name'],
                    'device_ip': record['device_ip'],
                    'zkteco_id': record['zkteco_id'],
                    'employee_id': employee.employee_id if employee else record['zkteco_id'],
                    'employee_name': employee.name if employee else 'Unknown Employee',
                    'timestamp': record['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'date': record['timestamp'].strftime('%Y-%m-%d'),
                    'time': record['timestamp'].strftime('%H:%M:%S'),
                    'punch_type': record.get('punch_type', 0),
                    'verify_type': record.get('verify_type', 0),
                    'source_type': record.get('source_type', 'device'),
                    'is_imported': is_imported,
                    'has_employee': bool(employee),
                    'can_import': bool(employee) and not is_imported,
                    'raw_timestamp': record['timestamp']
                }
                formatted_data.append(formatted_record)
            
            # Sort by timestamp (newest first)
            formatted_data.sort(key=lambda x: x['raw_timestamp'], reverse=True)
            
            # Store in session for import (only importable records)
            session_data = []
            for record in formatted_data:
                if record['can_import']:
                    session_record = {
                        'zkteco_id': record['zkteco_id'],
                        'timestamp': record['raw_timestamp'].isoformat(),
                        'device_ip': record['device_ip'],
                        'punch_type': record['punch_type'],
                        'verify_type': record['verify_type'],
                        'source_type': record['source_type']
                    }
                    session_data.append(session_record)
            
            request.session['fetched_attendance_data'] = session_data
            
            return JsonResponse({
                'success': True,
                'data': formatted_data,
                'total_records': len(formatted_data),
                'new_records': len([r for r in formatted_data if r['can_import']]),
                'imported_records': len([r for r in formatted_data if r['is_imported']]),
                'missing_employee_records': len([r for r in formatted_data if not r['has_employee']]),
                'fetch_results': fetch_results,
                'message': f'Fetched {len(formatted_data)} attendance records'
            })
            
        except Exception as e:
            logger.error(f"Error fetching attendance data: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})


class ImportAttendanceDataView(LoginRequiredMixin, CompanyAccessMixin, View):
    """Class-based view to import selected attendance data to database"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            selected_indices = data.get('selected_indices', [])
            import_all = data.get('import_all', False)
            
            fetched_data = request.session.get('fetched_attendance_data', [])
            
            if not fetched_data:
                return JsonResponse({'success': False, 'error': 'No data to import. Please fetch data first.'})
            
            # Use company from mixin
            if not self.company:
                return JsonResponse({
                    'success': False, 
                    'error': 'No company access found. Please ensure your user account is linked to an employee record.'
                })
            
            if import_all:
                records_to_import = fetched_data
            else:
                if not selected_indices:
                    return JsonResponse({'success': False, 'error': 'No records selected for import'})
                records_to_import = [fetched_data[i] for i in selected_indices if i < len(fetched_data)]
            
            imported_count = 0
            duplicate_count = 0
            error_count = 0
            missing_employee_count = 0
            
            with transaction.atomic():
                for record in records_to_import:
                    try:
                        # Find employee
                        employee = Employee.objects.filter(
                            Q(zkteco_id=record['zkteco_id']) | Q(employee_id=record['zkteco_id']),
                            company=self.company
                        ).first()
                        
                        if not employee:
                            missing_employee_count += 1
                            continue
                        
                        # Find device
                        device = ZkDevice.objects.filter(
                            ip_address=record['device_ip'], 
                            company=self.company
                        ).first()
                        
                        # Convert timestamp back to datetime
                        timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
                        if timestamp.tzinfo is None:
                            timestamp = timezone.make_aware(timestamp)
                        
                        # Final duplicate check
                        existing = AttendanceLog.objects.filter(
                            employee=employee,
                            timestamp=timestamp,
                            device=device
                        ).exists()
                        
                        if existing:
                            duplicate_count += 1
                            continue
                        
                        # Create attendance log
                        AttendanceLog.objects.create(
                            employee=employee,
                            device=device,
                            timestamp=timestamp,
                            source_type=record.get('source_type', 'device')
                        )
                        
                        imported_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error importing record {record}: {str(e)}")
                        error_count += 1
            
            # Clear session data after successful import
            if 'fetched_attendance_data' in request.session:
                del request.session['fetched_attendance_data']
            
            return JsonResponse({
                'success': True,
                'imported_count': imported_count,
                'duplicate_count': duplicate_count,
                'error_count': error_count,
                'missing_employee_count': missing_employee_count,
                'message': f'Import completed: {imported_count} imported, {duplicate_count} duplicates skipped, {missing_employee_count} missing employees, {error_count} errors.'
            })
            
        except Exception as e:
            logger.error(f"Error importing attendance data: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})