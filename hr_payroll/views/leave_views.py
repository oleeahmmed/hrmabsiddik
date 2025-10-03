from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from ..models import LeaveApplication, LeaveBalance
from ..forms import LeaveApplicationForm


class LeaveListView(LoginRequiredMixin, ListView):
    model = LeaveApplication
    template_name = 'leave/leave_list.html'
    context_object_name = 'leaves'
    paginate_by = 20
    ordering = ['-start_date']

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee', 'leave_type')
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(employee__name__icontains=search) | qs.filter(employee__employee_id__icontains=search)
        
        # Filter by status if provided
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
            
        return qs


class LeaveDetailView(LoginRequiredMixin, DetailView):
    model = LeaveApplication
    template_name = 'leave/leave_detail.html'
    context_object_name = 'leave'


class LeaveCreateView(LoginRequiredMixin, CreateView):
    model = LeaveApplication
    template_name = 'leave/leave_form.html'
    form_class = LeaveApplicationForm
    success_url = reverse_lazy('zkteco:leave_list')


class LeaveUpdateView(LoginRequiredMixin, UpdateView):
    model = LeaveApplication
    template_name = 'leave/leave_form.html'
    form_class = LeaveApplicationForm
    success_url = reverse_lazy('zkteco:leave_list')


class LeaveDeleteView(LoginRequiredMixin, DeleteView):
    model = LeaveApplication
    template_name = 'leave/leave_confirm_delete.html'
    success_url = reverse_lazy('zkteco:leave_list')


class LeaveStatusChangeView(LoginRequiredMixin, View):
    """
    API endpoint to change leave application status (Approve/Reject/Pending)
    """
    
    def post(self, request, pk):
        try:
            leave = get_object_or_404(LeaveApplication, pk=pk)
            new_status = request.POST.get('status')
            
            # Validate status
            valid_statuses = ['P', 'A', 'R']
            if new_status not in valid_statuses:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid status'
                }, status=400)
            
            old_status = leave.status
            
            with transaction.atomic():
                # Update leave status
                leave.status = new_status
                leave.approved_by = request.user if new_status in ['A', 'R'] else None
                leave.updated_at = timezone.now()
                leave.save()
                
                # Calculate leave days
                leave_days = (leave.end_date - leave.start_date).days + 1
                
                # Update leave balance if status changed
                if new_status == 'A' and old_status != 'A':
                    # Approved: Deduct from leave balance
                    leave_balance, created = LeaveBalance.objects.get_or_create(
                        employee=leave.employee,
                        leave_type=leave.leave_type,
                        defaults={
                            'entitled_days': leave.leave_type.max_days,
                            'used_days': 0
                        }
                    )
                    leave_balance.used_days += leave_days
                    leave_balance.save()
                    
                elif old_status == 'A' and new_status != 'A':
                    # Was approved but now changed: Add back to leave balance
                    try:
                        leave_balance = LeaveBalance.objects.get(
                            employee=leave.employee,
                            leave_type=leave.leave_type
                        )
                        leave_balance.used_days -= leave_days
                        if leave_balance.used_days < 0:
                            leave_balance.used_days = 0
                        leave_balance.save()
                    except LeaveBalance.DoesNotExist:
                        pass
            
            # Status messages
            status_map = {
                'P': 'Pending',
                'A': 'Approved',
                'R': 'Rejected'
            }
            
            return JsonResponse({
                'success': True,
                'message': f'Leave application {status_map[new_status].lower()} successfully',
                'new_status': new_status,
                'status_label': status_map[new_status],
                'leave_id': leave.id
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)