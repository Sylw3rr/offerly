"""Sign-in, sign-up, sign-out and password recovery pages."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import service
from app.auth.dependencies import clear_session_cookies, set_session_cookies
from app.config import get_settings
from app.web.templates import templates

router = APIRouter(tags=["auth"])

# Shown whether or not the address has an account here.
RESET_SENT = (
    "If that address has an account, a link to set a new password is on its way. "
    "It expires in an hour."
)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        session = service.sign_in(email.strip().lower(), password)
    except service.AuthError as exc:
        return templates.TemplateResponse(
            request, "login.html", {"error": str(exc), "email": email}, status_code=400
        )

    response = RedirectResponse("/", status_code=303)
    set_session_cookies(response, session)
    return response


@router.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse(request, "signup.html", {})


@router.post("/signup")
def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(...),
):
    try:
        session = service.sign_up(email.strip().lower(), password, invite_code)
    except service.AuthError as exc:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": str(exc), "email": email, "invite_code": invite_code},
            status_code=400,
        )

    response = RedirectResponse("/", status_code=303)
    set_session_cookies(response, session)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookies(response)
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {})


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(request: Request, email: str = Form(...)):
    """Always answers the same way, sent or not — see `send_password_reset`."""
    redirect_to = get_settings().app_base_url.rstrip("/") + "/reset-password"
    service.send_password_reset(email.strip().lower(), redirect_to)
    return templates.TemplateResponse(request, "forgot_password.html", {"sent": RESET_SENT})


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_form(request: Request, token_hash: str = "", type: str = ""):
    """The page the emailed link lands on.

    The link carries the token as a query parameter, so the exchange happens
    server-side. Without one there is nothing to redeem: say so rather than
    showing a password field that cannot work.
    """
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "token_hash": token_hash,
            "error": None if token_hash else "This link is missing its token.",
        },
    )


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    token_hash: str = Form(...),
    password: str = Form(...),
    password_again: str = Form(""),
):
    if password != password_again:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"token_hash": token_hash, "error": "The two passwords do not match."},
            status_code=400,
        )

    try:
        session = service.reset_password(token_hash, password)
    except service.AuthError as exc:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"token_hash": token_hash, "error": str(exc)},
            status_code=400,
        )

    # Signed in with the new password, so the next step is the application
    # rather than the sign-in form they just came from.
    response = RedirectResponse("/", status_code=303)
    set_session_cookies(response, session)
    return response
