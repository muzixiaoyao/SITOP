"""自定义分页类，支持前端通过 page_size 参数覆盖默认分页大小"""
from rest_framework.pagination import PageNumberPagination


class FlexiblePagination(PageNumberPagination):
    """允许前端通过 ?page_size=N 覆盖默认分页大小"""
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 10000
