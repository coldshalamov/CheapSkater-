"""Timezone conversion utilities for regional timestamp display."""

from datetime import datetime, timedelta, timezone


def convert_utc_to_regional_time(dt: datetime | None, region: str | None) -> datetime | None:
    """Convert UTC datetime to regional timezone (Pacific for WA_OR, Eastern for FL)."""
    if dt is None:
        return None
    
    # Ensure datetime is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to UTC if not already
    dt_utc = dt.astimezone(timezone.utc)
    
    # Determine offset based on region
    if region == "FL":
        # Eastern Time: UTC-5 (EST) or UTC-4 (EDT)
        # Simplified: use UTC-5 for now (can add DST logic later)
        offset = timedelta(hours=-5)
    else:  # WA_OR or default
        # Pacific Time: UTC-8 (PST) or UTC-7 (PDT)
        # Simplified: use UTC-8 for now (can add DST logic later)
        offset = timedelta(hours=-8)
    
    return dt_utc + offset


def format_regional_timestamp(dt: datetime | None, region: str | None, format_str: str = "%I:%M %p") -> str:
    """Format a UTC datetime in regional timezone with appropriate timezone label."""
    if dt is None:
        return ""
    
    regional_dt = convert_utc_to_regional_time(dt, region)
    if regional_dt is None:
        return ""
    
    # Determine timezone abbreviation
    if region == "FL":
        tz_abbr = "ET"  # Eastern Time
    else:  # WA_OR or default
        tz_abbr = "PT"  # Pacific Time
    
    return f"{regional_dt.strftime(format_str)} {tz_abbr}"


def format_regional_full_timestamp(dt: datetime | None, region: str | None) -> str:
    """Format a UTC datetime with full date and time in regional timezone."""
    if dt is None:
        return ""
    
    return format_regional_timestamp(dt, region, "%b %d, %Y %I:%M %p")
