from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views import View
from django.db.models import Q
from math import radians, cos, sin, asin, sqrt
from decimal import Decimal
import logging
from datetime import timedelta
import requests
from ..models import Location, UserLocation, AttendanceLog, Employee, ZkDevice
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================
def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers"""
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371  # Earth radius in km


def get_address_from_coords(latitude, longitude):
    """Get a formatted address string from coordinates using OpenWeatherMap API"""
    try:
        lat_float = float(latitude)
        lon_float = float(longitude)
        
        # Try OpenWeatherMap Geocoding API
        try:
            api_key = "5b0498f50f16aa88a9c91fc3bb43a519"
            url = f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat_float}&lon={lon_float}&limit=1&appid={api_key}"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    location_data = data[0]
                    address_parts = []
                    
                    if location_data.get('name'):
                        address_parts.append(location_data['name'])
                    if location_data.get('state'):
                        address_parts.append(location_data['state'])
                    if location_data.get('country'):
                        address_parts.append(location_data['country'])
                    
                    if address_parts:
                        address = ', '.join(address_parts)
                        logger.info(f"OpenWeatherMap geocoding successful: {address}")
                        return address
                        
        except requests.exceptions.Timeout:
            logger.warning("OpenWeatherMap geocoding timeout")
        except Exception as e:
            logger.warning(f"OpenWeatherMap geocoding failed: {e}")
        
        # Fallback: Try OpenStreetMap
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat_float}&lon={lon_float}&zoom=16"
            headers = {'User-Agent': 'ezydreamhrm/1.0'}
            
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                address = data.get('display_name', '')
                if address:
                    logger.info(f"OpenStreetMap fallback geocoding successful: {address}")
                    return address
        except Exception as e:
            logger.warning(f"OpenStreetMap fallback failed: {e}")
        
        # Final fallback
        return f"Coordinates: {lat_float:.6f}, {lon_float:.6f}"
        
    except (ValueError, TypeError) as e:
        logger.warning(f"Geocoding error: {e}")
        return f"Coordinates: {latitude}, {longitude}"


# ==================== LOCATION VIEWS ====================
class LocationListView(LoginRequiredMixin, ListView):
    """List all locations"""
    model = Location
    template_name = 'location/location_list.html'
    context_object_name = 'locations'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Location.objects.all().order_by('name')
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
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
    model = Location
    template_name = 'location/location_form.html'
    fields = ['name', 'address', 'latitude', 'longitude', 'radius', 'is_active']
    success_url = reverse_lazy('zkteco:location_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Location "{form.instance.name}" created successfully.')
        return super().form_valid(form)


class LocationUpdateView(LoginRequiredMixin, UpdateView):
    model = Location
    template_name = 'location/location_form.html'
    fields = ['name', 'address', 'latitude', 'longitude', 'radius', 'is_active']
    success_url = reverse_lazy('zkteco:location_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Location "{form.instance.name}" updated successfully.')
        return super().form_valid(form)


class LocationDetailView(LoginRequiredMixin, DetailView):
    model = Location
    template_name = 'location/location_detail.html'
    context_object_name = 'location'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assigned_users'] = UserLocation.objects.filter(
            location=self.object
        ).select_related('user')
        return context


class LocationDeleteView(LoginRequiredMixin, DeleteView):
    model = Location
    success_url = reverse_lazy('zkteco:location_list')
    template_name = 'location/location_confirm_delete.html'
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Location deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ==================== USER LOCATION VIEWS ====================
class UserLocationListView(LoginRequiredMixin, ListView):
    model = UserLocation
    template_name = 'location/user_location_list.html'
    context_object_name = 'user_locations'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = UserLocation.objects.all().select_related('user', 'location')
        
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        location_id = self.request.GET.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        return queryset.order_by('user__username')


class UserLocationCreateView(LoginRequiredMixin, CreateView):
    model = UserLocation
    template_name = 'location/user_location_form.html'
    fields = ['user', 'location', 'is_primary']
    success_url = reverse_lazy('zkteco:user_location_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'User assigned to location successfully.')
        return super().form_valid(form)


class UserLocationUpdateView(LoginRequiredMixin, UpdateView):
    model = UserLocation
    template_name = 'location/user_location_form.html'
    fields = ['user', 'location', 'is_primary']
    success_url = reverse_lazy('zkteco:user_location_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Assignment updated successfully.')
        return super().form_valid(form)


class UserLocationDeleteView(LoginRequiredMixin, DeleteView):
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
        
        has_assignments = UserLocation.objects.filter(user=self.request.user).exists()
        
        try:
            employee = Employee.objects.get(user=self.request.user)
        except Employee.DoesNotExist:
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
    """API to get locations based on company's location_restricted setting"""
    
    def get(self, request):
        try:
            # Get employee and company
            try:
                employee = Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                try:
                    employee = Employee.objects.get(employee_id=request.user.username)
                except Employee.DoesNotExist:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Employee record not found. Please contact administrator.'
                    }, status=404)
            
            company = employee.company
            location_restricted = company.location_restricted if company else True
            
            logger.info(f"User {request.user.username}, Company: {company.name if company else 'None'}, Location Restricted: {location_restricted}")
            
            # Get user's assigned locations (for reference)
            user_location_ids = UserLocation.objects.filter(
                user=request.user
            ).values_list('location_id', flat=True)
            
            has_assignments = len(user_location_ids) > 0
            
            if location_restricted:
                # RESTRICTED MODE: Show only assigned active locations
                user_locations = UserLocation.objects.filter(
                    user=request.user,
                    location__is_active=True
                ).select_related('location')
                
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
                
                logger.info(f"RESTRICTED MODE: User {request.user.username} has {len(locations)} assigned locations")
                
            else:
                # NON-RESTRICTED MODE: Show ALL active locations regardless of assignment
                all_locations = Location.objects.filter(is_active=True)
                
                locations = [{
                    'id': loc.id,
                    'name': loc.name,
                    'address': loc.address,
                    'latitude': float(loc.latitude),
                    'longitude': float(loc.longitude),
                    'radius': float(loc.radius),
                    'is_primary': loc.id in user_location_ids,  # Check if user is assigned
                    'is_assigned': loc.id in user_location_ids  # Mark if assigned
                } for loc in all_locations]
                
                logger.info(f"NON-RESTRICTED MODE: Showing all {len(locations)} active locations (User has {len(user_location_ids)} assignments)")
            
            return JsonResponse({
                'status': 'success',
                'data': locations,
                'location_restricted': location_restricted,
                'has_assignments': has_assignments,
                'total_locations': len(locations)
            })
            
        except Exception as e:
            logger.exception(f"Error getting locations: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
class MarkAttendanceView(LoginRequiredMixin, View):
    """API to mark mobile attendance with location restriction logic"""
    
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
                    'message': _('Location not found or inactive')
                }, status=404)
            
            # Get employee
            try:
                employee = Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                try:
                    employee = Employee.objects.get(employee_id=request.user.username)
                except Employee.DoesNotExist:
                    return JsonResponse({
                        'status': 'error',
                        'message': _('Employee record not found. Please contact administrator.')
                    }, status=404)
            
            # Get company and location restriction setting
            company = employee.company
            location_restricted = company.location_restricted if company else True
            
            # Calculate distance
            distance_km = haversine(
                location.latitude,
                location.longitude,
                Decimal(latitude),
                Decimal(longitude)
            )
            
            is_within_radius = distance_km <= (float(location.radius) / 1000)
            
            # Get actual GPS location name
            actual_location_name = get_address_from_coords(latitude, longitude)
            
            logger.info(f"Attendance attempt - User: {request.user.username}, Location: {location.name}, "
                       f"Distance: {distance_km:.3f}km, Radius: {float(location.radius)/1000:.3f}km, "
                       f"Within Radius: {is_within_radius}, Restricted: {location_restricted}")
            
            # LOCATION RESTRICTION LOGIC
            if location_restricted:
                # RESTRICTED MODE: Check assignment and radius
                user_location = UserLocation.objects.filter(
                    user=request.user,
                    location=location
                ).first()
                
                if not user_location:
                    return JsonResponse({
                        'status': 'error',
                        'message': _('You are not assigned to this location. Please contact administrator.'),
                        'data': {
                            'location_restricted': True,
                            'has_assignment': False
                        }
                    }, status=403)
                
                # Check radius - MUST be within radius in restricted mode
                if not is_within_radius:
                    return JsonResponse({
                        'status': 'error',
                        'message': _(f'You must be within {float(location.radius)}m radius to mark attendance.'),
                        'data': {
                            'distance': round(distance_km * 1000, 2),
                            'required_radius': float(location.radius),
                            'location_restricted': True,
                            'is_within_radius': False,
                            'actual_location': actual_location_name
                        }
                    }, status=400)
            
            else:
                # NON-RESTRICTED MODE: Allow attendance from anywhere
                # No assignment check, no radius check
                logger.info(f"NON-RESTRICTED MODE: Allowing attendance from {distance_km:.3f}km away")
            
            # Get or create mobile device
            device, created = ZkDevice.objects.get_or_create(
                company=company,
                name='Mobile Attendance Device',
                defaults={
                    'ip_address': '0.0.0.0',
                    'port': 0,
                    'is_active': True,
                    'description': 'Virtual device for mobile attendance tracking'
                }
            )
            
            # Determine punch type
            if attendance_type == 'IN':
                punch_type = 'CHECK_IN'
                status_code = 0
            else:
                punch_type = 'CHECK_OUT'
                status_code = 1
            
            # Create attendance log with ACTUAL location name (not the assigned location)
            attendance_log = AttendanceLog.objects.create(
                device=device,
                employee=employee,
                timestamp=timezone.now(),
                status_code=status_code,
                punch_type=punch_type,
                source_type='MB',  # Mobile
                user=request.user,
                location=location,  # Assigned location reference
                attendance_type=attendance_type,
                latitude=latitude,
                longitude=longitude,
                is_within_radius=is_within_radius,
                distance=distance_km,
                location_name=actual_location_name,  # ACTUAL GPS location name
                device_info=device_info,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            success_message = f'Attendance marked successfully!'
            if not is_within_radius and not location_restricted:
                success_message += f' (Outside location radius - {round(distance_km * 1000, 2)}m away)'
            
            logger.info(
                f"✓ Attendance marked: user={request.user.username}, employee={employee.employee_id}, "
                f"location={location.name}, type={attendance_type}, within_radius={is_within_radius}, "
                f"distance={distance_km:.3f}km, actual_location={actual_location_name}, "
                f"restricted={location_restricted}"
            )
            
            return JsonResponse({
                'status': 'success',
                'message': _(success_message),
                'data': {
                    'id': attendance_log.id,
                    'timestamp': attendance_log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'is_within_radius': is_within_radius,
                    'distance': round(distance_km * 1000, 2),
                    'assigned_location': location.name,
                    'actual_location': actual_location_name,
                    'type': attendance_type,
                    'location_restricted': location_restricted
                }
            })
            
        except Exception as e:
            logger.exception(f"Error marking attendance: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': _('An error occurred while marking attendance')
            }, status=500)
