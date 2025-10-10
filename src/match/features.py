"""Feature extraction for market matching."""

import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Set


# Common stopwords
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'will', 'be', 'is', 'are', 'was', 'were',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'can', 'could',
    'would', 'should', 'may', 'might', 'must', 'shall'
}

# Political offices
OFFICES = {
    'president', 'vice president', 'vp', 'senator', 'representative', 'rep',
    'governor', 'mayor', 'congress', 'senate', 'house', 'potus', 'scotus'
}

# US States/Jurisdictions
JURISDICTIONS = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
    'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
    'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new hampshire', 'new jersey', 'new mexico', 'new york',
    'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
    'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
    'west virginia', 'wisconsin', 'wyoming', 'dc', 'federal', 'national',
    'us', 'usa', 'united states'
}

# Parties
PARTIES = {'democrat', 'republican', 'gop', 'dem', 'democratic', 'libertarian', 'green'}


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove punctuation."""
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Remove common punctuation but keep spaces
    text = re.sub(r'[^\w\s-]', ' ', text)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def normalize_person(name: str) -> str:
    """Normalize person name: accent-insensitive, lowercase."""
    if not name:
        return ""
    
    # Remove accents
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    
    # Normalize
    name = normalize_text(name)
    
    # Remove common titles
    name = re.sub(r'\b(mr|mrs|ms|dr|prof|sen|rep)\b\.?', '', name)
    
    return name.strip()


def remove_stopwords(text: str) -> str:
    """Remove stopwords from text."""
    words = text.split()
    return ' '.join(w for w in words if w.lower() not in STOPWORDS)


def extract_year(text: str) -> Optional[int]:
    """Extract 4-digit year from text."""
    matches = re.findall(r'\b(20\d{2})\b', text)
    if matches:
        return int(matches[0])
    return None


def extract_office(text: str) -> Optional[str]:
    """Extract political office from text."""
    text_lower = text.lower()
    for office in OFFICES:
        if re.search(r'\b' + re.escape(office) + r'\b', text_lower):
            # Normalize some offices
            if office in ('vp', 'vice president'):
                return 'vice_president'
            if office in ('rep', 'representative'):
                return 'representative'
            if office == 'potus':
                return 'president'
            return office.replace(' ', '_')
    return None


def extract_jurisdiction(text: str) -> Optional[str]:
    """Extract jurisdiction/state from text."""
    text_lower = text.lower()
    for jurisdiction in JURISDICTIONS:
        if re.search(r'\b' + re.escape(jurisdiction) + r'\b', text_lower):
            return jurisdiction.replace(' ', '_')
    return None


def extract_party(text: str) -> Optional[str]:
    """Extract party from text."""
    text_lower = text.lower()
    for party in PARTIES:
        if re.search(r'\b' + re.escape(party) + r'\b', text_lower):
            # Normalize
            if party in ('gop', 'republican'):
                return 'republican'
            if party in ('dem', 'democrat', 'democratic'):
                return 'democratic'
            return party
    return None


def extract_person_names(text: str) -> List[str]:
    """Extract potential person names (capitalized sequences)."""
    # Look for capitalized words that might be names
    # This is a simple heuristic
    words = text.split()
    names = []
    current_name = []
    
    for word in words:
        # Remove punctuation from word
        clean_word = re.sub(r'[^\w\s]', '', word)
        
        if clean_word and clean_word[0].isupper() and len(clean_word) > 1:
            # Skip if it's a known keyword
            if clean_word.lower() not in {'will', 'bitcoin', 'fed', 'rate', 'ceo', 'election'}:
                current_name.append(clean_word)
        else:
            if current_name and len(current_name) >= 2:  # At least first + last name
                names.append(' '.join(current_name))
            current_name = []
    
    # Don't forget the last name
    if current_name and len(current_name) >= 2:
        names.append(' '.join(current_name))
    
    return [normalize_person(name) for name in names]


def extract_threshold(text: str) -> Optional[float]:
    """Extract numerical threshold (e.g., Bitcoin price, polling %)."""
    # Look for patterns like "$150,000", "150000", "75%"
    
    # Dollar amounts
    matches = re.findall(r'\$[\d,]+(?:\.\d+)?', text)
    if matches:
        # Remove $ and commas, convert to float
        value = matches[0].replace('$', '').replace(',', '')
        try:
            return float(value)
        except ValueError:
            pass
    
    # Percentages
    matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', text)
    if matches:
        try:
            return float(matches[0])
        except ValueError:
            pass
    
    # Plain numbers (with commas)
    matches = re.findall(r'\b[\d,]+(?:\.\d+)?\b', text)
    if matches:
        # Get the largest number (most likely the threshold)
        numbers = []
        for match in matches:
            try:
                num = float(match.replace(',', ''))
                if num > 100:  # Likely a threshold, not a year or small number
                    numbers.append(num)
            except ValueError:
                pass
        if numbers:
            return max(numbers)
    
    return None


def extract_date_keywords(text: str) -> List[str]:
    """Extract date-related keywords."""
    keywords = []
    text_lower = text.lower()
    
    # Month names
    months = ['january', 'february', 'march', 'april', 'may', 'june',
              'july', 'august', 'september', 'october', 'november', 'december']
    for month in months:
        if month in text_lower:
            keywords.append(month)
    
    # Specific date patterns
    date_patterns = [
        r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # MM/DD/YYYY
        r'\b(\d{4}-\d{2}-\d{2})\b',  # YYYY-MM-DD
        r'\b(december \d+)',  # December 31
        r'\b(jan \d+)', r'\b(feb \d+)', r'\b(mar \d+)',  # Abbreviated months
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text_lower)
        keywords.extend(matches)
    
    return keywords


def extract_crypto_ticker(text: str) -> Optional[str]:
    """Extract cryptocurrency ticker."""
    text_upper = text.upper()
    
    # Common crypto tickers
    cryptos = ['BTC', 'ETH', 'BITCOIN', 'ETHEREUM', 'SOL', 'SOLANA', 'DOGE', 'DOGECOIN']
    
    for crypto in cryptos:
        if re.search(r'\b' + re.escape(crypto) + r'\b', text_upper):
            # Normalize to ticker
            if crypto in ('BITCOIN', 'BTC'):
                return 'BTC'
            if crypto in ('ETHEREUM', 'ETH'):
                return 'ETH'
            if crypto in ('SOLANA', 'SOL'):
                return 'SOL'
            if crypto in ('DOGECOIN', 'DOGE'):
                return 'DOGE'
            return crypto
    
    return None


def extract_market_type(text: str) -> str:
    """Determine market type from text."""
    text_lower = text.lower()
    
    # Check for different market types
    if any(keyword in text_lower for keyword in ['election', 'president', 'senator', 'governor', 'vote']):
        return 'election'
    
    if any(keyword in text_lower for keyword in ['bitcoin', 'btc', 'ethereum', 'crypto', 'doge']):
        return 'crypto'
    
    if any(keyword in text_lower for keyword in ['ceo', 'out as', 'resign', 'fired']):
        return 'corporate'
    
    if any(keyword in text_lower for keyword in ['fed', 'rate', 'inflation', 'gdp', 'unemployment']):
        return 'economy'
    
    if any(keyword in text_lower for keyword in ['market cap', 'largest company', 'valuation']):
        return 'market_cap'
    
    if any(keyword in text_lower for keyword in ['wins', 'loses', 'score', 'points', 'game', 'match']):
        return 'sports'
    
    return 'other'


def extract_features(title: str, description: str = "") -> Dict[str, any]:
    """
    Extract features from market title and description.
    
    Returns:
        Dictionary with extracted features including:
        - market_type: election, crypto, corporate, economy, sports, other
        - year: extracted 4-digit year
        - office: political office if applicable
        - jurisdiction: state/federal jurisdiction
        - party: political party
        - persons: list of person names
        - threshold: numerical threshold (price, percentage, etc.)
        - crypto_ticker: BTC, ETH, etc.
        - date_keywords: list of date-related terms
        - normalized_text: normalized title + description
        - keywords: set of important keywords (no stopwords)
    """
    combined_text = f"{title} {description}".strip()
    normalized = normalize_text(combined_text)
    
    features = {
        'title': title,
        'description': description,
        'market_type': extract_market_type(combined_text),
        'year': extract_year(combined_text),
        'office': extract_office(combined_text),
        'jurisdiction': extract_jurisdiction(combined_text),
        'party': extract_party(combined_text),
        'persons': extract_person_names(title),  # Focus on title for names
        'threshold': extract_threshold(combined_text),
        'crypto_ticker': extract_crypto_ticker(combined_text),
        'date_keywords': extract_date_keywords(combined_text),
        'normalized_text': normalized,
        'keywords': set(remove_stopwords(normalized).split()),
    }
    
    return features

