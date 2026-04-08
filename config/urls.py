from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from marks import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("marks.urls")),
    path("register/", views.register, name="register"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
