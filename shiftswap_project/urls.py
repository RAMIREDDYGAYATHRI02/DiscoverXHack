
from django.urls import include, path
from django.http import HttpResponseRedirect
from django.conf import settings


def frontend_redirect(request):
    return HttpResponseRedirect(settings.FRONTEND_URL)


urlpatterns = [
    path("", frontend_redirect, name="home"),
    path("api/", include("api.urls")),
]
