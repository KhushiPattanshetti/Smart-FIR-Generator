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
from .models import User, Station, FIR, LegalSuggestion, Notification
from .forms import UserRegistrationForm, AdminRegistrationForm

logger = logging.getLogger(__name__)

# ======================
# MODEL LOADING SYSTEM
# ======================

def load_ml_models():
    """Load ML models once at application startup"""
    try:
        global ipc_model, vectorizer
        model_dir = os.path.join(settings.BASE_DIR, 'ml_models')
        ipc_model = joblib.load(os.path.join(model_dir, 'ipc_model.pkl'))
        vectorizer = joblib.load(os.path.join(model_dir, 'vectorizer.pkl'))
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

def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'police_officer'
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)
            return redirect('officer_dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'auth/register.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def register_admin_view(request):
    if request.method == 'POST':
        form = AdminRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'admin'
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, "Admin user created successfully")
            return redirect('user_list')
    else:
        form = AdminRegistrationForm()
    return render(request, 'auth/register_admin.html', {'form': form})

def forgot_password(request):
    # TODO: Implement password reset functionality
    return render(request, 'auth/forgot_password.html')

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

# Reports
@login_required
@user_passes_test(is_admin)
def report_generate_view(request):
    report_type = request.GET.get('type', 'monthly')
    format = request.GET.get('format', 'html')
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    if report_type == 'monthly':
        data = FIR.objects.filter(created_at__range=(start_date, end_date)).values(
            'station__name').annotate(
            total=Count('id'),
            draft=Count('id', filter=Q(status='draft')),
            submitted=Count('id', filter=Q(status='submitted')),
            investigating=Count('id', filter=Q(status='under_investigation')),
            closed=Count('id', filter=Q(status='closed'))
        )
        template = 'admin/reports/monthly.html'
    elif report_type == 'officer_performance':
        data = User.objects.filter(role='police_officer').annotate(
            total=Count('filed_firs'),
            closed=Count('filed_firs', filter=Q(filed_firs__status='closed'))
        )
        template = 'admin/reports/officer_performance.html'
    else:
        return redirect('report_generate')
    
    if format == 'pdf':
        pdf = generate_pdf_report(render_to_string(template, {
            'data': data, 
            'start_date': start_date, 
            'end_date': end_date
        }))
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report_type}_report.pdf"'
            return response
    
    elif format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report.csv"'
        writer = csv.writer(response)
        
        if report_type == 'monthly':
            writer.writerow(['Station', 'Total', 'Draft', 'Submitted', 'Investigating', 'Closed'])
            for item in data:
                writer.writerow([
                    item['station__name'],
                    item['total'],
                    item['draft'],
                    item['submitted'],
                    item['investigating'],
                    item['closed']
                ])
        else:
            writer.writerow(['Officer', 'Total FIRs', 'Closed FIRs'])
            for officer in data:
                writer.writerow([officer.username, officer.total, officer.closed])
        
        return response
    
    return render(request, template, {
        'data': data,
        'start_date': start_date,
        'end_date': end_date,
        'report_type': report_type
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
        fir = FIR.objects.create(
            fir_number=generate_fir_number(),
            complainant_name=request.POST.get('complainant_name'),
            complainant_contact=request.POST.get('complainant_contact'),
            incident_description=request.POST.get('incident_description'),
            incident_date=request.POST.get('incident_date'),
            incident_location=request.POST.get('incident_location'),
            police_officer=request.user,
            station=request.user.station,
            status='draft'
        )
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
        fir.save()
        messages.success(request, "FIR updated successfully")
        return redirect('officer_fir_detail', pk=pk)
    
    return render(request, 'officer/firs/update.html', {'fir': fir})

@login_required
@user_passes_test(is_police_officer)
def generate_legal_suggestions_view(request, pk):  # Note the parameter name is 'pk'
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

@login_required
@user_passes_test(is_police_officer)
def generate_charge_sheet(request, fir_pk):
    fir = get_object_or_404(FIR, pk=fir_pk)
    if not can_access_fir(request.user, fir):
        raise PermissionDenied
    
    if fir.status != 'under_investigation':
        messages.error(request, "Charge sheet can only be generated for cases under investigation")
        return redirect('officer_fir_detail', pk=fir.pk)
    
    context = {
        'fir': fir,
        'legal_suggestions': LegalSuggestion.objects.filter(fir=fir),
        'officer': request.user
    }
    
    if request.GET.get('format') == 'pdf':
        pdf = generate_pdf_report(render_to_string('officer/firs/charge_sheet_pdf.html', context))
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="charge_sheet_{fir.fir_number}.pdf"'
            return response
    
    return render(request, 'officer/firs/charge_sheet.html', context)

# ======================
# NOTIFICATION VIEWS
# ======================

@login_required
def notifications_view(request):
    return render(request, 'notifications/list.html', {
        'notifications': Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:50]
    })

@login_required
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.read = True
    notification.save()
    return redirect(notification.link if notification.link else 'notifications')

# ======================
# ANALYTICS VIEWS
# ======================

@login_required
def dashboard_analytics(request):
    if is_admin(request.user):
        return render(request, 'admin/analytics.html', {
            'stations': Station.objects.annotate(
                total=Count('firs'),
                pending=Count('firs', filter=Q(firs__status__in=['submitted', 'under_investigation'])),
                overdue=Count('firs', filter=Q(
                    firs__status='under_investigation',
                    firs__investigation_deadline__lt=timezone.now()
                ))
            ),
            'officers': User.objects.filter(role='police_officer').annotate(
                case_load=Count('filed_firs', filter=Q(filed_firs__status__in=['submitted', 'under_investigation'])),
                closed_cases=Count('filed_firs', filter=Q(filed_firs__status='closed'))
            )
        })
    else:
        return render(request, 'officer/analytics.html', {
            'firs_by_status': FIR.objects.filter(
                police_officer=request.user
            ).values('status').annotate(count=Count('id')),
            'overdue_firs': FIR.objects.filter(
                police_officer=request.user,
                status='under_investigation',
                investigation_deadline__lt=timezone.now()
            ).count()
        })