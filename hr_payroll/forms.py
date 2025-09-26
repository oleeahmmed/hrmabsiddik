# zkteco/forms.py
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from .models import ZkDevice

class ZkDeviceForm(forms.ModelForm):
    """Form for adding/editing ZKTeco devices"""
    
    # IP address validator
    ip_validator = RegexValidator(
        regex=r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        message=_('Enter a valid IP address.')
    )
    
    class Meta:
        model = ZkDevice
        fields = ['name', 'ip_address', 'port', 'password', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': 'Enter device name (e.g., Main Entrance)',
                'required': True
            }),
            'ip_address': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': '192.168.1.100',
                'pattern': r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
                'title': 'Enter a valid IP address',
                'required': True
            }),
            'port': forms.NumberInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'min': 1,
                'max': 65535,
                'placeholder': '4370 (default)',
                'value': 4370
            }),
            'password': forms.TextInput(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'placeholder': 'Leave empty if no password (default: 0)',
                'autocomplete': 'new-password'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
                'rows': 3,
                'placeholder': 'Optional description about device location, purpose, etc.'
            })
        }
        labels = {
            'name': _('Device Name'),
            'ip_address': _('IP Address'),
            'port': _('Port'),
            'password': _('Device Password'),
            'description': _('Description')
        }
        help_texts = {
            'name': _('A descriptive name for the device (e.g., "Main Office Entrance")'),
            'ip_address': _('The IP address of the ZKTeco device on your network'),
            'port': _('Communication port (default: 4370)'),
            'password': _('Device password if set (leave empty for no password)'),
            'description': _('Optional notes about device location or purpose')
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add IP address validator
        self.fields['ip_address'].validators.append(self.ip_validator)
        
        # Set default port if not provided
        if not self.instance.pk:
            self.fields['port'].initial = 4370
    
    def clean_ip_address(self):
        """Validate IP address format"""
        ip_address = self.cleaned_data.get('ip_address')
        
        if ip_address:
            # Split IP and validate each octet
            octets = ip_address.split('.')
            if len(octets) != 4:
                raise forms.ValidationError(_('Invalid IP address format.'))
            
            for octet in octets:
                try:
                    num = int(octet)
                    if not 0 <= num <= 255:
                        raise forms.ValidationError(_('Each IP address octet must be between 0 and 255.'))
                except ValueError:
                    raise forms.ValidationError(_('IP address must contain only numbers and dots.'))
        
        return ip_address
    
    def clean_port(self):
        """Validate port number"""
        port = self.cleaned_data.get('port')
        
        if port is not None:
            if not 1 <= port <= 65535:
                raise forms.ValidationError(_('Port number must be between 1 and 65535.'))
        
        return port
    
    def clean_password(self):
        """Clean password field"""
        password = self.cleaned_data.get('password')
        
        # Convert empty string to None for consistency
        if password == '':
            return None
        
        return password
    
    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        ip_address = cleaned_data.get('ip_address')
        
        # Check for duplicate IP address (excluding current instance)
        if ip_address:
            existing_device = ZkDevice.objects.filter(ip_address=ip_address)
            if self.instance.pk:
                existing_device = existing_device.exclude(pk=self.instance.pk)
            
            if existing_device.exists():
                raise forms.ValidationError({
                    'ip_address': _('A device with this IP address already exists.')
                })
        
        return cleaned_data

class LoginForm(forms.Form):
    """Custom login form"""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
            'placeholder': 'Enter your username',
            'autocomplete': 'username',
            'required': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full rounded-lg border-gray-300 focus:ring-2 focus:ring-primary focus:border-primary',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
            'required': True
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary focus:ring-primary focus:ring-offset-0'
        })
    )