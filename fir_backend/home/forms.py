from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User,Station

class UserRegistrationForm(UserCreationForm):
    station = forms.ModelChoiceField(
        queryset=Station.objects.all(),
        required=True,
        label="Police Station"
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'station')

class AdminRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')