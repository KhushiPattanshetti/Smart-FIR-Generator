from django.urls import path
from home import views

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Admin URLs
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Station Management
    path('admin/stations/', views.station_list_view, name='station_list'),
    path('admin/stations/create/', views.station_create_view, name='station_create'),
    path('admin/stations/<int:pk>/edit/', views.station_edit_view, name='station_edit'),
    path('admin/stations/<int:pk>/delete/', views.station_delete_view, name='station_delete'),
    
    # User Management
    path('admin/users/', views.user_list_view, name='user_list'),
    path('admin/users/create/', views.user_create_view, name='user_create'),
    path('admin/users/<int:pk>/edit/', views.user_edit_view, name='user_edit'),
    path('admin/users/<int:pk>/delete/', views.user_delete_view, name='user_delete'),
    
    # Admin FIR Management
    path('admin/firs/', views.admin_fir_list_view, name='admin_fir_list'),
    path('admin/firs/<int:pk>/', views.admin_fir_detail_view, name='admin_fir_detail'),
    
    # Reports
    path('admin/reports/', views.report_generate_view, name='report_generate'),
    
    # Police Officer URLs
    path('officer/dashboard/', views.officer_dashboard, name='officer_dashboard'),
    
    # FIR Management
    path('officer/firs/', views.officer_fir_list_view, name='officer_fir_list'),
    path('officer/firs/create/', views.officer_fir_create_view, name='officer_fir_create'),
    path('officer/firs/<int:pk>/', views.officer_fir_detail_view, name='officer_fir_detail'),
    path('officer/firs/<int:pk>/update/', views.officer_fir_update_view, name='officer_fir_update'),
    
    # Team Management
    path('officer/firs/<int:fir_pk>/team/', views.assign_team_view, name='assign_team'),
    
    # Evidence Management
    path('officer/firs/<int:fir_pk>/evidence/', views.manage_evidence_view, name='manage_evidence'),
    path('officer/firs/<int:fir_pk>/evidence/upload/', views.upload_evidence_view, name='upload_evidence'),
    path('officer/firs/<int:fir_pk>/transcribe/', views.transcribe_audio_view, name='transcribe_audio'),
    
    # Legal Suggestions
    path('officer/firs/<int:fir_pk>/legal-suggestions/', 
         views.generate_legal_suggestions_view, name='generate_legal_suggestions'),
    
    # Witness Management
    path('officer/firs/<int:fir_pk>/witnesses/', views.manage_witnesses_view, name='manage_witnesses'),
    
    # Court Hearings
    path('officer/firs/<int:fir_pk>/hearings/', views.court_hearings_view, name='court_hearings'),
    
    # Charge Sheet
    path('officer/firs/<int:fir_pk>/charge-sheet/', views.generate_charge_sheet, name='generate_charge_sheet'),
    
    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/<int:notification_id>/mark-read/', 
         views.mark_notification_read_view, name='mark_notification_read'),
    
    # Analytics
    path('analytics/', views.dashboard_analytics, name='dashboard_analytics'),
]