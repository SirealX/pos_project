from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='sales:pos', permanent=False)),
    path('', include('apps.users.urls', namespace='users')),
    path('inventory/', include('apps.inventory.urls', namespace='inventory')),
    path('pos/', include('apps.sales.urls', namespace='sales')),
    path('staff/', include('apps.staff.urls', namespace='staff')),
    path('reports/', include('apps.reports.urls', namespace='reports')),
]

# Serve uploaded media files in development only.
# In production, your web server (nginx/S3) handles media.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
