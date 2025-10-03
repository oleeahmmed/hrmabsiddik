from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib import messages
from ..models import AttendanceProcessorConfiguration, Shift
from ..forms import AttendanceProcessorConfigurationForm


class AttendanceConfigListView(LoginRequiredMixin, ListView):
    """List all attendance processor configurations"""
    model = AttendanceProcessorConfiguration
    template_name = 'attendance_config/config_list.html'
    context_object_name = 'configs'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('company', 'created_by', 'dynamic_shift_fallback_shift')
        
        # Filter by company if user has company
        if hasattr(self.request.user, 'company'):
            qs = qs.filter(company=self.request.user.company)
        
        # Search functionality
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
            
        return qs


class AttendanceConfigDetailView(LoginRequiredMixin, DetailView):
    """View details of a specific attendance processor configuration"""
    model = AttendanceProcessorConfiguration
    template_name = 'attendance_config/config_detail.html'
    context_object_name = 'config'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.object
        
        # Get weekend days as readable text
        weekend_days = []
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if config.weekend_monday: weekend_days.append('Monday')
        if config.weekend_tuesday: weekend_days.append('Tuesday')
        if config.weekend_wednesday: weekend_days.append('Wednesday')
        if config.weekend_thursday: weekend_days.append('Thursday')
        if config.weekend_friday: weekend_days.append('Friday')
        if config.weekend_saturday: weekend_days.append('Saturday')
        if config.weekend_sunday: weekend_days.append('Sunday')
        
        context['weekend_days_text'] = ', '.join(weekend_days) if weekend_days else 'None'
        
        return context


class AttendanceConfigCreateView(LoginRequiredMixin, CreateView):
    """Create a new attendance processor configuration"""
    model = AttendanceProcessorConfiguration
    template_name = 'attendance_config/config_form.html'
    form_class = AttendanceProcessorConfigurationForm
    success_url = reverse_lazy('zkteco:config_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        # Set company from user if available
        if hasattr(self.request.user, 'company'):
            form.instance.company = self.request.user.company
        
        messages.success(self.request, f'Configuration "{form.instance.name}" created successfully!')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if hasattr(self.request.user, 'company'):
            kwargs['company'] = self.request.user.company
        return kwargs


class AttendanceConfigUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing attendance processor configuration"""
    model = AttendanceProcessorConfiguration
    template_name = 'attendance_config/config_form.html'
    form_class = AttendanceProcessorConfigurationForm
    success_url = reverse_lazy('zkteco:config_list')

    def form_valid(self, form):
        messages.success(self.request, f'Configuration "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if hasattr(self.request.user, 'company'):
            kwargs['company'] = self.request.user.company
        return kwargs


class AttendanceConfigDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an attendance processor configuration"""
    model = AttendanceProcessorConfiguration
    template_name = 'attendance_config/config_confirm_delete.html'
    success_url = reverse_lazy('zkteco:config_list')

    def delete(self, request, *args, **kwargs):
        config = self.get_object()
        messages.success(request, f'Configuration "{config.name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)


class AttendanceConfigToggleStatusView(LoginRequiredMixin, View):
    """Toggle active/inactive status of a configuration"""
    
    def post(self, request, pk):
        try:
            config = get_object_or_404(AttendanceProcessorConfiguration, pk=pk)
            
            with transaction.atomic():
                # Toggle status
                config.is_active = not config.is_active
                config.save()
            
            status_text = "activated" if config.is_active else "deactivated"
            
            return JsonResponse({
                'success': True,
                'message': f'Configuration {status_text} successfully',
                'is_active': config.is_active
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


class AttendanceConfigDuplicateView(LoginRequiredMixin, View):
    """Duplicate an existing configuration"""
    
    def post(self, request, pk):
        try:
            original_config = get_object_or_404(AttendanceProcessorConfiguration, pk=pk)
            
            with transaction.atomic():
                # Create a duplicate
                new_config = AttendanceProcessorConfiguration.objects.get(pk=original_config.pk)
                new_config.pk = None
                new_config.name = f"{original_config.name} (Copy)"
                new_config.is_active = False
                new_config.created_by = request.user
                new_config.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Configuration duplicated successfully',
                'new_id': new_config.id,
                'redirect_url': reverse_lazy('zkteco:config_detail', kwargs={'pk': new_config.pk})
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)