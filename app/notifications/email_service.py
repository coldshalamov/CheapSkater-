"""Email service for sending deal notifications."""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any

# Optional SendGrid import
try:
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition
    HAS_SENDGRID = True
except ImportError:
    HAS_SENDGRID = False

from app.logging_config import get_logger

LOGGER = get_logger(__name__)

# Configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM", "deals@gloorbot.com")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "GloorBot Deal Alerts")


def is_email_configured() -> bool:
    """Check if email sending is configured."""
    return bool(HAS_SENDGRID and SENDGRID_API_KEY)


def _format_currency(value: float | None) -> str:
    """Format a number as currency."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _format_discount(pct_off: float | None) -> str:
    """Format discount percentage."""
    if pct_off is None:
        return "N/A"
    # Handle both 0.75 and 75 formats
    if pct_off < 1:
        pct_off = pct_off * 100
    return f"{pct_off:.0f}%"


def _generate_deal_card_html(deal: dict[str, Any]) -> str:
    """Generate HTML for a single deal card in emails."""
    title = deal.get("title", "Unknown Product")
    price = _format_currency(deal.get("price"))
    was_price = _format_currency(deal.get("price_was"))
    pct_off = _format_discount(deal.get("pct_off"))
    category = deal.get("category", "Uncategorized")
    store_label = deal.get("store_label", deal.get("store_name", "Unknown Store"))
    store_state = deal.get("store_state", "")
    sku = deal.get("sku", "")
    product_url = deal.get("product_url", "#")
    image_url = deal.get("image_url", "")
    
    image_html = ""
    if image_url:
        image_html = f'''
            <td style="width: 100px; padding: 16px;">
                <img src="{image_url}" alt="{title}" style="width: 80px; height: 80px; object-fit: contain; border-radius: 8px; background: #f8f9fa;">
            </td>
        '''
    
    return f'''
    <table style="width: 100%; border-collapse: collapse; background: linear-gradient(145deg, #1a1f2e, #252b3d); border-radius: 16px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.3);">
        <tr>
            {image_html}
            <td style="padding: 20px;">
                <h3 style="margin: 0 0 8px 0; color: #ffffff; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 18px; font-weight: 600;">
                    <a href="{product_url}" style="color: #ffffff; text-decoration: none; hover: text-decoration: underline;">{title}</a>
                </h3>
                <p style="margin: 0 0 12px 0; color: #a8b5c8; font-size: 14px;">
                    <span style="background: rgba(212, 175, 55, 0.2); color: #d4af37; padding: 2px 10px; border-radius: 20px; font-weight: 600; font-size: 12px;">{category}</span>
                    <span style="margin-left: 8px; color: #6b7a8f;">SKU: {sku}</span>
                </p>
                <table style="width: 100%;">
                    <tr>
                        <td style="padding: 0;">
                            <span style="font-size: 28px; font-weight: 800; color: #10b981; font-family: 'Helvetica Neue', Arial, sans-serif;">{price}</span>
                            <span style="font-size: 14px; color: #6b7a8f; text-decoration: line-through; margin-left: 8px;">{was_price}</span>
                        </td>
                        <td style="text-align: right; padding: 0;">
                            <span style="background: linear-gradient(135deg, #d4af37, #f4d03f); color: #1a1f2e; padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 16px;">{pct_off} OFF</span>
                        </td>
                    </tr>
                </table>
                <p style="margin: 12px 0 0 0; color: #a8b5c8; font-size: 13px;">
                    📍 {store_label} {f"({store_state})" if store_state else ""}
                </p>
            </td>
        </tr>
        <tr>
            <td colspan="2" style="padding: 0 20px 20px 20px;">
                <a href="{product_url}" style="display: inline-block; background: linear-gradient(135deg, #d4af37, #b8860b); color: #1a1f2e; padding: 12px 24px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 14px;">View Deal →</a>
            </td>
        </tr>
    </table>
    '''


def _generate_email_html(
    alert_name: str,
    deals: list[dict[str, Any]],
    alert_type: str,
    criteria: str,
) -> str:
    """Generate the full HTML email template."""
    
    deal_cards = "\n".join(_generate_deal_card_html(deal) for deal in deals[:10])  # Limit to 10 deals
    more_text = ""
    if len(deals) > 10:
        more_text = f'<p style="color: #a8b5c8; text-align: center; font-size: 14px;">... and {len(deals) - 10} more deals matching your alert</p>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{len(deals)} New Deal{"s" if len(deals) != 1 else ""} Found!</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #0f1218; font-family: 'Helvetica Neue', Arial, sans-serif;">
        <table style="width: 100%; max-width: 640px; margin: 0 auto; padding: 32px 20px;">
            <tr>
                <td>
                    <!-- Header -->
                    <table style="width: 100%; margin-bottom: 32px;">
                        <tr>
                            <td style="text-align: center;">
                                <h1 style="margin: 0 0 8px 0; font-size: 32px; font-weight: 800; background: linear-gradient(135deg, #d4af37, #f4d03f); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">
                                    🤖 GloorBot
                                </h1>
                                <p style="margin: 0; color: #6b7a8f; font-size: 14px;">Deal Alert: {alert_name}</p>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- Alert Info -->
                    <table style="width: 100%; background: rgba(212, 175, 55, 0.1); border: 1px solid rgba(212, 175, 55, 0.3); border-radius: 12px; margin-bottom: 24px;">
                        <tr>
                            <td style="padding: 16px 20px;">
                                <p style="margin: 0; color: #d4af37; font-size: 18px; font-weight: 600;">
                                    🎯 {len(deals)} New Match{"es" if len(deals) != 1 else ""}!
                                </p>
                                <p style="margin: 8px 0 0 0; color: #a8b5c8; font-size: 14px;">
                                    {alert_type.title()} alert for: <strong style="color: #ffffff;">{criteria}</strong>
                                </p>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- Deals -->
                    {deal_cards}
                    {more_text}
                    
                    <!-- Footer -->
                    <table style="width: 100%; margin-top: 32px; border-top: 1px solid #252b3d; padding-top: 24px;">
                        <tr>
                            <td style="text-align: center;">
                                <p style="margin: 0 0 8px 0; color: #6b7a8f; font-size: 12px;">
                                    You're receiving this because you set up a deal alert on GloorBot.
                                </p>
                                <p style="margin: 0; color: #6b7a8f; font-size: 12px;">
                                    <a href="https://gloorbot.com/auth/account" style="color: #d4af37;">Manage your alerts</a> · 
                                    <a href="https://gloorbot.com" style="color: #d4af37;">View all deals</a>
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    '''


def send_deal_alert_email(
    to_email: str,
    alert_name: str,
    deals: list[dict[str, Any]],
    alert_type: str,
    criteria: str,
) -> bool:
    """
    Send a deal alert email to a user.
    
    Returns True if email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        LOGGER.warning("Email not configured, skipping notification to %s", to_email)
        return False
    
    if not deals:
        LOGGER.debug("No deals to send for alert %s", alert_name)
        return False
    
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        
        subject = f"🤖 {len(deals)} New Deal{'s' if len(deals) != 1 else ''} - {alert_name}"
        html_content = _generate_email_html(alert_name, deals, alert_type, criteria)
        
        message = Mail(
            from_email=Email(SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )
        
        response = sg.send(message)
        
        if response.status_code in (200, 201, 202):
            LOGGER.info("Sent deal alert email to %s for alert %s", to_email, alert_name)
            return True
        else:
            LOGGER.error("Failed to send email: status=%s", response.status_code)
            return False
            
    except Exception as e:
        LOGGER.error("Email send error: %s", e)
        return False


def send_welcome_email(to_email: str, display_name: str | None = None) -> bool:
    """Send a welcome email to new subscribers."""
    if not is_email_configured():
        return False
    
    name = display_name or "Deal Hunter"
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 0; background-color: #0f1218; font-family: 'Helvetica Neue', Arial, sans-serif;">
        <table style="width: 100%; max-width: 640px; margin: 0 auto; padding: 40px 20px;">
            <tr>
                <td style="text-align: center;">
                    <h1 style="font-size: 36px; margin: 0 0 16px 0; background: linear-gradient(135deg, #d4af37, #f4d03f); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                        Welcome to GloorBot! 🤖
                    </h1>
                    <p style="color: #a8b5c8; font-size: 18px; margin: 0 0 24px 0;">
                        Hey {name}, you're now a member of the exclusive deal-hunting crew.
                    </p>
                    <table style="width: 100%; background: linear-gradient(145deg, #1a1f2e, #252b3d); border-radius: 16px; padding: 24px; margin: 24px 0;">
                        <tr>
                            <td>
                                <h2 style="color: #d4af37; margin: 0 0 16px 0; font-size: 20px;">What's Next?</h2>
                                <p style="color: #a8b5c8; margin: 0 0 12px 0; font-size: 16px;">✅ Browse thousands of clearance deals</p>
                                <p style="color: #a8b5c8; margin: 0 0 12px 0; font-size: 16px;">✅ Set up custom deal alerts ($10/mo each)</p>
                                <p style="color: #a8b5c8; margin: 0; font-size: 16px;">✅ Never miss a 50%+ off deal again</p>
                            </td>
                        </tr>
                    </table>
                    <a href="https://gloorbot.com" style="display: inline-block; background: linear-gradient(135deg, #d4af37, #b8860b); color: #1a1f2e; padding: 16px 32px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 16px; margin-top: 16px;">
                        Start Hunting Deals →
                    </a>
                </td>
            </tr>
        </table>
    </body>
    </html>
    '''
    
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=Email(SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME),
            to_emails=To(to_email),
            subject="Welcome to GloorBot! 🤖 Your deal-hunting journey begins",
            html_content=Content("text/html", html),
        )
        response = sg.send(message)
        return response.status_code in (200, 201, 202)
    except Exception as e:
        LOGGER.error("Welcome email error: %s", e)
        return False
