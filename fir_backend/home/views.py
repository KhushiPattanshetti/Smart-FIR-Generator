import os
import logging
import json
import csv
import tempfile
import requests
from datetime import datetime, timedelta
import uuid
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, F
from django.template.loader import render_to_string
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from xhtml2pdf import pisa

from .models import User, Station, FIR, LegalSuggestion, Evidence, Witness, CourtHearing, Notification
from .serializers import (
    UserSerializer,
    StationSerializer,
    FIRSerializer,
    LegalSuggestionSerializer,
    ReportSerializer
)

logger = logging.getLogger(__name__)

# Speech-to-text service URL
SPEECH_TO_TEXT_SERVICE_URL = "http://localhost:5001/transcribe"

# Utility Functions
def is_admin(user):
    return user.role == 'admin'

def is_police_officer(user):
    return user.role == 'police_officer'

def can_access_fir(user, fir):
    """Check if user has permission to access this FIR"""
    if is_admin(user):
        return True
    if is_police_officer(user):
        return fir.police_officer == user or fir.assigned_team.filter(pk=user.pk).exists()
    return False

def validate_user_role(user, allowed_roles):
    if user.role not in allowed_roles:
        raise PermissionDenied("You don't have permission to access this resource")

def generate_fir_number():
    return f"FIR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def generate_pdf_report(html_content):
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_content.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None

def validate_status_change(old_status, new_status):
    """Validate FIR status transitions"""
    workflow = {
        'draft': ['submitted'],
        'submitted': ['under_investigation', 'rejected'],
        'under_investigation': ['closed', 'rejected'],
        'rejected': ['submitted'],
        'closed': []  # Once closed, no further changes
    }
    return new_status in workflow.get(old_status, [])

def send_fir_notification(fir, action, actor):
    """Send notifications about FIR updates"""
    recipients = set()
    
    # Always notify the primary officer if not the actor
    if fir.police_officer != actor:
        recipients.add(fir.police_officer)
    
    # Notify assigned team members
    for member in fir.assigned_team.all():
        if member != actor:
            recipients.add(member)
    
    # Notify admins for certain actions
    if action in ['rejected', 'status_change', 'overdue']:
        admins = User.objects.filter(role='admin')
        recipients.update(admins)
    
    # Create notifications
    for recipient in recipients:
        Notification.objects.create(
            user=recipient,
            message=f"FIR {fir.fir_number}: {action.replace('_', ' ')} by {actor.username}",
            link=f"/firs/{fir.pk}/"
        )

