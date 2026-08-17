"""Shared Jinja2 environment.

Every page goes through `render`, which merges the language globals in. Doing
it here rather than at each call site means a new screen cannot forget `t()`
and render a page full of raw translation keys.
"""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import template_globals

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {**template_globals(request), **(context or {})},
        status_code=status_code,
    )
