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
    """
    Get a formatted address string from coordinates using geocode.maps.co API (FREE)
    Reverse Geocoding: Convert coordinates to address
    
    API Endpoint: https://geocode.maps.co/reverse?lat=latitude&lon=longitude&api_key=YOUR_SECRET_API_KEY
    """
    try:
        lat_float = float(latitude)
        lon_float = float(longitude)
        
        # Your API Key from geocode.maps.co
        API_KEY = "68f1f9d5c3920013927254yec95eb87"
        
        # Geocode.maps.co Reverse Geocoding API
        url = f"https://geocode.maps.co/reverse?lat={lat_float}&lon={lon_float}&api_key={API_KEY}"
        
        logger.info(f"Fetching address from geocode.maps.co: lat={lat_float}, lon={lon_float}")
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract address components
            address_parts = []
            
            # Geocode.maps.co returns detailed address information
            if 'address' in data:
                address_dict = data['address']
                
                # Build address from most specific to general
                components_order = [
                    'road',
                    'neighbourhood',
                    'village',
                    'city',
                    'county',
                    'state',
                    'country'
                ]
                
                for component in components_order:
                    if component in address_dict and address_dict[component]:
                        address_parts.append(address_dict[component])
                
                if address_parts:
                    address = ', '.join(address_parts)
                    logger.info(f"✓ Geocode.maps.co reverse geocoding successful: {address}")
                    return address
            
            # Fallback: use display_name if available
            if 'display_name' in data:
                logger.info(f"✓ Using display_name: {data['display_name']}")
                return data['display_name']
        
        else:
            logger.warning(f"Geocode.maps.co API error: Status {response.status_code}")
            # Log the response for debugging
            logger.debug(f"Response: {response.text}")
        
    except requests.exceptions.Timeout:
        logger.warning("Geocode.maps.co geocoding timeout")
    except requests.exceptions.ConnectionError:
        logger.warning("Geocode.maps.co connection error")
    except Exception as e:
        logger.warning(f"Geocode.maps.co geocoding error: {e}")
    
    # Fallback: Return coordinates as string
    try:
        return f"Latitude: {float(latitude):.6f}, Longitude: {float(longitude):.6f}"
    except:
        return f"Coordinates: {latitude}, {longitude}"

def search_location_by_address(address):
    """
    Search for location by address using geocode.maps.co API (FREE)
    Forward Geocoding: Search or convert address to coordinates
    
    API Endpoint: https://geocode.maps.co/search?q=address&api_key=YOUR_SECRET_API_KEY
    """
    try:
        API_KEY = "68f1f9d5c3920013927254yec95eb87"
        
        # Geocode.maps.co Forward Geocoding API
        url = f"https://geocode.maps.co/search?q={address}&api_key={API_KEY}&limit=1"
        
        logger.info(f"Searching address via geocode.maps.co: {address}")
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data and len(data) > 0:
                result = data[0]
                location_data = {
                    'latitude': float(result.get('lat')),
                    'longitude': float(result.get('lon')),
                    'display_name': result.get('display_name', address),
                    'address': result.get('address', {})
                }
                
                logger.info(f"✓ Forward geocoding successful: {location_data['display_name']}")
                return location_data
        
        logger.warning(f"No results from forward geocoding for: {address}")
        return None
        
    except Exception as e:
        logger.warning(f"Forward geocoding error: {e}")
        return None

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


