from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("academics.urls")),
    path("api/", include("questions.urls")),
    path("api/", include("exams.urls")),
    path("api/", include("core.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("analytics.urls")),
    path("api/", include("gamification.urls")),
    path("api/", include("guardians.urls")),
    path("api/", include("proctoring.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Question images and the school logo are saved under MEDIA_ROOT (a persistent disk on Render). gunicorn does not serve them by
    # itself, so Django does: fine for the few small images of a school (the web app asks the API address for them, see mediaUrl()).
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
