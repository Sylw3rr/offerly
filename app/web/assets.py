"""Stamping static files with their own contents.

A stylesheet served from one address forever is a stylesheet a cache is
entitled to keep. Ours sits behind Cloudflare with a four-hour `max-age`, and
the deploy that added the hero shimmer proved what that means: the new markup
went out, the browser asked for `/static/offerly.css`, and the edge answered
`cf-cache-status: HIT` with the stylesheet from before the change. Nothing was
broken, but nothing was styled either — and the failure is only harmless while
the new markup happens not to need the new rules.

So the address changes when the file does. `offerly.css?v=8f21c3d0` is a URL no
cache has seen before, which makes a deploy self-purging: no dashboard, no API
token, no waiting out somebody else's TTL.

The digest is read once per process. These files are baked into the image and
cannot change under a running server, and hashing them on every request would
be work done for nobody.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from fastapi import Request

STATIC_DIR = Path(__file__).parent / "static"


@lru_cache(maxsize=64)
def digest(path: str) -> str:
    """Eight hex characters of the file's content hash, or "" if it is missing.

    A missing file is not worth an exception: the link would 404 either way,
    and a template that raises turns a broken asset into a broken page.
    """
    target = STATIC_DIR / path
    try:
        return hashlib.sha256(target.read_bytes()).hexdigest()[:8]
    except OSError:
        return ""


def asset(request: Request, path: str) -> str:
    """The versioned URL for a static file, for use in templates."""
    url = str(request.url_for("static", path=path))
    stamp = digest(path)
    return f"{url}?v={stamp}" if stamp else url
