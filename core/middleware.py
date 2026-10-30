class SecurityHeadersMiddleware:
    """Extra response headers. The JSON API never needs scripts, frames or images, so a strict policy costs nothing.
    (The web app is static files served by the host: see frontend/public/_headers for its policy.)"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), payment=(), usb=()")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
            if resp.headers.get("Content-Type", "").startswith("application/json"):  # not on PDFs: a strict policy stops browsers from showing them
                resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return resp
