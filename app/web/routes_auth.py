"""Sign-in, sign-up and sign-out pages."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import service
from app.auth.dependencies import clear_session_cookies, set_session_cookies
from app.web.templates import templates

router = APIRouter(tags=["auth"])


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
