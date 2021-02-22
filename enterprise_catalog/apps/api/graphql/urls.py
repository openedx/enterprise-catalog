from django.conf.urls import url

from django.views.decorators.csrf import csrf_exempt

from enterprise_catalog.apps.api.graphql.views import schema

from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)

from rest_framework.authentication import SessionAuthentication
from graphene_django.views import GraphQLView
from rest_framework import permissions
from rest_framework.decorators import authentication_classes, permission_classes, api_view

# Reusing the rest api permission and authentication stufffff to handle authentication and csrf things
# Janky but works
def rest_permissions_view():
    view = GraphQLView.as_view(graphiql=True, schema=schema)
    view = permission_classes((permissions.IsAuthenticated,))(view)
    view = authentication_classes((JwtAuthentication, SessionAuthentication))(view)
    view = api_view(['GET', 'POST'])(view)
    return view

urlpatterns = [
    # ...
    url('authgraph', rest_permissions_view()),
    url('graphiql', csrf_exempt(GraphQLView.as_view(graphiql=True, schema=schema)))
]
