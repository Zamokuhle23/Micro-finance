from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("loans/", include("loans.urls", namespace="loans")),
    path('accounts/', include('accounts.urls')),
    path('', RedirectView.as_view(url='/accounts/login/')),
]
