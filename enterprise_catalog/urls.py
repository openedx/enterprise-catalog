"""catalog URL Configuration
The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""

import os

from auth_backends.urls import oauth2_urlpatterns
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from rest_framework_swagger.views import get_swagger_view

from enterprise_catalog.apps.api import urls as api_urls
from enterprise_catalog.apps.core import views as core_views


admin.autodiscover()

urlpatterns = [
    url(r'', include(oauth2_urlpatterns)),
    url(r'^admin/', admin.site.urls),
    url(r'^api/', include(api_urls), name='api'),
    url(r'^api-docs/', get_swagger_view(title='Enterprise Catalog API')),
    # Use the same auth views for all logins, including those originating from the browseable API.
    url(r'^auto_auth/$', core_views.AutoAuth.as_view(), name='auto_auth'),
    url(r'^health/$', core_views.health, name='health'),
]

if settings.DEBUG and os.environ.get('ENABLE_DJANGO_TOOLBAR', False):  # pragma: no cover
    import debug_toolbar
    urlpatterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))

if os.environ.get('ENABLE_DJANGO_SILK', False):  # pragma: no cover
    urlpatterns.append(url(r'^silk/', include('silk.urls', namespace='silk')))
