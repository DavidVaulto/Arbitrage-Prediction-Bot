"""Canonical key generation for market matching."""

from typing import Dict


def make_key(features: Dict[str, any]) -> str:
    """
    Generate a canonical key for a market based on its features.
    
    Format examples:
    - ELECTION:president:2024:federal:trump
    - CRYPTO:BTC_TARGET:150000:2025-12-31
    - CORPORATE:CEO_CHANGE:apple:tim_cook:2025
    - ECONOMY:FED_RATE:hike:2025
    - MARKET_CAP:largest_company:apple:2025-12-31
    
    Args:
        features: Feature dictionary from extract_features()
        
    Returns:
        Canonical key string
    """
    market_type = features.get('market_type', 'other').upper()
    
    if market_type == 'ELECTION':
        office = features.get('office', 'unknown')
        year = features.get('year', 'unknown')
        jurisdiction = features.get('jurisdiction', 'federal')
        
        # Try to get person name
        persons = features.get('persons', [])
        person_key = persons[0].replace(' ', '_') if persons else 'unknown'
        
        # Try to get party
        party = features.get('party', '')
        if party:
            person_key = f"{party}_{person_key}"
        
        return f"ELECTION:{office}:{year}:{jurisdiction}:{person_key}"
    
    elif market_type == 'CRYPTO':
        ticker = features.get('crypto_ticker', 'unknown')
        threshold = features.get('threshold')
        year = features.get('year', '')
        
        # Get date keywords for more specificity
        date_keywords = features.get('date_keywords', [])
        date_str = date_keywords[0] if date_keywords else str(year) if year else 'unknown'
        
        threshold_str = f"{int(threshold)}" if threshold else 'unknown'
        
        return f"CRYPTO:{ticker}_TARGET:{threshold_str}:{date_str}"
    
    elif market_type == 'CORPORATE':
        persons = features.get('persons', [])
        person_key = persons[0].replace(' ', '_') if persons else 'unknown'
        
        # Extract company from keywords or title
        title_lower = features.get('title', '').lower()
        companies = ['apple', 'google', 'microsoft', 'amazon', 'meta', 'tesla', 'nvidia',
                     'openai', 'coinbase', 'twitch']
        
        company_key = 'unknown'
        for company in companies:
            if company in title_lower:
                company_key = company
                break
        
        year = features.get('year', 'unknown')
        
        return f"CORPORATE:CEO_CHANGE:{company_key}:{person_key}:{year}"
    
    elif market_type == 'ECONOMY':
        # Look for specific economic indicators
        title_lower = features.get('title', '').lower()
        
        if 'fed' in title_lower or 'federal reserve' in title_lower:
            if 'rate' in title_lower:
                if 'hike' in title_lower or 'raise' in title_lower:
                    action = 'hike'
                elif 'cut' in title_lower or 'lower' in title_lower:
                    action = 'cut'
                else:
                    action = 'change'
                
                year = features.get('year', 'unknown')
                return f"ECONOMY:FED_RATE:{action}:{year}"
        
        # Generic economy event
        year = features.get('year', 'unknown')
        threshold = features.get('threshold')
        threshold_str = f"{int(threshold)}" if threshold else ''
        
        return f"ECONOMY:indicator:{threshold_str}:{year}"
    
    elif market_type == 'MARKET_CAP':
        title_lower = features.get('title', '').lower()
        
        # Extract company
        companies = ['apple', 'google', 'microsoft', 'amazon', 'meta', 'tesla', 'nvidia',
                     'alphabet', 'saudi aramco']
        company_key = 'unknown'
        for company in companies:
            if company in title_lower:
                company_key = company.replace(' ', '_')
                break
        
        # Get date
        date_keywords = features.get('date_keywords', [])
        date_str = date_keywords[0] if date_keywords else str(features.get('year', 'unknown'))
        
        return f"MARKET_CAP:largest_company:{company_key}:{date_str}"
    
    elif market_type == 'SPORTS':
        # Sports markets are typically too specific for cross-venue matching
        # But generate a key anyway
        title_words = features.get('title', '').lower().split()[:5]  # First 5 words
        key_words = '_'.join(title_words)
        
        return f"SPORTS:{key_words}"
    
    else:
        # Generic key based on normalized text
        keywords = list(features.get('keywords', set()))[:5]
        if keywords:
            key_words = '_'.join(sorted(keywords)[:3])
            return f"OTHER:{key_words}"
        else:
            return f"OTHER:unknown"


def normalize_key(key: str) -> str:
    """Normalize a canonical key for consistent matching."""
    # Convert to uppercase, remove extra colons
    key = key.upper()
    key = ':'.join(part.strip() for part in key.split(':') if part.strip())
    return key


def keys_match(key1: str, key2: str) -> bool:
    """Check if two canonical keys match."""
    return normalize_key(key1) == normalize_key(key2)


def key_distance(key1: str, key2: str) -> float:
    """
    Compute distance between two canonical keys.
    Returns 0.0 for exact match, 1.0 for completely different.
    """
    norm1 = normalize_key(key1)
    norm2 = normalize_key(key2)
    
    if norm1 == norm2:
        return 0.0
    
    # Split into parts
    parts1 = norm1.split(':')
    parts2 = norm2.split(':')
    
    # If different market types, maximum distance
    if parts1[0] != parts2[0]:
        return 1.0
    
    # Count matching parts
    min_len = min(len(parts1), len(parts2))
    max_len = max(len(parts1), len(parts2))
    
    if max_len == 0:
        return 1.0
    
    matching = sum(1 for i in range(min_len) if parts1[i] == parts2[i])
    
    # Distance is inverse of match ratio
    return 1.0 - (matching / max_len)

