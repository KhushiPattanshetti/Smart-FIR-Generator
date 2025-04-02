from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from .models import User, Station, Complaint, FIR, Transcription
from django.utils import timezone
from django.core.validators import FileExtensionValidator

class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )

class RegistrationForm(UserCreationForm):
    PROFILE_PICTURE_CHOICES = [
        ('avatar1.png', 'Avatar 1'),
        ('avatar2.png', 'Avatar 2'),
        ('avatar3.png', 'Avatar 3'),
        ('avatar4.png', 'Avatar 4'),
    ]
    
    profile_picture = forms.ChoiceField(
        choices=PROFILE_PICTURE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = User
        fields = ('name', 'email', 'role', 'badge_number', 'rank', 'profile_picture')
        
        # Remove 'police_station' from fields if it's not needed for all users
        # Or keep it if it's required for your application
        
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'badge_number': forms.TextInput(attrs={'class': 'form-control'}),
            'rank': forms.TextInput(attrs={'class': 'form-control'}),
            # 'police_station': forms.Select(attrs={'class': 'form-control'}),  # Only include if field exists
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only include if police_station field exists in User model
        if 'police_station' in self.fields:
            self.fields['police_station'].queryset = Station.objects.filter(status='Active')
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('name', 'email', 'phone', 'address', 'profile_picture', 'badge_number', 'rank')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
            'badge_number': forms.TextInput(attrs={'class': 'form-control'}),
            'rank': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({'class': 'form-control'})
        self.fields['new_password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['new_password2'].widget.attrs.update({'class': 'form-control'})

class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = ('name', 'station_code', 'address', 'city', 'state', 'pincode', 'phone', 'jurisdiction', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'station_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'jurisdiction': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

class ComplaintForm(forms.ModelForm):
    incident_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        initial=timezone.now
    )
    
    class Meta:
        model = Complaint
        fields = (
            'complainant_name', 'complainant_contact', 'complainant_address',
            'incident_date', 'incident_location', 'complaint_type', 
            'incident_description', 'suggested_sections', 'evidence_files'
        )
        widgets = {
            'complainant_name': forms.TextInput(attrs={'class': 'form-control'}),
            'complainant_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'complainant_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'incident_location': forms.TextInput(attrs={'class': 'form-control'}),
            'complaint_type': forms.Select(attrs={'class': 'form-control'}),
            'incident_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'suggested_sections': forms.TextInput(attrs={'class': 'form-control'}),
            'evidence_files': forms.FileInput(attrs={'class': 'form-control', 'multiple': True}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'evidence_files' in self.fields:
            self.fields['evidence_files'].validators.append(
                FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'mp4', 'mov'])
            )

class FIRForm(forms.ModelForm):
    date_registered = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        initial=timezone.now
    )
    
    class Meta:
        model = FIR
        fields = (
            'fir_number', 'date_registered', 'investigating_officer', 'complainant',
            'complainant_name', 'complainant_contact', 'accused_details', 
            'incident_details', 'sections_applied', 'status', 'remarks'
        )
        widgets = {
            'fir_number': forms.TextInput(attrs={'class': 'form-control'}),
            'investigating_officer': forms.Select(attrs={'class': 'form-control'}),
            'complainant': forms.Select(attrs={'class': 'form-control'}),
            'complainant_name': forms.TextInput(attrs={'class': 'form-control'}),
            'complainant_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'accused_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'incident_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'sections_applied': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'investigating_officer' in self.fields:
            self.fields['investigating_officer'].queryset = User.objects.filter(role='officer', status='Active')
        if 'complainant' in self.fields:
            self.fields['complainant'].queryset = User.objects.filter(role='citizen', status='Active')

class TranscriptionForm(forms.ModelForm):
    audio_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg'])]
    )
    
    class Meta:
        model = Transcription
        fields = ('original_text', 'audio_file', 'language')
        widgets = {
            'original_text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Or paste your text here for IPC section suggestions'
            }),
            'language': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        original_text = cleaned_data.get('original_text')
        audio_file = cleaned_data.get('audio_file')
        
        if not original_text and not audio_file:
            raise ValidationError("Either text or audio file must be provided.")
        
        return cleaned_data