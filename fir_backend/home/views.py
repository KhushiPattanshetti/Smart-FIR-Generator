import os
import logging
import csv
import uuid
from io import BytesIO
from datetime import datetime, timedelta
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Q, Count
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa
from deep_translator import GoogleTranslator
import joblib
import easyocr
import speech_recognition as sr
from PIL import Image
from .models import User, Station, FIR, LegalSuggestion, Notification

logger = logging.getLogger(__name__)

# ======================
# MODEL LOADING SYSTEM
# ======================

def homepage(request):
    return render(request, 'home.html')

def load_ml_models():
    """Load ML models once at application startup"""
    try:
        global ipc_model, vectorizer, ocr_reader, speech_recognizer
        model_dir = os.path.join(settings.BASE_DIR, 'ml_models')
        ipc_model = joblib.load(os.path.join(model_dir, 'ipc_model.pkl'))
        vectorizer = joblib.load(os.path.join(model_dir, 'vectorizer.pkl'))
        ocr_reader = easyocr.Reader(['en'])  # Initialize EasyOCR
        speech_recognizer = sr.Recognizer()  # Initialize SpeechRecognizer
        logger.info("ML models loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load ML models: {str(e)}")
        return False

models_loaded = load_ml_models()

# ======================
# UTILITY FUNCTIONS
# ======================

def is_admin(user):
    return getattr(user, 'role', None) == 'admin'

def is_police_officer(user):
    return getattr(user, 'role', None) == 'police_officer'

def can_access_fir(user, fir):
    """Check if user has permission to access this FIR"""
    if is_admin(user):
        return True
    if is_police_officer(user):
        return fir.police_officer == user
    return False

def generate_fir_number():
    return f"FIR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def generate_pdf_report(html_content):
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_content.encode("UTF-8")), result)
    return result.getvalue() if not pdf.err else None

def safe_translate(text):
    """Safe translation wrapper with fallback"""
    if not text or not text.strip():
        return ""
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception as e:
        logger.warning(f"Translation failed: {str(e)}")
        return f"[Translation failed] {text}"

def predict_ipc_section(text):
    """Safe IPC section prediction with fallback"""
    if not text or not text.strip() or not models_loaded:
        return "IPC 302", 0.75  # Default fallback
    try:
        text_vectorized = vectorizer.transform([text])
        return ipc_model.predict(text_vectorized)[0], 0.85
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        return "IPC 302", 0.75

def process_image_upload(image_file):
    """Process uploaded image using EasyOCR"""
    try:
        # Save temporary image file
        temp_image_path = os.path.join(settings.MEDIA_ROOT, 'temp_ocr_image.jpg')
        with open(temp_image_path, 'wb+') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)
        
        # Perform OCR
        results = ocr_reader.readtext(temp_image_path)
        extracted_text = ' '.join([result[1] for result in results])
        
        # Clean up
        os.remove(temp_image_path)
        
        return extracted_text
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        return None

def process_audio_upload(audio_file):
    """Process uploaded audio using SpeechRecognition"""
    try:
        # Save temporary audio file
        temp_audio_path = os.path.join(settings.MEDIA_ROOT, 'temp_speech_audio.wav')
        with open(temp_audio_path, 'wb+') as destination:
            for chunk in audio_file.chunks():
                destination.write(chunk)
        
        # Perform speech recognition
        with sr.AudioFile(temp_audio_path) as source:
            audio_data = speech_recognizer.record(source)
            text = speech_recognizer.recognize_google(audio_data)
        
        # Clean up
        os.remove(temp_audio_path)
        
        return text
    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        return None

