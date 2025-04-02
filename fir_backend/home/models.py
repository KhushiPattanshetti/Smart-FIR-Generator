from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('police_officer', 'Police Officer'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='police_officer')
    station = models.ForeignKey('Station', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Station(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    contact_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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
    assigned_team = models.ManyToManyField(User, related_name='team_firs', blank=True)
    priority = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], default='medium')
    protection_required = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.fir_number} - {self.complainant_name}"
    
    def get_status_class(self):
        return {
            'draft': 'secondary',
            'submitted': 'info',
            'under_investigation': 'warning',
            'closed': 'success',
            'rejected': 'danger'
        }.get(self.status, 'secondary')

class Evidence(models.Model):
    EVIDENCE_TYPES = [
        ('photo', 'Photograph'),
        ('video', 'Video Recording'),
        ('document', 'Document'),
        ('audio', 'Audio Recording'),
        ('other', 'Other'),
    ]
    
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='evidence')
    file = models.FileField(upload_to='evidence/%Y/%m/%d/')
    description = models.TextField()
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    upload_date = models.DateTimeField(auto_now_add=True)
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPES)
    transcription = models.TextField(blank=True, null=True)
    transcription_language = models.CharField(max_length=10, blank=True, null=True)
    chain_of_custody = models.JSONField(default=list)
    
    def __str__(self):
        return f"Evidence {self.id} for {self.fir.fir_number}"
    
    def save(self, *args, **kwargs):
        # Auto-detect evidence type from file extension if not set
        if not self.evidence_type:
            ext = self.file.name.split('.')[-1].lower()
            if ext in ('jpg', 'jpeg', 'png', 'gif'):
                self.evidence_type = 'photo'
            elif ext in ('mp4', 'mov', 'avi'):
                self.evidence_type = 'video'
            elif ext in ('mp3', 'wav', 'm4a', 'ogg'):
                self.evidence_type = 'audio'
            elif ext in ('pdf', 'doc', 'docx'):
                self.evidence_type = 'document'
        super().save(*args, **kwargs)

class Witness(models.Model):
    PROTECTION_STATUS = [
        ('none', 'No Protection'),
        ('basic', 'Basic Protection'),
        ('high', 'High Security'),
    ]
    
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='witnesses')
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=20)
    address = models.TextField()
    statement = models.TextField()
    protection_status = models.CharField(max_length=20, choices=PROTECTION_STATUS, default='none')
    
    def __str__(self):
        return f"{self.name} (Witness for {self.fir.fir_number})"

class LegalSuggestion(models.Model):
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='legal_suggestions')
    ipc_section = models.CharField(max_length=20)
    crpc_section = models.CharField(max_length=20, blank=True, null=True)
    act_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    confidence_score = models.FloatField(default=0.0)
    
    def __str__(self):
        return f"Legal Suggestion: {self.ipc_section} for {self.fir.fir_number}"

class InvestigationNote(models.Model):
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='investigation_notes')
    note = models.TextField()
    translated_text = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note by {self.created_by.username} on {self.created_at}"

class CourtHearing(models.Model):
    fir = models.ForeignKey(FIR, on_delete=models.CASCADE, related_name='court_hearings')
    hearing_date = models.DateTimeField()
    purpose = models.TextField()
    outcome = models.TextField(blank=True, null=True)
    next_hearing_date = models.DateTimeField(blank=True, null=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['hearing_date']
    
    def __str__(self):
        return f"Hearing on {self.hearing_date} for {self.fir.fir_number}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=200)
    link = models.CharField(max_length=100)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"