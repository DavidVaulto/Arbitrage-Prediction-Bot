"""Exact canonical key generation for deterministic matching."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MarketLite:
    """Lightweight market representation."""
    title: str
    description: str = ""
    expires_at: Optional[datetime] = None
    meta: dict = None


def normalize_ascii(text: str) -> str:
    """Convert to ASCII, removing accents."""
    if not text:
        return ""
    # Normalize to NFD (decomposed form) and filter out combining marks
    nfd = unicodedata.normalize('NFD', text)
    ascii_text = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return ascii_text


def normalize_name(name: str) -> str:
    """
    Normalize person name for canonical key.
    - ASCII conversion
    - Lowercase
    - Remove middle initials
    - Collapse whitespace
    - Remove punctuation except hyphens
    """
    if not name:
        return ""
    
    # Convert to ASCII
    name = normalize_ascii(name)
    
    # Lowercase
    name = name.lower()
    
    # Remove titles
    name = re.sub(r'\b(mr|mrs|ms|dr|prof|sen|rep)\b\.?', '', name)
    
    # Remove middle initials (single letters followed by period)
    name = re.sub(r'\s+[a-z]\.\s+', ' ', name)
    
    # Remove punctuation except hyphens
    name = re.sub(r'[^\w\s-]', '', name)
    
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    
    return name.strip()


def extract_office(text: str) -> Optional[str]:
    """Extract and normalize political office."""
    text_lower = text.lower()
    
    # Map variations to canonical forms
    if re.search(r'\b(president|presidential|potus)\b', text_lower):
        return "PRESIDENT"
    if re.search(r'\b(vice president|vp)\b', text_lower):
        return "VP"
    if re.search(r'\b(senator|senate)\b', text_lower):
        return "SENATE"
    if re.search(r'\b(representative|house|congress)\b', text_lower):
        return "HOUSE"
    if re.search(r'\b(governor)\b', text_lower):
        return "GOVERNOR"
    
    return None


def extract_party(text: str) -> Optional[str]:
    """Extract and normalize party."""
    text_lower = text.lower()
    
    if re.search(r'\b(dem|democrat|democratic)\b', text_lower):
        return "DEM"
    if re.search(r'\b(rep|republican|gop)\b', text_lower):
        return "REPUBLICAN"
    if re.search(r'\b(independent|ind)\b', text_lower):
        return "INDEPENDENT"
    
    return None


def extract_jurisdiction(text: str) -> Optional[str]:
    """Extract and normalize jurisdiction."""
    text_lower = text.lower()
    
    # Federal/National
    if re.search(r'\b(federal|national|us|usa|united states)\b', text_lower):
        return "US"
    
    # States (just a few key ones for demo)
    states = {
        'california': 'CA', 'texas': 'TX', 'florida': 'FL', 'new york': 'NY',
        'pennsylvania': 'PA', 'ohio': 'OH', 'georgia': 'GA', 'michigan': 'MI',
        'north carolina': 'NC', 'arizona': 'AZ', 'nevada': 'NV', 'wisconsin': 'WI'
    }
    
    for state_name, state_code in states.items():
        if state_name in text_lower:
            return state_code
    
    return None


def extract_year(text: str) -> Optional[int]:
    """Extract 4-digit year."""
    matches = re.findall(r'\b(20\d{2})\b', text)
    if matches:
        return int(matches[0])
    return None


def extract_person_name(text: str) -> Optional[str]:
    """
    Extract person name from text.
    Looks for capitalized sequences that are likely names.
    """
    # Look for common patterns like "Donald Trump" or "Biden"
    # This is a simplified approach
    words = text.split()
    
    # Common politician names (for demo)
    known_names = [
        'trump', 'biden', 'harris', 'desantis', 'newsom', 'pence',
        'obama', 'clinton', 'sanders', 'warren', 'cruz', 'rubio',
        'mcconnell', 'schumer', 'pelosi', 'mccarthy'
    ]
    
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word).lower()
        if clean_word in known_names:
            return normalize_name(clean_word)
    
    # Look for capitalized sequences
    potential_names = []
    current_name = []
    
    for word in words:
        clean = re.sub(r'[^\w\s]', '', word)
        if clean and clean[0].isupper() and len(clean) > 2:
            if clean.lower() not in {'will', 'the', 'election', 'win', 'wins'}:
                current_name.append(clean)
        else:
            if len(current_name) >= 2:  # First + Last name
                potential_names.append(' '.join(current_name))
            current_name = []
    
    if len(current_name) >= 2:
        potential_names.append(' '.join(current_name))
    
    if potential_names:
        return normalize_name(potential_names[0])
    
    return None


def extract_crypto_ticker(text: str) -> Optional[str]:
    """Extract crypto ticker."""
    text_upper = text.upper()
    
    if re.search(r'\b(BITCOIN|BTC)\b', text_upper):
        return "BTC"
    if re.search(r'\b(ETHEREUM|ETH)\b', text_upper):
        return "ETH"
    if re.search(r'\b(SOLANA|SOL)\b', text_upper):
        return "SOL"
    
    return None


def extract_threshold(text: str) -> Optional[int]:
    """Extract numerical threshold as integer."""
    # Look for dollar amounts
    matches = re.findall(r'\$[\d,]+(?:k|K)?', text)
    if matches:
        value_str = matches[0].replace('$', '').replace(',', '')
        if value_str.endswith(('k', 'K')):
            try:
                return int(float(value_str[:-1]) * 1000)
            except ValueError:
                pass
        else:
            try:
                return int(float(value_str))
            except ValueError:
                pass
    
    # Look for plain numbers
    matches = re.findall(r'\b([\d,]+(?:\.\d+)?)\b', text)
    for match in matches:
        try:
            num = float(match.replace(',', ''))
            if num >= 1000:  # Likely a threshold
                return int(num)
        except ValueError:
            continue
    
    return None


def extract_date(text: str, expires_at: Optional[datetime] = None) -> Optional[str]:
    """
    Extract date in YYYY-MM-DD format.
    First try explicit dates in text, then fall back to expires_at.
    """
    # Look for explicit dates
    date_patterns = [
        (r'(\d{4})-(\d{2})-(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', lambda m: f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"),
        (r'(december|dec)\s+(\d{1,2}),?\s+(\d{4})', lambda m: f"{m.group(3)}-12-{int(m.group(2)):02d}"),
        (r'(january|jan)\s+(\d{1,2}),?\s+(\d{4})', lambda m: f"{m.group(3)}-01-{int(m.group(2)):02d}"),
    ]
    
    text_lower = text.lower()
    for pattern, formatter in date_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                return formatter(match)
            except (ValueError, IndexError):
                continue
    
    # Fall back to expires_at
    if expires_at:
        return expires_at.strftime("%Y-%m-%d")
    
    return None


def extract_oscars_category(text: str) -> Optional[str]:
    """Extract Oscars category."""
    text_lower = text.lower()
    
    categories = {
        'best picture': 'PICTURE',
        'best director': 'DIRECTOR',
        'best actor': 'ACTOR',
        'best actress': 'ACTRESS',
        'best supporting actor': 'SUPPORTING_ACTOR',
        'best supporting actress': 'SUPPORTING_ACTRESS',
    }
    
    for full_name, short_name in categories.items():
        if full_name in text_lower:
            return short_name
    
    return None


def build_canonical_key(market: MarketLite) -> Optional[str]:
    """
    Build deterministic canonical key for a market.
    
    Returns None if required fields are missing.
    
    Supported formats:
    - ELECTION:{office}:{year}:{jurisdiction}:{party_or_person}
    - CRYPTO:{ticker}:{threshold}:{yyyy-mm-dd}
    - ECONOMY:{series}:{yyyy-mm-dd}
    - AWARDS:OSCARS:{category}:{year}:{person}
    
    Args:
        market: MarketLite with title, description, expires_at
        
    Returns:
        Canonical key string or None
    """
    combined_text = f"{market.title} {market.description}".strip()
    
    # Try ELECTION
    office = extract_office(combined_text)
    if office:
        year = extract_year(combined_text)
        jurisdiction = extract_jurisdiction(combined_text)
        person = extract_person_name(combined_text)
        party = extract_party(combined_text)
        
        # Need at least office and year
        if year:
            jurisdiction = jurisdiction or "US"  # Default to US
            
            # Prefer person over party
            identifier = person if person else party
            if not identifier:
                identifier = "UNKNOWN"
            
            return f"ELECTION:{office}:{year}:{jurisdiction}:{identifier}"
    
    # Try CRYPTO
    ticker = extract_crypto_ticker(combined_text)
    if ticker:
        threshold = extract_threshold(combined_text)
        date = extract_date(combined_text, market.expires_at)
        
        if threshold and date:
            return f"CRYPTO:{ticker}:{threshold}:{date}"
    
    # Try ECONOMY (Fed rate, CPI, etc.)
    text_lower = combined_text.lower()
    if any(keyword in text_lower for keyword in ['fed rate', 'federal reserve', 'interest rate', 'cpi', 'inflation']):
        date = extract_date(combined_text, market.expires_at)
        year = extract_year(combined_text)
        
        if 'fed rate' in text_lower or 'interest rate' in text_lower:
            series = "FED_RATE"
        elif 'cpi' in text_lower:
            series = "CPI"
        elif 'inflation' in text_lower:
            series = "INFLATION"
        else:
            series = "UNKNOWN"
        
        if date:
            return f"ECONOMY:{series}:{date}"
        elif year:
            return f"ECONOMY:{series}:{year}"
    
    # Try OSCARS
    if 'oscar' in text_lower or 'academy award' in text_lower:
        category = extract_oscars_category(combined_text)
        year = extract_year(combined_text)
        person = extract_person_name(combined_text)
        
        if category and year:
            person = person or "UNKNOWN"
            return f"AWARDS:OSCARS:{category}:{year}:{person}"
    
    # No match
    return None


def keys_match_exactly(key1: Optional[str], key2: Optional[str]) -> bool:
    """Check if two canonical keys match exactly."""
    if key1 is None or key2 is None:
        return False
    return key1 == key2

