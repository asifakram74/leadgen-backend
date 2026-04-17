import asyncio
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from app.core.config import settings
from pathlib import Path

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates' / 'email'
)

def print_fallback_message(email_type: str, email: str, token: str, url: str):
    print(f"\n{'!'*60}")
    print(f"⚠️  SMTP FALLBACK: {email_type} for {email}")
    print(f"Token: {token}")
    print(f"URL:   {url}")
    print(f"{'!'*60}\n")

async def send_welcome_verification_email(email: str, first_name: str, token: str):
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    
    # Check if SMTP is likely unconfigured
    if settings.MAIL_USERNAME == "your_email@gmail.com":
        print_fallback_message("WELCOME/VERIFY", email, token, verification_url)
        return

    message = MessageSchema(
        subject="Welcome to LeadStation Pro! Verify your Identity",
        recipients=[email],
        template_body={
            "first_name": first_name or "User",
            "verification_url": verification_url
        },
        subtype=MessageType.html
    )

    try:
        fm = FastMail(conf)
        # Add a protective timeout to prevent hanging on bad connections
        await asyncio.wait_for(fm.send_message(message, template_name="welcome.html"), timeout=10.0)
    except Exception as e:
        print(f"❌ SMTP ERROR: {str(e)}")
        print_fallback_message("WELCOME/VERIFY (FAILED DISPATCH)", email, token, verification_url)

async def send_forgot_password_email(email: str, token: str):
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    
    # Check if SMTP is likely unconfigured
    if settings.MAIL_USERNAME == "your_email@gmail.com":
        print_fallback_message("PASSWORD RESET", email, token, reset_url)
        return

    message = MessageSchema(
        subject="LeadStation Pro: Password Reset Authorization",
        recipients=[email],
        template_body={
            "reset_url": reset_url,
            "token": token
        },
        subtype=MessageType.html
    )

    try:
        fm = FastMail(conf)
        # Add a protective timeout to prevent hanging on bad connections
        await asyncio.wait_for(fm.send_message(message, template_name="reset_password.html"), timeout=10.0)
    except Exception as e:
        print(f"❌ SMTP ERROR: {str(e)}")
        print_fallback_message("PASSWORD RESET (FAILED DISPATCH)", email, token, reset_url)