class GetUserAttendanceLogsView(LoginRequiredMixin, View):
    """API to get current user's attendance logs"""
    
    def get(self, request):
        try:
            # Get employee
            try:
                employee = Employee.objects.get(user=request.user)
            except Employee.DoesNotExist:
                try:
                    employee = Employee.objects.get(employee_id=request.user.username)
                except Employee.DoesNotExist:
                    return JsonResponse({
                        'status': 'error',
                        'message': _('Employee record not found')
                    }, status=404)
            
            # Get filter parameters
            days = request.GET.get('days', '7')
            
            if days == 'all':
                date_from = None
            else:
                try:
                    days_int = int(days)
                    date_from = timezone.now() - timedelta(days=days_int)
                except ValueError:
                    date_from = timezone.now() - timedelta(days=7)
            
            # Build queryset
            queryset = AttendanceLog.objects.filter(
                employee=employee,
                source_type='MB'
            ).select_related('location').order_by('-timestamp')
            
            if date_from:
                queryset = queryset.filter(timestamp__gte=date_from)
            
            # Prepare data
            logs = []
            for log in queryset:
                logs.append({
                    'id': log.id,
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'date': log.timestamp.strftime('%Y-%m-%d'),
                    'time': log.timestamp.strftime('%H:%M:%S'),
                    'type': log.attendance_type,
                    'type_display': 'Check In' if log.attendance_type == 'IN' else 'Check Out',
                    'location': log.location.name if log.location else 'Unknown',
                    'actual_location': log.location_name or 'Not recorded',
                    'latitude': float(log.latitude) if log.latitude else None,
                    'longitude': float(log.longitude) if log.longitude else None,
                    'distance': round(float(log.distance) * 1000, 2) if log.distance else None,
                    'is_within_radius': log.is_within_radius,
                })
            
            return JsonResponse({
                'status': 'success',
                'data': logs,
                'count': len(logs),
                'employee': {
                    'id': employee.id,
                    'employee_id': employee.employee_id,
                    'name': employee.name
                }
            })
            
        except Exception as e:
            logger.exception(f"Error getting attendance logs: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)


# ==================== ATTENDANCE LOG VIEWS ====================
class AttendanceLogListView(LoginRequiredMixin, ListView):
    model = AttendanceLog
    template_name = 'location/attendance_log_list.html'
    context_object_name = 'logs'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = AttendanceLog.objects.all().select_related(
            'employee', 'device', 'user', 'location'
        ).order_by('-timestamp')
        
        source_type = self.request.GET.get('source_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        
        employee_id = self.request.GET.get('employee')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        
        location_id = self.request.GET.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)
        
        return queryset

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