from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views import View
from math import radians, cos, sin, asin, sqrt
from decimal import Decimal
import logging

from ..models import Location, UserLocation, AttendanceLog, Employee, ZkDevice
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTION ====================
def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers"""
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371  # Earth radius in km


# ==================== LOCATION VIEWS ====================
class LocationListView(LoginRequiredMixin, ListView):
    """List all locations"""
    model = Location
    template_name = 'location/location_list.html'
    context_object_name = 'locations'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Location.objects.all().order_by('name')
        
        # Search filter
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Active filter
        is_active = self.request.GET.get('is_active')
        if is_active:
            queryset = queryset.filter(is_active=is_active == 'True')
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Locations')
        context['subtitle'] = _('Manage attendance locations')
        return context


class LocationCreateView(LoginRequiredMixin, CreateView):
    """Create new location"""
    model = Location
    template_name = 'location/location_form.html'
    fields = ['name', 'address', 'latitude', 'longitude', 'radius', 'is_active']
    success_url = reverse_lazy('zkteco:location_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Create Location')
        context['subtitle'] = _('Add a new location for attendance tracking')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f'Location "{form.instance.name}" created successfully.')
        return super().form_valid(form)


class LocationUpdateView(LoginRequiredMixin, UpdateView):
    """Update existing location"""
    model = Location
    template_name = 'location/location_form.html'
    fields = ['name', 'address', 'latitude', 'longitude', 'radius', 'is_active']
    success_url = reverse_lazy('zkteco:location_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Update Location')
        context['subtitle'] = f'Edit location "{self.object.name}"'
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f'Location "{form.instance.name}" updated successfully.')
        return super().form_valid(form)


class LocationDetailView(LoginRequiredMixin, DetailView):
    """View location details"""
    model = Location
    template_name = 'location/location_detail.html'
    context_object_name = 'location'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Location Details')
        context['subtitle'] = f'zkteco: {self.object.name}'
        
        # Get assigned users
        context['assigned_users'] = UserLocation.objects.filter(
            location=self.object
        ).select_related('user')
        
        return context


class LocationDeleteView(LoginRequiredMixin, DeleteView):
    """Delete location"""
    model = Location
    success_url = reverse_lazy('zkteco:location_list')
    template_name = 'location/location_confirm_delete.html'
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Location deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ==================== USER LOCATION VIEWS ====================
class UserLocationListView(LoginRequiredMixin, ListView):
    """List all user location assignments"""
    model = UserLocation
    template_name = 'location/user_location_list.html'
    context_object_name = 'user_locations'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = UserLocation.objects.all().select_related('user', 'location')
        
        # User filter
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Location filter
        location_id = self.request.GET.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        return queryset.order_by('user__username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('User Locations')
        context['subtitle'] = _('Manage user location assignments')
        context['users'] = User.objects.all()
        context['locations'] = Location.objects.filter(is_active=True)
        return context


class UserLocationCreateView(LoginRequiredMixin, CreateView):
    """Assign user to location"""
    model = UserLocation
    template_name = 'location/user_location_form.html'
    fields = ['user', 'location', 'is_primary']
    success_url = reverse_lazy('zkteco:user_location_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Assign Location')
        context['subtitle'] = _('Assign a user to a location')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'User assigned to location successfully.')
        return super().form_valid(form)


class UserLocationUpdateView(LoginRequiredMixin, UpdateView):
    """Update user location assignment"""
    model = UserLocation
    template_name = 'location/user_location_form.html'
    fields = ['user', 'location', 'is_primary']
    success_url = reverse_lazy('zkteco:user_location_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Update Assignment')
        context['subtitle'] = _('Update user location assignment')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Assignment updated successfully.')
        return super().form_valid(form)


class UserLocationDeleteView(LoginRequiredMixin, DeleteView):
    """Remove user from location"""
    model = UserLocation
    success_url = reverse_lazy('zkteco:user_location_list')
    template_name = 'location/user_location_confirm_delete.html'
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'User location assignment removed successfully.')
        return super().delete(request, *args, **kwargs)


# ==================== MOBILE ATTENDANCE VIEWS ====================
class MobileAttendanceView(LoginRequiredMixin, TemplateView):
    """Mobile attendance marking page"""
    template_name = 'location/mobile_attendance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if user has any location assignments
        has_assignments = UserLocation.objects.filter(user=self.request.user).exists()
        
        # Try to get employee record
        try:
            employee = Employee.objects.get(employee_id=self.request.user.username)
        except Employee.DoesNotExist:
            employee = None
        
        context.update({
            'title': _('Mobile Attendance'),
            'subtitle': _('Mark your attendance from anywhere'),
            'has_assignments': has_assignments,
            'employee': employee,
        })
        
        return context


class GetLocationsView(LoginRequiredMixin, View):
    """API to get user's assigned locations or all locations if no assignment"""
    
    def get(self, request):
        try:
            # First check if user has any location assignments
            user_locations = UserLocation.objects.filter(
                user=request.user
            ).select_related('location').filter(location__is_active=True)
            
            if user_locations.exists():
                # User has assignments - return only assigned locations
                locations = [{
                    'id': ul.location.id,
                    'name': ul.location.name,
                    'address': ul.location.address,
                    'latitude': float(ul.location.latitude),
                    'longitude': float(ul.location.longitude),
                    'radius': float(ul.location.radius),
                    'is_primary': ul.is_primary,
                    'is_assigned': True
                } for ul in user_locations]
                
                logger.info(f"User {request.user.username} has {len(locations)} assigned locations")
            else:
                # No assignments - return all active locations
                all_locations = Location.objects.filter(is_active=True)
                locations = [{
                    'id': loc.id,
                    'name': loc.name,
                    'address': loc.address,
                    'latitude': float(loc.latitude),
                    'longitude': float(loc.longitude),
                    'radius': float(loc.radius),
                    'is_primary': False,
                    'is_assigned': False
                } for loc in all_locations]
                
                logger.info(f"User {request.user.username} has no assignments, showing all {len(locations)} locations")
            
            return JsonResponse({
                'status': 'success',
                'data': locations,
                'has_assignments': user_locations.exists()
            })
        except Exception as e:
            logger.exception(f"Error getting locations: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)


class MarkAttendanceView(LoginRequiredMixin, View):
    """API to mark mobile attendance in AttendanceLog"""
    
    def post(self, request):
        try:
            # Get POST data
            location_id = request.POST.get('location_id')
            attendance_type = request.POST.get('attendance_type')
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            device_info = request.POST.get('device_info', '')
            
            # Validate required fields
            if not all([location_id, attendance_type, latitude, longitude]):
                return JsonResponse({
                    'status': 'error',
                    'message': _('Missing required fields')
                }, status=400)
            
            # Validate attendance type
            if attendance_type not in ['IN', 'OUT']:
                return JsonResponse({
                    'status': 'error',
                    'message': _('Invalid attendance type')
                }, status=400)
            
            # Get location
            try:
                location = Location.objects.get(id=location_id, is_active=True)
            except Location.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': _('Location not found')
                }, status=404)
            
            # Check if user has any location assignments
            has_assignments = UserLocation.objects.filter(user=request.user).exists()
            
            if has_assignments:
                # User has assignments - check if this location is assigned
                user_location = UserLocation.objects.filter(
                    user=request.user, 
                    location=location
                ).first()
                
                if not user_zkteco:
                    logger.warning(
                        f"User {request.user.username} attempted to mark attendance at "
                        f"unassigned location {location.name}"
                    )
                    return JsonResponse({
                        'status': 'error',
                        'message': _('You are not assigned to this location')
                    }, status=403)
            
            # Get employee record - Changed to use user field instead of employee_id
            try:
                employee = Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                # Try fallback with username matching employee_id
                try:
                    employee = Employee.objects.get(employee_id=request.user.username)
                except Employee.DoesNotExist:
                    logger.error(f"No employee record found for user {request.user.username}")
                    return JsonResponse({
                        'status': 'error',
                        'message': _('Employee record not found. Please contact administrator.')
                    }, status=404)
            
            # Calculate distance
            distance = haversine(
                location.latitude,
                location.longitude,
                Decimal(latitude),
                Decimal(longitude)
            )
            
            # Check if within radius
            is_within_radius = distance <= float(location.radius)
            
            if not is_within_radius:
                logger.warning(
                    f"User {request.user.username} attempted attendance outside radius: "
                    f"distance={distance:.2f}km, required={location.radius}km"
                )
                return JsonResponse({
                    'status': 'error',
                    'message': _('You are outside the location radius'),
                    'data': {
                        'distance': round(distance, 2),
                        'required_radius': float(location.radius)
                    }
                }, status=400)
            
            # Get or create a virtual device for mobile attendance
            device, created = ZkDevice.objects.get_or_create(
                company=employee.company,
                name='Mobile Attendance Device',
                defaults={
                    'ip_address': '0.0.0.0',
                    'port': 0,
                    'is_active': True,
                    'description': 'Virtual device for mobile attendance tracking'
                }
            )
            
            # Determine punch type and status code based on attendance type
            if attendance_type == 'IN':
                punch_type = 'CHECK_IN'
                status_code = 0
            else:
                punch_type = 'CHECK_OUT'
                status_code = 1
            
            # Create attendance log entry
            attendance_log = AttendanceLog.objects.create(
                device=device,
                employee=employee,
                timestamp=timezone.now(),
                status_code=status_code,
                punch_type=punch_type,
                source_type='MB',  # Mobile
                user=request.user,
                location=location,
                attendance_type=attendance_type,
                latitude=latitude,
                longitude=longitude,
                is_within_radius=is_within_radius,
                distance=distance,
                device_info=device_info,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            logger.info(
                f"Mobile attendance marked successfully: "
                f"user={request.user.username}, employee={employee.employee_id}, "
                f"location={location.name}, type={attendance_type}, "
                f"distance={distance:.2f}km, has_assignment={has_assignments}"
            )
            
            return JsonResponse({
                'status': 'success',
                'message': _('Attendance marked successfully'),
                'data': {
                    'id': attendance_log.id,
                    'timestamp': attendance_log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'is_within_radius': is_within_radius,
                    'distance': round(distance, 2),
                    'location': location.name,
                    'type': attendance_type,
                    'has_assignment': has_assignments
                }
            })
            
        except Exception as e:
            logger.exception(f"Error marking attendance: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': _('An error occurred while marking attendance')
            }, status=500)
# ==================== ATTENDANCE LOG VIEWS ====================
class AttendanceLogListView(LoginRequiredMixin, ListView):
    """List all attendance logs"""
    model = AttendanceLog
    template_name = 'location/attendance_log_list.html'
    context_object_name = 'logs'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.all().select_related(
            'employee', 'device', 'user', 'location'
        ).order_by('-timestamp')
        
        # Source type filter
        source_type = self.request.GET.get('source_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        
        # Employee filter
        employee_id = self.request.GET.get('employee')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        
        # Location filter
        location_id = self.request.GET.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Date filter
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Attendance Logs')
        context['subtitle'] = _('View all attendance records')
        context['employees'] = Employee.objects.filter(is_active=True)
        context['locations'] = Location.objects.filter(is_active=True)
        context['source_types'] = AttendanceLog.SOURCE_TYPES
        return context


class AttendanceLogDetailView(LoginRequiredMixin, DetailView):
    """View attendance log details"""
    model = AttendanceLog
    template_name = 'location/attendance_log_detail.html'
    context_object_name = 'log'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Attendance Log Details')
        context['subtitle'] = f'Log #{self.object.id}'
        return context