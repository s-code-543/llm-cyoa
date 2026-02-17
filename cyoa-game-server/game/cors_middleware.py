"""
CORS middleware for PWA static assets.

Adds CORS headers to PWA-related paths so crossorigin="use-credentials"
manifest fetches work correctly.
"""


class PWACorsMiddleware:
    """Add CORS headers to PWA static assets."""

    PWA_PATHS = (
        '/sw.js',
        '/site.webmanifest',
        '/favicon.ico',
        '/apple-touch-icon.png',
        '/offline.html',
        '/static/icons/',
        '/static/js/sw.js',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add CORS headers to PWA-related paths
        if any(request.path.startswith(path) for path in self.PWA_PATHS):
            response['Access-Control-Allow-Origin'] = 'https://cyoa.chat-sdp.org'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'X-Requested-With, Content-Type'

        return response
