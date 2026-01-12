"""Background processor for matching deals to alerts and sending notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.notifications.models import DealAlert, NotificationLog, NotificationType, NotificationFrequency
from app.notifications.email_service import send_deal_alert_email, is_email_configured
from app.auth.models import User

LOGGER = get_logger(__name__)


def process_new_deals(session: Session, deals: list[dict[str, Any]]) -> dict[str, int]:
    """
    Process new deals and send notifications to matching alerts.
    
    This should be called after new deals are ingested into the database.
    
    Returns a summary dict with counts of alerts matched and emails sent.
    """
    if not deals:
        return {"alerts_matched": 0, "emails_sent": 0}
    
    # Get all active instant alerts
    active_alerts = session.query(DealAlert).filter(
        DealAlert.is_active == True,
        DealAlert.email_enabled == True,
        DealAlert.frequency == NotificationFrequency.INSTANT,
    ).all()
    
    if not active_alerts:
        return {"alerts_matched": 0, "emails_sent": 0}
    
    alerts_matched = 0
    emails_sent = 0
    
    # Group alerts by user for efficiency
    user_alerts: dict[int, list[DealAlert]] = {}
    for alert in active_alerts:
        user_alerts.setdefault(alert.user_id, []).append(alert)
    
    # Check each alert against new deals
    for user_id, alerts in user_alerts.items():
        for alert in alerts:
            # Find matching deals
            matching_deals = [deal for deal in deals if alert.matches_deal(deal)]
            
            if not matching_deals:
                continue
            
            # Filter out already-notified deals
            new_deals = []
            for deal in matching_deals:
                sku = deal.get("sku", "")
                store_id = deal.get("store_id", "")
                
                # Check if we've already notified for this deal
                existing = session.query(NotificationLog).filter(
                    NotificationLog.alert_id == alert.id,
                    NotificationLog.deal_sku == sku,
                    NotificationLog.deal_store_id == store_id,
                ).first()
                
                if not existing:
                    new_deals.append(deal)
            
            if not new_deals:
                continue
            
            alerts_matched += 1
            
            # Get user email
            user = session.query(User).filter(User.id == user_id).first()
            if not user or not user.email:
                continue
            
            # Determine criteria string for email
            if alert.alert_type == NotificationType.CATEGORY:
                criteria = alert.category or "Any Category"
            else:
                criteria = alert.keywords or "Any Keyword"
            
            # Send email
            if is_email_configured():
                success = send_deal_alert_email(
                    to_email=user.email,
                    alert_name=alert.name,
                    deals=new_deals,
                    alert_type=alert.alert_type.value,
                    criteria=criteria,
                )
                
                if success:
                    emails_sent += 1
            
            # Log notifications to prevent duplicates
            for deal in new_deals:
                log = NotificationLog(
                    alert_id=alert.id,
                    user_id=user_id,
                    deal_sku=deal.get("sku", ""),
                    deal_store_id=deal.get("store_id", ""),
                    deal_data=json.dumps(deal, default=str),
                    email_sent=is_email_configured(),
                    sent_at=datetime.now(timezone.utc) if is_email_configured() else None,
                )
                session.add(log)
            
            # Update alert last triggered time
            alert.last_triggered_at = datetime.now(timezone.utc)
            session.add(alert)
    
    session.commit()
    
    LOGGER.info(
        "Processed %d deals, matched %d alerts, sent %d emails",
        len(deals), alerts_matched, emails_sent
    )
    
    return {"alerts_matched": alerts_matched, "emails_sent": emails_sent}


def send_daily_digest(session: Session) -> int:
    """
    Send daily digest emails for alerts configured for daily frequency.
    Should be called by a scheduled job once per day.
    
    Returns number of digest emails sent.
    """
    # Get all active daily alerts
    daily_alerts = session.query(DealAlert).filter(
        DealAlert.is_active == True,
        DealAlert.email_enabled == True,
        DealAlert.frequency == NotificationFrequency.DAILY,
    ).all()
    
    if not daily_alerts:
        return 0
    
    emails_sent = 0
    
    # For each alert, find unsent notifications from the last 24 hours
    for alert in daily_alerts:
        # Get pending notification logs
        pending_logs = session.query(NotificationLog).filter(
            NotificationLog.alert_id == alert.id,
            NotificationLog.email_sent == False,
        ).all()
        
        if not pending_logs:
            continue
        
        # Parse deal data
        deals = []
        for log in pending_logs:
            if log.deal_data:
                try:
                    deals.append(json.loads(log.deal_data))
                except json.JSONDecodeError:
                    pass
        
        if not deals:
            continue
        
        # Get user
        user = session.query(User).filter(User.id == alert.user_id).first()
        if not user or not user.email:
            continue
        
        # Determine criteria
        if alert.alert_type == NotificationType.CATEGORY:
            criteria = alert.category or "Any Category"
        else:
            criteria = alert.keywords or "Any Keyword"
        
        # Send digest email
        if is_email_configured():
            success = send_deal_alert_email(
                to_email=user.email,
                alert_name=f"{alert.name} (Daily Digest)",
                deals=deals,
                alert_type=alert.alert_type.value,
                criteria=criteria,
            )
            
            if success:
                emails_sent += 1
                
                # Mark logs as sent
                for log in pending_logs:
                    log.email_sent = True
                    log.sent_at = datetime.now(timezone.utc)
                
                alert.last_triggered_at = datetime.now(timezone.utc)
    
    session.commit()
    
    LOGGER.info("Sent %d daily digest emails", emails_sent)
    return emails_sent
