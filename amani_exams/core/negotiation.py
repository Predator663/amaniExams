from rest_framework.negotiation import DefaultContentNegotiation


class IgnoreAcceptNegotiation(DefaultContentNegotiation):
    """Always use the first renderer (JSON) and never refuse with 406.

    Views that return a PDF/Excel/CSV build their own HttpResponse, so the Accept header of
    a download link must not matter. Parsers are still chosen normally, so multipart
    uploads keep working."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type
