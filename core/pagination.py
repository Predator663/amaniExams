"""Optional paging for every list in the API.

A list is paged only when the request carries ?page=N (and optionally ?page_size=M). Without ?page the old
plain response is returned unchanged, so older screens, the Android SMS sender and the load tests keep working.

Paged shape: {"count", "page", "pages", "page_size", "results": [...]}. A page past the end is moved to the last
page (a row deleted on the last page must not show an empty screen).
"""
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

DEFAULT_SIZE = 20
MAX_SIZE = 100


def wants_page(request) -> bool:
    return "page" in request.query_params


def page_params(request, default=DEFAULT_SIZE):
    """(page, size) from the query string, clamped. Raises a 400 for text that is not a number."""
    p = request.query_params
    try:
        size = min(max(int(p.get("page_size", default)), 1), MAX_SIZE)
        page = max(int(p.get("page", 1)), 1)
    except ValueError:
        raise ValidationError({"detail": "page and page_size must be numbers."})
    return page, size


def envelope(count, page, size, results, **extra):
    pages = max(1, -(-count // size))
    return {"count": count, "page": min(page, pages), "pages": pages, "page_size": size, **extra, "results": results}


def _stable(qs):
    """Add the primary key as the last sort key so rows with equal values never swap pages."""
    if isinstance(qs, list) or not hasattr(qs, "order_by"):
        return qs
    order = list(qs.query.order_by) or list(qs.model._meta.ordering)
    return qs.order_by(*order, "pk")


def paginate(request, items, default=DEFAULT_SIZE, row=None, **extra):
    """Slice a list or queryset for ?page=. Returns the paged dict, or None when the request did not ask for paging."""
    if not wants_page(request):
        return None
    page, size = page_params(request, default)
    items = _stable(items)
    count = items.count() if hasattr(items, "count") and not isinstance(items, list) else len(items)
    pages = max(1, -(-count // size))
    page = min(page, pages)
    rows = list(items[(page - 1) * size: page * size])
    return envelope(count, page, size, [row(r) for r in rows] if row else rows, **extra)


class OptionalPagination(PageNumberPagination):
    """DRF default for every ViewSet: pages only when ?page= is sent."""
    page_size = DEFAULT_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_SIZE

    def paginate_queryset(self, queryset, request, view=None):
        if not wants_page(request):
            return None
        page, size = page_params(request, self.page_size)
        self.request, self.size = request, size
        queryset = _stable(queryset)
        self.count = queryset.count() if hasattr(queryset, "count") and not isinstance(queryset, list) else len(queryset)
        self.pages = max(1, -(-self.count // size))
        self.page = min(page, self.pages)
        return list(queryset[(self.page - 1) * size: self.page * size])

    def get_paginated_response(self, data):
        return Response(envelope(self.count, self.page, self.size, data))
