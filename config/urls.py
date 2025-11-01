from django.contrib import admin
from django.urls import path, include
from marks import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("marks.urls")),
    path("register/", views.register, name="register"),
]
