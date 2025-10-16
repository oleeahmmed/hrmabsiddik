from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django import forms

from ..models import Company


# ==================== PERMISSION MIXINS ====================

class CompanyRequiredMixin(LoginRequiredMixin):
    """
    Ensures user has a company profile before accessing views
    """
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'profile') or not request.user.profile.company:
            messages.error(
                request,
                'You must be associated with a company to access this page. Please contact administrator.'
            )
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class CompanyFilterMixin(CompanyRequiredMixin):
    """
    Automatically filters queryset by user's company
    Includes subsidiary companies if applicable
    """
    
    def get_user_company(self):
        """Get the user's company from profile"""
        if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
            return self.request.user.profile.company
        return None
    
    def get_user_companies(self, include_subsidiaries=True):
        """
        Get user's company and all subsidiaries
        Returns a list of company IDs
        """
        user_company = self.get_user_company()
        if not user_company:
            return []
        
        if include_subsidiaries:
            companies = user_company.get_all_subsidiaries(include_self=True)
            return [c.id for c in companies]
        
        return [user_company.id]
    
    def filter_queryset_by_company(self, queryset, field_name='company'):
        """
        Filter queryset by user's company (including subsidiaries)
        """
        company_ids = self.get_user_companies(include_subsidiaries=True)
        if company_ids:
            filter_kwargs = {f'{field_name}__id__in': company_ids}
            queryset = queryset.filter(**filter_kwargs)
        return queryset
    
    def get_queryset(self):
        """Override to automatically filter by company"""
        queryset = super().get_queryset()
        return self.filter_queryset_by_company(queryset)


class AutoAssignOwnerMixin:
    """
    Automatically assigns owner and company to new objects
    """
    
    def form_valid(self, form):
        """Auto-assign owner and company before saving"""
        if not form.instance.pk:  # Only for new objects
            # Auto-assign owner
            if hasattr(form.instance, 'owner') and not form.instance.owner:
                form.instance.owner = self.request.user
            
            # Auto-assign company
            if hasattr(form.instance, 'company') and not form.instance.company:
                if hasattr(self.request.user, 'profile') and self.request.user.profile.company:
                    form.instance.company = self.request.user.profile.company
        
        return super().form_valid(form)


class CompanyOwnershipMixin(CompanyFilterMixin):
    """
    Ensures user can only access/modify objects from their company
    """
    
    def get_object(self, queryset=None):
        """Override to check company ownership"""
        obj = super().get_object(queryset)
        
        # Check if object belongs to user's company or subsidiaries
        if hasattr(obj, 'company'):
            company_ids = self.get_user_companies(include_subsidiaries=True)
            if obj.company.id not in company_ids:
                raise PermissionDenied("You don't have permission to access this object.")
        
        return obj


class CommonContextMixin:
    """Common context mixin for all views"""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add latest 3 records for form views
        if hasattr(self, 'model') and not isinstance(self, (ListView, DeleteView)):
            context['latest_records'] = self.model.objects.all()[:3]
        
        return context