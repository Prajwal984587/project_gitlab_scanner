from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('scan/start/', views.start_scan, name='start_scan'),
    path('results/<int:scan_id>/', views.results, name='results'),
    path('export/pdf/<int:scan_id>/', views.export_pdf, name='export_pdf'),
    path('export/json/<int:scan_id>/', views.export_json, name='export_json'),
    path('history/', views.history, name='history'),
    path('scan/delete/<int:scan_id>/', views.delete_scan, name='delete_scan'),  # ADD THIS LINE
]