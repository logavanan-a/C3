from django.contrib import admin
from django.urls import path
from dashboard.views import *

app_name = "dashboard"

urlpatterns = [
    # API for checking user exist or not
    
    path('dashboard/', dashboard, name="dashboard"),
]
