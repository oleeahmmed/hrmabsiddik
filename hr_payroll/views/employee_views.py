from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from ..models import Employee
from ..forms import EmployeeForm


class EmployeeListView(LoginRequiredMixin, ListView):
    model = Employee
    template_name = 'employee/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 20
    ordering = ['employee_id']

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(employee_id__icontains=search)
        return queryset


class EmployeeDetailView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = 'employee/employee_detail.html'
    context_object_name = 'employee'


class EmployeeCreateView(LoginRequiredMixin, CreateView):
    model = Employee
    template_name = 'employee/employee_form.html'
    form_class = EmployeeForm
    success_url = reverse_lazy('zkteco:employee_list')


class EmployeeUpdateView(LoginRequiredMixin, UpdateView):
    model = Employee
    template_name = 'employee/employee_form.html'
    form_class = EmployeeForm
    success_url = reverse_lazy('zkteco:employee_list')


class EmployeeDeleteView(LoginRequiredMixin, DeleteView):
    model = Employee
    template_name = 'employee/employee_confirm_delete.html'
    success_url = reverse_lazy('zkteco:employee_list')