# ==================== LOCATION VIEWS ====================
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
            
            logger.info(
                f"GetLocations - User: {request.user.username}, "
                f"Company: {company.name if company else 'None'}, "
                f"Location Restricted: {location_restricted}"
            )
            
            # Get user's assigned locations
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
                # NON-RESTRICTED MODE: Show ALL active locations
                all_locations = Location.objects.filter(is_active=True)
                
                locations = [{
                    'id': loc.id,
                    'name': loc.name,
                    'address': loc.address,
                    'latitude': float(loc.latitude),
                    'longitude': float(loc.longitude),
                    'radius': float(loc.radius),
                    'is_primary': loc.id in user_location_ids,
                    'is_assigned': loc.id in user_location_ids
                } for loc in all_locations]
                
                logger.info(
                    f"NON-RESTRICTED MODE: Showing {len(locations)} active locations "
                    f"(User has {len(user_location_ids)} assignments)"
                )
            
            return JsonResponse({
                'status': 'success',
                'data': locations,
                'location_restricted': location_restricted,
                'has_assignments': has_assignments,
                'total_locations': len(locations),
                'api_provider': 'geocode.maps.co'
            })
            
        except Exception as e:
            logger.exception(f"Error getting locations: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)


class MarkAttendanceView(LoginRequiredMixin, View):
    """
    FIXED API to mark mobile attendance with geocode.maps.co integration
    - Works with OR without predefined locations
    - Gets actual location name from coordinates
    - Only requires: attendance_type, latitude, longitude
    """
    
    def post(self, request):
        try:
            # Get POST data
            location_id = request.POST.get('location_id')  # Optional
            attendance_type = request.POST.get('attendance_type')  # Required
            latitude = request.POST.get('latitude')  # Required
            longitude = request.POST.get('longitude')  # Required
            device_info = request.POST.get('device_info', '')  # Optional
            
            # VALIDATION: Only attendance_type, latitude, longitude are required
            if not attendance_type or not latitude or not longitude:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing required fields: attendance_type, latitude, longitude',
                    'required_fields': ['attendance_type', 'latitude', 'longitude']
                }, status=400)
            
            if attendance_type not in ['IN', 'OUT']:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid attendance type. Must be IN or OUT'
                }, status=400)
            
            # Try to convert coordinates
            try:
                lat_float = float(latitude)
                lon_float = float(longitude)
                
                if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                    raise ValueError("Invalid coordinate range")
            except (ValueError, TypeError):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid latitude or longitude values'
                }, status=400)
            
            # Get employee (Required)
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
            
            # Get company
            company = employee.company
            location_restricted = company.location_restricted if company else True
            
            logger.info(
                f"Attendance attempt - User: {request.user.username}, "
                f"Employee: {employee.employee_id}, Type: {attendance_type}, "
                f"Coords: {lat_float:.6f}, {lon_float:.6f}, "
                f"Location Restricted: {location_restricted}, Location ID: {location_id}"
            )
            
            # ==================== GET ACTUAL LOCATION NAME ====================
            # Call geocode.maps.co to get the actual address from GPS coordinates
            actual_location_name = get_address_from_coords(lat_float, lon_float)
            logger.info(f"Actual location name from geocoding: {actual_location_name}")
            
            # ==================== LOCATION HANDLING LOGIC ====================
            location_obj = None
            assigned_location_name = None
            distance_km = None
            is_within_radius = False
            
            # CASE 1: location_id provided
            if location_id:
                try:
                    location_obj = Location.objects.get(id=location_id, is_active=True)
                    assigned_location_name = location_obj.name
                    
                    # Calculate distance
                    distance_km = haversine(
                        location_obj.latitude,
                        location_obj.longitude,
                        Decimal(latitude),
                        Decimal(longitude)
                    )
                    
                    is_within_radius = distance_km <= (float(location_obj.radius) / 1000)
                    
                    logger.info(
                        f"Location: {location_obj.name}, Distance: {distance_km:.3f}km, "
                        f"Radius: {float(location_obj.radius)/1000:.3f}km, Within: {is_within_radius}"
                    )
                    
                    # Location restriction check
                    if location_restricted:
                        user_location = UserLocation.objects.filter(
                            user=request.user,
                            location=location_obj
                        ).first()
                        
                        if not user_location:
                            return JsonResponse({
                                'status': 'error',
                                'message': f'You are not assigned to "{location_obj.name}". Contact administrator.',
                                'error_type': 'not_assigned'
                            }, status=403)
                        
                        if not is_within_radius:
                            return JsonResponse({
                                'status': 'error',
                                'message': f'You must be within {float(location_obj.radius)}m of {location_obj.name}.',
                                'error_type': 'outside_radius',
                                'data': {
                                    'distance': round(distance_km * 1000, 2),
                                    'required_radius': float(location_obj.radius),
                                    'assigned_location': assigned_location_name,
                                    'actual_location': actual_location_name
                                }
                            }, status=400)
                    
                except Location.DoesNotExist:
                    logger.warning(f"Location {location_id} not found or inactive")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Location not found or inactive'
                    }, status=404)
            
            # CASE 2: No location_id provided
            else:
                logger.info("No location_id provided - GPS-only attendance")
                
                if location_restricted:
                    user_locations = UserLocation.objects.filter(
                        user=request.user
                    ).select_related('location')
                    
                    if not user_locations.exists():
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Location Restricted Mode: You must select a location to mark attendance.',
                            'error_type': 'no_location_assigned'
                        }, status=400)
                    
                    # Try to find nearby location
                    closest_location = None
                    closest_distance = float('inf')
                    
                    for user_loc in user_locations:
                        dist = haversine(
                            user_loc.location.latitude,
                            user_loc.location.longitude,
                            Decimal(latitude),
                            Decimal(longitude)
                        )
                        
                        if dist < closest_distance:
                            closest_distance = dist
                            closest_location = user_loc.location
                    
                    if closest_location and closest_distance <= (float(closest_location.radius) / 1000):
                        location_obj = closest_location
                        assigned_location_name = closest_location.name
                        distance_km = closest_distance
                        is_within_radius = True
                        logger.info(f"Auto-matched to {closest_location.name} ({closest_distance:.3f}km away)")
                    else:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'You are not within any assigned location radius.',
                            'error_type': 'outside_all_locations',
                            'data': {
                                'closest_location': closest_location.name if closest_location else None,
                                'distance_to_closest': round(closest_distance * 1000, 2) if closest_distance != float('inf') else None,
                                'actual_location': actual_location_name
                            }
                        }, status=400)
            
            # ==================== CREATE ATTENDANCE LOG ====================
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
            
            punch_type = 'CHECK_IN' if attendance_type == 'IN' else 'CHECK_OUT'
            status_code = 0 if attendance_type == 'IN' else 1
            
            attendance_log = AttendanceLog.objects.create(
                device=device,
                employee=employee,
                timestamp=timezone.now(),
                status_code=status_code,
                punch_type=punch_type,
                source_type='MB',
                user=request.user,
                location=location_obj,
                attendance_type=attendance_type,
                latitude=latitude,
                longitude=longitude,
                is_within_radius=is_within_radius,
                distance=distance_km,
                location_name=actual_location_name,  # ACTUAL address from geocoding
                device_info=device_info,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            success_message = 'Attendance marked successfully!'
            if assigned_location_name:
                if is_within_radius:
                    success_message += f' at {assigned_location_name}'
                else:
                    success_message += f' (Outside {assigned_location_name})'
            
            logger.info(
                f"✓ Attendance marked: user={request.user.username}, "
                f"employee={employee.employee_id}, type={attendance_type}, "
                f"assigned_location={assigned_location_name}, "
                f"actual_location={actual_location_name}, "
                f"distance={distance_km}km"
            )
            
            return JsonResponse({
                'status': 'success',
                'message': success_message,
                'data': {
                    'id': attendance_log.id,
                    'timestamp': attendance_log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'type': attendance_type,
                    'assigned_location': assigned_location_name,
                    'actual_location': actual_location_name,  # Address from geocoding API
                    'distance': round(distance_km * 1000, 2) if distance_km else None,
                    'is_within_radius': is_within_radius,
                    'location_restricted': location_restricted,
                    'api_provider': 'geocode.maps.co'
                }
            })
            
        except Exception as e:
            logger.exception(f"Error marking attendance: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred while marking attendance',
                'error_detail': str(e) if settings.DEBUG else None
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