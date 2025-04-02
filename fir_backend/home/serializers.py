from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import User, Station, FIR, LegalSuggestion

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'station', 'is_active', 'date_joined'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'date_joined': {'read_only': True},
        }

    def validate_password(self, value):
        """Hash password before saving"""
        return make_password(value)

    def create(self, validated_data):
        """Handle user creation with proper role assignment"""
        user = User.objects.create_user(**validated_data)
        return user

class StationSerializer(serializers.ModelSerializer):
    officers = serializers.SerializerMethodField()
    
    class Meta:
        model = Station
        fields = ['id', 'name', 'location', 'contact_number', 'officers']
        read_only_fields = ['officers']

    def get_officers(self, obj):
        """Get list of officers assigned to this station"""
        return UserSerializer(
            obj.officers.all(),
            many=True,
            context=self.context
        ).data

class LegalSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalSuggestion
        fields = [
            'id', 'ipc_section', 'crpc_section', 'act_name',
            'confidence_score', 'created_at'
        ]
        read_only_fields = ['created_at']

class FIRSerializer(serializers.ModelSerializer):
    police_officer = UserSerializer(read_only=True)
    station = StationSerializer(read_only=True)
    legal_suggestions = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )

    class Meta:
        model = FIR
        fields = [
            'id', 'fir_number', 'complainant_name', 'complainant_contact',
            'incident_description', 'incident_date', 'incident_location',
            'police_officer', 'station', 'status', 'status_display',
            'created_at', 'legal_suggestions'
        ]
        read_only_fields = [
            'fir_number', 'police_officer', 'station',
            'created_at', 'legal_suggestions'
        ]

    def get_legal_suggestions(self, obj):
        """Get legal suggestions for this FIR"""
        return LegalSuggestionSerializer(
            obj.legal_suggestions.all(),
            many=True,
            context=self.context
        ).data

    def create(self, validated_data):
        """Auto-assign the current user as police officer"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['police_officer'] = request.user
            if request.user.station:
                validated_data['station'] = request.user.station
        return super().create(validated_data)

class FIRStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FIR
        fields = ['status']
        extra_kwargs = {
            'status': {'required': True}
        }

class ReportSerializer(serializers.Serializer):
    """Serializer for generating various reports"""
    station_name = serializers.CharField()
    total_firs = serializers.IntegerField()
    draft_firs = serializers.IntegerField()
    submitted_firs = serializers.IntegerField()
    investigating_firs = serializers.IntegerField()
    closed_firs = serializers.IntegerField()

class OfficerPerformanceSerializer(serializers.Serializer):
    """Serializer for officer performance reports"""
    officer = serializers.CharField(source='username')
    total_firs = serializers.IntegerField()
    closed_firs = serializers.IntegerField()
    closure_rate = serializers.SerializerMethodField()

    def get_closure_rate(self, obj):
        if obj.total_firs > 0:
            return (obj.closed_firs / obj.total_firs) * 100
        return 0

class CrimeTrendSerializer(serializers.Serializer):
    """Serializer for crime trend reports"""
    location = serializers.CharField(source='incident_location')
    count = serializers.IntegerField()
    percentage = serializers.SerializerMethodField()

    def get_percentage(self, obj):
        total = self.context.get('total_count', 1)
        return (obj['count'] / total) * 100

class NotificationSerializer(serializers.Serializer):
    """Serializer for notifications"""
    id = serializers.IntegerField()
    message = serializers.CharField()
    read = serializers.BooleanField()
    timestamp = serializers.DateTimeField()
    fir_number = serializers.CharField(required=False)