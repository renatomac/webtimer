from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView, TemplateView
from django.views.decorators.cache import never_cache
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("cast-receiver/", never_cache(TemplateView.as_view(template_name="timerapp/cast_receiver.html")), name="cast_receiver"),
    path("", RedirectView.as_view(pattern_name="timers:home", permanent=False)),
    path("timers/", include(("timerapp.clone_urls", "timers"), namespace="timers")),
    path("legacy/", include("timerapp.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
