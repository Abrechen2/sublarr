"""AniDB ID Resolver — resolves AniDB IDs from Sonarr Custom Fields or TVDB mappings.

Provides multiple strategies for resolving AniDB IDs:
1. Sonarr Custom Fields (highest priority)
2. Local cache (TVDB → AniDB mappings)
3. External mapping APIs (future: AniList, TheTVDB cross-references)

License: GPL-3.0
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from config import get_settings
from database import get_anidb_mapping, save_anidb_mapping

logger = logging.getLogger(__name__)


def extract_anidb_from_custom_fields(series: dict, custom_field_name: str = None) -> Optional[int]:
    """Extract AniDB ID from Sonarr series Custom Fields.
    
    Args:
        series: Sonarr series dict (from API)
        custom_field_name: Optional custom field name to check (defaults to config)
    
    Returns:
        AniDB ID as int, or None if not found
    """
    if not series:
        return None
    
    settings = get_settings()
    field_name = custom_field_name or settings.anidb_custom_field_name
    
    # Check customFields dict (Sonarr v3 structure)
    custom_fields = series.get("customFields", {})
    if custom_fields:
        # Try various field name variations
        possible_names = [
            field_name,
            "anidb_id",
            "anidbId",
            "AniDB",
            "AniDB ID",
            "anidb",
        ]
        
        for name in possible_names:
            if not name:
                continue
            value = custom_fields.get(name)
            if value:
                try:
                    # Handle both string and int values
                    anidb_id = int(value) if isinstance(value, (int, str)) else None
                    if anidb_id and anidb_id > 0:
                        logger.debug("Found AniDB ID %d in Custom Field '%s'", anidb_id, name)
                        return anidb_id
                except (ValueError, TypeError):
                    continue
    
    return None


def get_anidb_id(tvdb_id: Optional[int] = None, series_title: str = "", 
                 series: dict = None) -> Optional[int]:
    """Resolve AniDB ID from multiple sources.
    
    Priority order:
    1. Sonarr Custom Fields (if series dict provided)
    2. Local cache (if tvdb_id provided)
    3. Future: External mapping APIs
    
    Args:
        tvdb_id: Optional TVDB ID for cache lookup
        series_title: Optional series title (for logging)
        series: Optional Sonarr series dict (for Custom Fields extraction)
    
    Returns:
        AniDB ID as int, or None if not found
    """
    settings = get_settings()
    
    # Check if AniDB integration is enabled
    if not settings.anidb_enabled:
        return None
    
    # Strategy 1: Sonarr Custom Fields (highest priority)
    if series:
        anidb_id = extract_anidb_from_custom_fields(series)
        if anidb_id:
            # Cache the mapping if we have a TVDB ID
            if tvdb_id and settings.anidb_fallback_to_mapping:
                try:
                    save_anidb_mapping(tvdb_id, anidb_id, series_title or "")
                except Exception as e:
                    logger.warning("Failed to cache AniDB mapping: %s", e)
            return anidb_id
    
    # Strategy 2: Local cache (if TVDB ID available)
    if tvdb_id and settings.anidb_fallback_to_mapping:
        cached = get_anidb_mapping(tvdb_id)
        if cached:
            logger.debug("Found cached AniDB ID %d for TVDB ID %d", cached, tvdb_id)
            return cached
    
    # Strategy 3: External mapping APIs (future implementation)
    # Could use AniList API, TheTVDB cross-references, etc.
    # For now, return None if not found in Custom Fields or cache
    
    return None
