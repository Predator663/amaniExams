import bleach
from django.conf import settings

ALLOWED_TAGS = ["b", "strong", "i", "em", "u", "br", "p", "ul", "ol", "li", "sup", "sub", "span", "img"]


def _own_image(tag, name, value):
    """SECURITY: an <img> may only point at this site's own uploads (/media/...). An image on another server would tell that
    server every student's address and when she opened the question."""
    if name != "src":
        return name in ("alt",)
    v = (value or "").strip()
    if v.startswith("/media/") or v.startswith("media/"):
        return True
    if v.startswith("http://") or v.startswith("https://"):
        from urllib.parse import urlparse
        host = (urlparse(v).hostname or "").lower()
        own = {h.lower().lstrip(".") for h in settings.ALLOWED_HOSTS if h and h != "*"}
        own |= {(urlparse(o).hostname or "").lower() for o in getattr(settings, "CORS_ALLOWED_ORIGINS", [])}
        return host in own and urlparse(v).path.startswith("/media/")
    return False


ALLOWED_ATTRS = {
    "img": _own_image,
    "span": ["class", "data-formula"],  # formula editor output
}


def clean_html(value):
    """Rich question text (QB-05) is sanitised on the server to prevent XSS (NFR-07)."""
    return bleach.clean(value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https"], strip=True)