# Authentication Views
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if is_admin(user):
                return redirect('admin_dashboard')
            else:
                return redirect('officer_dashboard')
        else:
            return render(request, 'auth/login.html', {'error': 'Invalid credentials'})
    
    return render(request, 'auth/login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

# Admin Dashboard
@login_required
def admin_dashboard(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    # Get stats for dashboard
    total_stations = Station.objects.count()
    total_officers = User.objects.filter(role='police_officer').count()
    total_firs = FIR.objects.count()
    recent_firs = FIR.objects.order_by('-created_at')[:5]
    
    return render(request, 'admin/dashboard.html', {
        'total_stations': total_stations,
        'total_officers': total_officers,
        'total_firs': total_firs,
        'recent_firs': recent_firs
    })

# Admin - User & Station Management
@login_required
def station_list_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    stations = Station.objects.all()
    return render(request, 'admin/stations/list.html', {'stations': stations})

@login_required
def station_create_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    if request.method == 'POST':
        name = request.POST.get('name')
        location = request.POST.get('location')
        contact_number = request.POST.get('contact_number')
        
        Station.objects.create(
            name=name,
            location=location,
            contact_number=contact_number
        )
        return redirect('station_list')
    
    return render(request, 'admin/stations/create.html')

@login_required
def station_edit_view(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    
    station = get_object_or_404(Station, pk=pk)
    
    if request.method == 'POST':
        station.name = request.POST.get('name')
        station.location = request.POST.get('location')
        station.contact_number = request.POST.get('contact_number')
        station.save()
        return redirect('station_list')
    
    return render(request, 'admin/stations/edit.html', {'station': station})

@login_required
def station_delete_view(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    
    station = get_object_or_404(Station, pk=pk)
    station.delete()
    return redirect('station_list')

@login_required
def user_list_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    users = User.objects.all()
    return render(request, 'admin/users/list.html', {'users': users})

@login_required
def user_create_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role')
        station_id = request.POST.get('station')
        
        user = User.objects.create_user(
            username=username,
            password=password,
            role=role
        )
        
        if station_id:
            station = Station.objects.get(pk=station_id)
            user.station = station
            user.save()
        
        return redirect('user_list')
    
    stations = Station.objects.all()
    return render(request, 'admin/users/create.html', {'stations': stations})

@login_required
def user_edit_view(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.role = request.POST.get('role')
        station_id = request.POST.get('station')
        
        if station_id:
            station = Station.objects.get(pk=station_id)
            user.station = station
        else:
            user.station = None
        
        user.save()
        return redirect('user_list')
    
    stations = Station.objects.all()
    return render(request, 'admin/users/edit.html', {
        'user': user,
        'stations': stations
    })

@login_required
def user_delete_view(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    
    user = get_object_or_404(User, pk=pk)
    user.delete()
    return redirect('user_list')

# Admin - FIR Management
@login_required
def admin_fir_list_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    status_filter = request.GET.get('status')
    station_filter = request.GET.get('station')
    officer_filter = request.GET.get('officer')
    
    firs = FIR.objects.all()
    
    if status_filter:
        firs = firs.filter(status=status_filter)
    if station_filter:
        firs = firs.filter(station_id=station_filter)
    if officer_filter:
        firs = firs.filter(police_officer_id=officer_filter)
    
    stations = Station.objects.all()
    officers = User.objects.filter(role='police_officer')
    
    return render(request, 'admin/firs/list.html', {
        'firs': firs.order_by('-created_at'),
        'stations': stations,
        'officers': officers,
        'current_filters': {
            'status': status_filter,
            'station': station_filter,
            'officer': officer_filter
        }
    })

@login_required
def admin_fir_detail_view(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    
    fir = get_object_or_404(FIR, pk=pk)
    officers = User.objects.filter(role='police_officer')
    
    if request.method == 'POST':
        # Handle FIR reassignment
        officer_id = request.POST.get('officer_id')
        if officer_id:
            try:
                new_officer = User.objects.get(pk=officer_id, role='police_officer')
                fir.police_officer = new_officer
                fir.save()
                send_fir_notification(fir, 'reassigned', request.user)
            except User.DoesNotExist:
                pass
        
        return redirect('admin_fir_detail', pk=pk)
    
    return render(request, 'admin/firs/detail.html', {
        'fir': fir,
        'officers': officers
    })

# Admin - Reports
@login_required
def report_generate_view(request):
    if not is_admin(request.user):
        raise PermissionDenied
    
    report_type = request.GET.get('type', 'monthly')
    format = request.GET.get('format', 'html')
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    if report_type == 'monthly':
        data = FIR.objects.filter(
            created_at__range=(start_date, end_date)
        ).values('station__name').annotate(
            total_firs=Count('id'),
            draft_firs=Count('id', filter=Q(status='draft')),
            submitted_firs=Count('id', filter=Q(status='submitted')),
            investigating_firs=Count('id', filter=Q(status='under_investigation')),
            closed_firs=Count('id', filter=Q(status='closed'))
        )
        template = 'admin/reports/monthly.html'
    elif report_type == 'officer_performance':
        data = User.objects.filter(role='police_officer').annotate(
            total_firs=Count('filed_firs'),
            closed_firs=Count('filed_firs', filter=Q(filed_firs__status='closed'))
        )
        template = 'admin/reports/officer_performance.html'
    elif report_type == 'crime_trends':
        data = FIR.objects.values('incident_location').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        template = 'admin/reports/crime_trends.html'
    else:
        return redirect('report_generate')
    
    if format == 'pdf':
        html = render_to_string(template, {'data': data, 'start_date': start_date, 'end_date': end_date})
        pdf = generate_pdf_report(html)
        
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report_type}_report.pdf"'
            return response
        return redirect('report_generate')
    
    elif format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report.csv"'
        
        writer = csv.writer(response)
        if report_type == 'monthly':
            writer.writerow(['Station', 'Total FIRs', 'Draft', 'Submitted', 'Investigating', 'Closed'])
            for item in data:
                writer.writerow([
                    item['station__name'],
                    item['total_firs'],
                    item['draft_firs'],
                    item['submitted_firs'],
                    item['investigating_firs'],
                    item['closed_firs']
                ])
        elif report_type == 'officer_performance':
            writer.writerow(['Officer', 'Total FIRs', 'Closed FIRs'])
            for officer in data:
                writer.writerow([
                    officer.username,
                    officer.total_firs,
                    officer.closed_firs
                ])
        
        return response
    
    return render(request, template, {
        'data': data,
        'start_date': start_date,
        'end_date': end_date,
        'report_type': report_type
    })

# Police Officer Dashboard
@login_required
def officer_dashboard(request):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    total_firs = FIR.objects.filter(
        Q(police_officer=request.user) | Q(assigned_team=request.user)
    ).distinct().count()
    
    pending_firs = FIR.objects.filter(
        Q(police_officer=request.user) | Q(assigned_team=request.user),
        status__in=['draft', 'submitted', 'under_investigation']
    ).distinct().count()
    
    recent_firs = FIR.objects.filter(
        Q(police_officer=request.user) | Q(assigned_team=request.user)
    ).distinct().order_by('-created_at')[:5]
    
    overdue_firs = FIR.objects.filter(
        Q(police_officer=request.user) | Q(assigned_team=request.user),
        status='under_investigation',
        investigation_deadline__lt=timezone.now()
    ).distinct().count()
    
    return render(request, 'officer/dashboard.html', {
        'total_firs': total_firs,
        'pending_firs': pending_firs,
        'recent_firs': recent_firs,
        'overdue_firs': overdue_firs
    })

# Police Officer - FIR Management
@login_required
def officer_fir_list_view(request):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    status_filter = request.GET.get('status')
    firs = FIR.objects.filter(
        Q(police_officer=request.user) | Q(assigned_team=request.user)
    ).distinct()
    
    if status_filter:
        firs = firs.filter(status=status_filter)
    
    return render(request, 'officer/firs/list.html', {
        'firs': firs.order_by('-created_at'),
        'current_filter': status_filter
    })

@login_required
def officer_fir_create_view(request):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    if request.method == 'POST':
        fir_number = generate_fir_number()
        complainant_name = request.POST.get('complainant_name')
        complainant_contact = request.POST.get('complainant_contact')
        incident_description = request.POST.get('incident_description')
        incident_date = request.POST.get('incident_date')
        incident_location = request.POST.get('incident_location')
        
        fir = FIR.objects.create(
            fir_number=fir_number,
            complainant_name=complainant_name,
            complainant_contact=complainant_contact,
            incident_description=incident_description,
            incident_date=incident_date,
            incident_location=incident_location,
            police_officer=request.user,
            station=request.user.station,
            status='draft'
        )
        
        return redirect('officer_fir_detail', pk=fir.pk)
    
    return render(request, 'officer/firs/create.html')

@login_required
def officer_fir_detail_view(request, pk):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    fir = get_object_or_404(FIR, pk=pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        # Handle status update
        new_status = request.POST.get('status')
        if new_status in dict(FIR.STATUS_CHOICES).keys() and validate_status_change(fir.status, new_status):
            fir.status = new_status
            fir.save()
            send_fir_notification(fir, 'status_change', request.user)
        
        # Handle legal suggestion override
        suggestion_id = request.POST.get('suggestion_id')
        if suggestion_id:
            try:
                suggestion = LegalSuggestion.objects.get(pk=suggestion_id, fir=fir)
                suggestion.ipc_section = request.POST.get('ipc_section')
                suggestion.crpc_section = request.POST.get('crpc_section')
                suggestion.act_name = request.POST.get('act_name')
                suggestion.save()
            except LegalSuggestion.DoesNotExist:
                pass
        
        return redirect('officer_fir_detail', pk=pk)
    
    return render(request, 'officer/firs/detail.html', {
        'fir': fir,
        'supported_audio_types': ['wav', 'mp3', 'm4a', 'ogg']
    })

@login_required
def officer_fir_update_view(request, pk):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    fir = get_object_or_404(FIR, pk=pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        fir.complainant_name = request.POST.get('complainant_name')
        fir.complainant_contact = request.POST.get('complainant_contact')
        fir.incident_description = request.POST.get('incident_description')
        fir.incident_date = request.POST.get('incident_date')
        fir.incident_location = request.POST.get('incident_location')
        fir.save()
        
        return redirect('officer_fir_detail', pk=pk)
    
    return render(request, 'officer/firs/update.html', {'fir': fir})

# Team Management
@login_required
def assign_team_view(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        team_member_ids = request.POST.getlist('team_members')
        fir.assigned_team.clear()
        for member_id in team_member_ids:
            try:
                officer = User.objects.get(pk=member_id, role='police_officer')
                fir.assigned_team.add(officer)
            except User.DoesNotExist:
                pass
        fir.save()
        send_fir_notification(fir, 'team_updated', request.user)
        return redirect('officer_fir_detail', pk=fir.pk)
    
    available_officers = User.objects.filter(
        role='police_officer',
        station=fir.station
    ).exclude(pk=fir.police_officer.pk)
    
    return render(request, 'officer/firs/assign_team.html', {
        'fir': fir,
        'officers': available_officers
    })

# Evidence Management
@login_required
def manage_evidence_view(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    evidence_list = Evidence.objects.filter(fir=fir).order_by('-upload_date')
    return render(request, 'officer/firs/manage_evidence.html', {
        'fir': fir,
        'evidence_list': evidence_list
    })

@login_required
@csrf_exempt
def upload_evidence_view(request, fir_pk):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST' and request.FILES.get('evidence_file'):
        evidence_file = request.FILES['evidence_file']
        description = request.POST.get('description', '')
        evidence_type = request.POST.get('evidence_type', 'other')
        
        evidence = Evidence.objects.create(
            fir=fir,
            file=evidence_file,
            description=description,
            uploaded_by=request.user,
            evidence_type=evidence_type
        )
        
        return JsonResponse({
            'status': 'success',
            'evidence_id': evidence.id,
            'evidence_type': evidence.get_evidence_type_display()
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Audio Transcription
@login_required
@csrf_exempt
def transcribe_audio_view(request, fir_pk=None):
    """Handle audio file uploads for transcription"""
    if request.method == 'POST' and request.FILES.get('audio_file'):
        audio_file = request.FILES['audio_file']
        language = request.POST.get('language', 'en-US')
        
        # Save temporarily
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, audio_file.name)
        
        with open(temp_path, 'wb+') as destination:
            for chunk in audio_file.chunks():
                destination.write(chunk)
        
        # Call the speech-to-text service
        try:
            files = {'audio': open(temp_path, 'rb')}
            data = {'language': language}
            response = requests.post(SPEECH_TO_TEXT_SERVICE_URL, files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                
                # If FIR pk is provided, save to FIR record
                if fir_pk:
                    fir = get_object_or_404(FIR, pk=fir_pk)
                    if not can_access_fir(request.user, fir):
                        raise PermissionDenied
                    
                    # Create an Evidence record for the audio
                    evidence = Evidence.objects.create(
                        fir=fir,
                        file=audio_file,
                        description="Audio statement transcription",
                        uploaded_by=request.user,
                        evidence_type='audio',
                        transcription=result['original_text'],
                        transcription_language=language
                    )
                    
                    # Add transcription to FIR notes
                    fir.investigation_notes.create(
                        note=f"Audio transcription: {result['original_text']}",
                        translated_text=result['translated_text'],
                        created_by=request.user
                    )
                    
                    return JsonResponse({
                        'status': 'success',
                        'transcription': result['original_text'],
                        'translation': result['translated_text'],
                        'evidence_id': evidence.id
                    })
                
                return JsonResponse(result)
            else:
                return JsonResponse({'error': 'Transcription failed'}, status=400)
                
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
            
        finally:
            # Clean up temp files
            if os.path.exists(temp_path):
                os.remove(temp_path)
            os.rmdir(temp_dir)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Legal Suggestions
@login_required
def generate_legal_suggestions_view(request, fir_pk):
    if not is_police_officer(request.user):
        raise PermissionDenied
    
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    # In a real implementation, this would call your AI service
    # For now, we'll mock the response
    mock_suggestions = [
        {
            'ipc_section': 'IPC 379',
            'description': 'Punishment for theft',
            'confidence_score': 0.85
        },
        {
            'ipc_section': 'IPC 34',
            'description': 'Acts done by several persons in furtherance of common intention',
            'confidence_score': 0.72
        }
    ]
    
    # Clear existing suggestions
    LegalSuggestion.objects.filter(fir=fir).delete()
    
    # Create new suggestions
    for suggestion in mock_suggestions:
        LegalSuggestion.objects.create(
            fir=fir,
            ipc_section=suggestion['ipc_section'],
            crpc_section=None,
            act_name="Indian Penal Code",
            confidence_score=suggestion['confidence_score']
        )
    
    return redirect('officer_fir_detail', pk=fir_pk)

# Witness Management
@login_required
def manage_witnesses_view(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        name = request.POST.get('name')
        contact = request.POST.get('contact')
        address = request.POST.get('address')
        statement = request.POST.get('statement')
        protection_status = request.POST.get('protection_status', 'none')
        
        Witness.objects.create(
            fir=fir,
            name=name,
            contact=contact,
            address=address,
            statement=statement,
            protection_status=protection_status
        )
        return redirect('manage_witnesses', fir_pk=fir.pk)
    
    witnesses = Witness.objects.filter(fir=fir)
    return render(request, 'officer/firs/manage_witnesses.html', {
        'fir': fir,
        'witnesses': witnesses
    })

# Court Hearings
@login_required
def court_hearings_view(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        hearing_date = request.POST.get('hearing_date')
        purpose = request.POST.get('purpose')
        
        if hearing_date and purpose:
            CourtHearing.objects.create(
                fir=fir,
                hearing_date=hearing_date,
                purpose=purpose,
                added_by=request.user
            )
            return redirect('court_hearings', fir_pk=fir.pk)
    
    hearings = CourtHearing.objects.filter(fir=fir).order_by('hearing_date')
    return render(request, 'officer/firs/court_hearings.html', {
        'fir': fir,
        'hearings': hearings
    })

# Charge Sheet Generation
@login_required
def generate_charge_sheet(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if fir.status != 'under_investigation':
        return JsonResponse({'error': 'Charge sheet can only be generated for cases under investigation'}, status=400)
    
    legal_suggestions = LegalSuggestion.objects.filter(fir=fir)
    evidence = Evidence.objects.filter(fir=fir)
    witnesses = Witness.objects.filter(fir=fir)
    
    context = {
        'fir': fir,
        'legal_suggestions': legal_suggestions,
        'evidence': evidence,
        'witnesses': witnesses,
        'officer': request.user
    }
    
    if request.GET.get('format') == 'pdf':
        html = render_to_string('officer/firs/charge_sheet_pdf.html', context)
        pdf = generate_pdf_report(html)
        
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="charge_sheet_{fir.fir_number}.pdf"'
            return response
    
    return render(request, 'officer/firs/charge_sheet.html', context)

# Notifications
@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]
    return render(request, 'notifications/list.html', {
        'notifications': notifications
    })

@login_required
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.read = True
    notification.save()
    return redirect(notification.link if notification.link else 'notifications')

# Dashboard Analytics
@login_required
def dashboard_analytics(request):
    if is_admin(request.user):
        # Admin analytics
        stations = Station.objects.annotate(
            total_firs=Count('firs'),
            pending_firs=Count('firs', filter=Q(firs__status__in=['submitted', 'under_investigation'])),
            overdue_firs=Count('firs', filter=Q(
                firs__status='under_investigation',
                firs__investigation_deadline__lt=timezone.now()
            ))
        )

        officers = User.objects.filter(role='police_officer').annotate(
            case_load=Count('filed_firs', filter=Q(filed_firs__status__in=['submitted', 'under_investigation'])),
            closed_cases=Count('filed_firs', filter=Q(filed_firs__status='closed'))
        )  # <-- Closing parenthesis added here

        return render(request, 'admin/analytics.html', {
            'stations': stations,
            'officers': officers
        })
    else:
        # Officer analytics
        officer = request.user
        firs_by_status = FIR.objects.filter(
            Q(police_officer=officer) | Q(assigned_team=officer)
        ).values('status').annotate(count=Count('id'))

        overdue_firs = FIR.objects.filter(
            Q(police_officer=officer) | Q(assigned_team=officer),
            status='under_investigation',
            investigation_deadline__lt=timezone.now()
        ).count()

        return render(request, 'officer/analytics.html', {
            'firs_by_status': firs_by_status,
            'overdue_firs': overdue_firs
        })
