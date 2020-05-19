from rest_framework.pagination import PageNumberPagination


class PageNumberWithSizePagination(PageNumberPagination):
    """
    Custom pagination that allows clients to pass a `page_size` query param.

    Example usage: /api/v1/enterprise-catalogs/{uuid}/get_content_metadata/?page_size=1000
    """
    page_size_query_param = 'page_size'