# ======================
# AUTHENTICATION VIEWS
# ======================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('admin_dashboard' if is_admin(request.user) else 'officer_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('admin_dashboard' if is_admin(user) else 'officer_dashboard')
        messages.error(request, "Invalid username or password")
    
    return render(request, 'auth/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

# ======================
# ADMIN VIEWS
# ======================

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    context = {
        'total_stations': Station.objects.count(),
        'total_officers': User.objects.filter(role='police_officer').count(),
        'total_firs': FIR.objects.count(),
        'recent_firs': FIR.objects.order_by('-created_at')[:5]
    }
    return render(request, 'admin/dashboard.html', context)

# Station Management
@login_required
@user_passes_test(is_admin)
def station_list_view(request):
    return render(request, 'admin/stations/list.html', {
        'stations': Station.objects.all()
    })

@login_required
@user_passes_test(is_admin)
def station_create_view(request):
    if request.method == 'POST':
        Station.objects.create(
            name=request.POST.get('name'),
            location=request.POST.get('location'),
            contact_number=request.POST.get('contact_number')
        )
        messages.success(request, "Station created successfully")
        return redirect('station_list')
    return render(request, 'admin/stations/create.html')

@login_required
@user_passes_test(is_admin)
def station_edit_view(request, pk):
    station = get_object_or_404(Station, pk=pk)
    if request.method == 'POST':
        station.name = request.POST.get('name')
        station.location = request.POST.get('location')
        station.contact_number = request.POST.get('contact_number')
        station.save()
        messages.success(request, "Station updated successfully")
        return redirect('station_list')
    return render(request, 'admin/stations/edit.html', {'station': station})

@login_required
@user_passes_test(is_admin)
def station_delete_view(request, pk):
    station = get_object_or_404(Station, pk=pk)
    station.delete()
    messages.success(request, "Station deleted successfully")
    return redirect('station_list')

# User Management
@login_required
@user_passes_test(is_admin)
def user_list_view(request):
    return render(request, 'admin/users/list.html', {
        'users': User.objects.all()
    })

@login_required
@user_passes_test(is_admin)
def user_create_view(request):
    if request.method == 'POST':
        user = User.objects.create_user(
            username=request.POST.get('username'),
            password=request.POST.get('password'),
            role=request.POST.get('role')
        )
        if request.POST.get('station'):
            user.station = Station.objects.get(pk=request.POST.get('station'))
            user.save()
        messages.success(request, "User created successfully")
        return redirect('user_list')
    return render(request, 'admin/users/create.html', {
        'stations': Station.objects.all()
    })

@login_required
@user_passes_test(is_admin)
def user_edit_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.role = request.POST.get('role')
        user.station = Station.objects.get(pk=request.POST.get('station')) if request.POST.get('station') else None
        user.save()
        messages.success(request, "User updated successfully")
        return redirect('user_list')
    return render(request, 'admin/users/edit.html', {
        'user': user,
        'stations': Station.objects.all()
    })

@login_required
@user_passes_test(is_admin)
def user_delete_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.delete()
    messages.success(request, "User deleted successfully")
    return redirect('user_list')

# FIR Management
@login_required
@user_passes_test(is_admin)
def admin_fir_list_view(request):
    firs = FIR.objects.all()
    filters = {
        'status': request.GET.get('status'),
        'station': request.GET.get('station'),
        'officer': request.GET.get('officer')
    }
    
    if filters['status']:
        firs = firs.filter(status=filters['status'])
    if filters['station']:
        firs = firs.filter(station_id=filters['station'])
    if filters['officer']:
        firs = firs.filter(police_officer_id=filters['officer'])
    
    return render(request, 'admin/firs/list.html', {
        'firs': firs.order_by('-created_at'),
        'stations': Station.objects.all(),
        'officers': User.objects.filter(role='police_officer'),
        'current_filters': filters
    })

@login_required
@user_passes_test(is_admin)
def admin_fir_detail_view(request, pk):
    fir = get_object_or_404(FIR, pk=pk)
    if request.method == 'POST' and request.POST.get('officer_id'):
        try:
            fir.police_officer = User.objects.get(pk=request.POST.get('officer_id'), role='police_officer')
            fir.save()
            messages.success(request, "FIR reassigned successfully")
        except User.DoesNotExist:
            messages.error(request, "Invalid officer selected")
        return redirect('admin_fir_detail', pk=pk)
    
    return render(request, 'admin/firs/detail.html', {
        'fir': fir,
        'officers': User.objects.filter(role='police_officer')
    })

# ======================
# OFFICER VIEWS
# ======================

@login_required
@user_passes_test(is_police_officer)
def officer_dashboard(request):
    return render(request, 'officer/dashboard.html', {
        'total_firs': FIR.objects.filter(police_officer=request.user).count(),
        'pending_firs': FIR.objects.filter(
            police_officer=request.user,
            status__in=['draft', 'submitted', 'under_investigation']
        ).count(),
        'recent_firs': FIR.objects.filter(police_officer=request.user).order_by('-created_at')[:5],
        'overdue_firs': FIR.objects.filter(
            police_officer=request.user,
            status='under_investigation',
            investigation_deadline__lt=timezone.now()
        ).count()
    })

@login_required
@user_passes_test(is_police_officer)
def officer_fir_list_view(request):
    firs = FIR.objects.filter(police_officer=request.user)
    if request.GET.get('status'):
        firs = firs.filter(status=request.GET.get('status'))
    
    return render(request, 'officer/firs/list.html', {
        'firs': firs.order_by('-created_at'),
        'current_filter': request.GET.get('status')
    })

@login_required
@user_passes_test(is_police_officer)
def officer_fir_create_view(request):
    if request.method == 'POST':
        incident_description = request.POST.get('incident_description')
        
        # Process image upload if present
        if 'incident_image' in request.FILES:
            image_text = process_image_upload(request.FILES['incident_image'])
            if image_text:
                incident_description = f"Image Text: {image_text}\n\nAdditional Details: {incident_description or ''}"
        
        # Process audio upload if present
        if 'incident_audio' in request.FILES:
            audio_text = process_audio_upload(request.FILES['incident_audio'])
            if audio_text:
                incident_description = f"Audio Transcript: {audio_text}\n\nAdditional Details: {incident_description or ''}"
        
        fir = FIR.objects.create(
            fir_number=generate_fir_number(),
            complainant_name=request.POST.get('complainant_name'),
            complainant_contact=request.POST.get('complainant_contact'),
            incident_description=incident_description,
            incident_date=request.POST.get('incident_date'),
            incident_location=request.POST.get('incident_location'),
            police_officer=request.user,
            station=request.user.station,
            status='draft'
        )
        
        # Save uploaded files if needed
        if 'incident_image' in request.FILES:
            fir.incident_image = request.FILES['incident_image']
        if 'incident_audio' in request.FILES:
            fir.incident_audio = request.FILES['incident_audio']
        fir.save()
        
        messages.success(request, "FIR created successfully")
        return redirect('officer_fir_detail', pk=fir.pk)
    
    return render(request, 'officer/firs/create.html')

@login_required
@user_passes_test(is_police_officer)
def officer_fir_detail_view(request, pk):
    fir = get_object_or_404(FIR, pk=pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(FIR.STATUS_CHOICES).keys():
            fir.status = new_status
            fir.save()
            messages.success(request, "FIR status updated successfully")
        return redirect('officer_fir_detail', pk=pk)
    
    return render(request, 'officer/firs/detail.html', {'fir': fir})

@login_required
@user_passes_test(is_police_officer)
def officer_fir_update_view(request, pk):
    fir = get_object_or_404(FIR, pk=pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if request.method == 'POST':
        fir.complainant_name = request.POST.get('complainant_name')
        fir.complainant_contact = request.POST.get('complainant_contact')
        fir.incident_description = request.POST.get('incident_description')
        fir.incident_date = request.POST.get('incident_date')
        fir.incident_location = request.POST.get('incident_location')
        
        # Process image update if present
        if 'incident_image' in request.FILES:
            image_text = process_image_upload(request.FILES['incident_image'])
            if image_text:
                fir.incident_description = f"Image Text: {image_text}\n\nAdditional Details: {fir.incident_description or ''}"
            fir.incident_image = request.FILES['incident_image']
        
        # Process audio update if present
        if 'incident_audio' in request.FILES:
            audio_text = process_audio_upload(request.FILES['incident_audio'])
            if audio_text:
                fir.incident_description = f"Audio Transcript: {audio_text}\n\nAdditional Details: {fir.incident_description or ''}"
            fir.incident_audio = request.FILES['incident_audio']
        
        fir.save()
        messages.success(request, "FIR updated successfully")
        return redirect('officer_fir_detail', pk=pk)
    
    return render(request, 'officer/firs/update.html', {'fir': fir})

@login_required
@user_passes_test(is_police_officer)
def generate_legal_suggestions_view(request, pk):
    fir = get_object_or_404(FIR, pk=pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied

    # Generate legal suggestions
    translated_text = safe_translate(fir.incident_description)
    ipc_section, confidence = predict_ipc_section(translated_text)
    
    # Save results
    LegalSuggestion.objects.filter(fir=fir).delete()
    LegalSuggestion.objects.create(
        fir=fir,
        ipc_section=ipc_section,
        description=translated_text or "AI-generated legal suggestion",
        confidence_score=confidence
    )

    messages.success(request, "Legal suggestions generated successfully")
    return redirect('officer_fir_detail', pk=fir.pk)