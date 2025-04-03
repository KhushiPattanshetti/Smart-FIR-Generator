from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import MinLengthValidator

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('police_officer', 'Police Officer'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    station = models.ForeignKey('Station', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Station(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    contact_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class FIR(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_investigation', 'Under Investigation'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
    ]
    
    fir_number = models.CharField(max_length=50, unique=True)
    complainant_name = models.CharField(max_length=100)
    complainant_contact = models.CharField(max_length=20)
    incident_description = models.TextField()
    incident_date = models.DateField()
    incident_location = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    police_officer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='filed_firs')
    station = models.ForeignKey(Station, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    investigation_deadline = models.DateField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "First Information Report"
        verbose_name_plural = "First Information Reports"
    
    def __str__(self):
        return f"{self.fir_number} - {self.complainant_name} ({self.get_status_display()})"
    
    def get_status_class(self):
        status_classes = {
            'draft': 'secondary',
            'submitted': 'info',
            'under_investigation': 'warning',
            'closed': 'success',
            'rejected': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

class LegalSuggestion(models.Model):
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='legal_suggestions')
    ipc_section = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    confidence_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.ipc_section} for {self.fir.fir_number}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True, null=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.user.username}"