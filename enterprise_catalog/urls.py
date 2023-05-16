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
from django.contrib import admin
from django.urls import include, path
from edx_api_doc_tools import make_api_info, make_docs_urls

from enterprise_catalog.apps.api import urls as api_urls
from enterprise_catalog.apps.core import views as core_views


admin.autodiscover()

api_info = make_api_info(
    title='Enterprise Catalog API',
    version="v1",
)

urlpatterns = [
    path('', include(oauth2_urlpatterns)),
    path('', include('csrf.urls')),  # Include csrf urls from edx-drf-extensions
    path('admin/clearcache/', include('clearcache.urls')),
    path('admin/', admin.site.urls),
    path('api/', include(api_urls), name='api'),
    # Use the same auth views for all logins, including those originating from the browseable API.
    path('auto_auth/', core_views.AutoAuth.as_view(), name='auto_auth'),
    path('health/', core_views.health, name='health'),
]

urlpatterns += make_docs_urls(api_info)

if settings.DEBUG and os.environ.get('ENABLE_DJANGO_TOOLBAR', False):  # pragma: no cover
    import debug_toolbar
    urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))
