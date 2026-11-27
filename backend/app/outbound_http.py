"""HTTP policy for requests that include integration credentials."""

from urllib.request import HTTPRedirectHandler, build_opener


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib turns the declined redirect into an HTTPError for the original URL.
        return None


def open_authenticated(request, *, timeout):
    return build_opener(RejectRedirects()).open(request, timeout=timeout)
