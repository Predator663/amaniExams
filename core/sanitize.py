import bleach

ALLOWED_TAGS = ["b", "strong", "i", "em", "u", "br", "p", "ul", "ol", "li", "sup", "sub", "span", "img"]
ALLOWED_ATTRS = {
    "img": ["src", "alt"],
    "span": ["class", "data-formula"],  # formula editor output
}


def clean_html(value):
    """Rich question text (QB-05) is sanitised on the server to prevent XSS (NFR-07)."""
    return bleach.clean(value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https"], strip=True)
