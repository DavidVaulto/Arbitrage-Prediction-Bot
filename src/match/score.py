"""Scoring functions for market pair matching."""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List


def text_similarity(a: str, b: str) -> float:
    """Compute text similarity using SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def person_match_score(pm_persons: List[str], kalshi_persons: List[str]) -> float:
    """
    Score person name matches.
    Returns 1.0 if any exact match, 0.0 otherwise.
    """
    if not pm_persons or not kalshi_persons:
        return 0.0
    
    # Check for exact matches
    pm_set = set(p.lower() for p in pm_persons)
    kalshi_set = set(k.lower() for k in kalshi_persons)
    
    if pm_set & kalshi_set:  # Intersection
        return 1.0
    
    # Check for partial matches (last name match)
    for pm_name in pm_persons:
        pm_parts = pm_name.lower().split()
        if not pm_parts:
            continue
        pm_last = pm_parts[-1]
        
        for kalshi_name in kalshi_persons:
            kalshi_parts = kalshi_name.lower().split()
            if not kalshi_parts:
                continue
            kalshi_last = kalshi_parts[-1]
            
            if pm_last == kalshi_last and len(pm_last) > 2:
                return 0.8  # Partial match
    
    return 0.0


def office_match_score(pm_office: str, kalshi_office: str) -> float:
    """Score office match."""
    if not pm_office or not kalshi_office:
        return 0.0
    
    if pm_office == kalshi_office:
        return 1.0
    
    # Partial matches
    if pm_office in kalshi_office or kalshi_office in pm_office:
        return 0.5
    
    return 0.0


def jurisdiction_match_score(pm_jurisdiction: str, kalshi_jurisdiction: str) -> float:
    """Score jurisdiction match."""
    if not pm_jurisdiction or not kalshi_jurisdiction:
        return 0.0
    
    if pm_jurisdiction == kalshi_jurisdiction:
        return 1.0
    
    # Both are national/federal
    if pm_jurisdiction in ('federal', 'national', 'us', 'usa') and \
       kalshi_jurisdiction in ('federal', 'national', 'us', 'usa'):
        return 1.0
    
    return 0.0


def year_match_score(pm_year: int, kalshi_year: int) -> float:
    """Score year match."""
    if not pm_year or not kalshi_year:
        return 0.0
    
    if pm_year == kalshi_year:
        return 1.0
    
    # Adjacent years get partial credit
    if abs(pm_year - kalshi_year) == 1:
        return 0.3
    
    return 0.0


def date_proximity_score(pm_date: datetime, kalshi_date: datetime) -> float:
    """Score based on how close the expiry dates are."""
    if not pm_date or not kalshi_date:
        return 0.0
    
    # Calculate difference in days
    diff_days = abs((pm_date - kalshi_date).days)
    
    if diff_days == 0:
        return 1.0
    elif diff_days <= 1:
        return 0.9
    elif diff_days <= 7:
        return 0.7
    elif diff_days <= 30:
        return 0.5
    elif diff_days <= 90:
        return 0.3
    else:
        return 0.1


def threshold_match_score(pm_threshold: float, kalshi_threshold: float) -> float:
    """Score threshold similarity (for crypto/numeric markets)."""
    if pm_threshold is None or kalshi_threshold is None:
        return 0.0
    
    if pm_threshold == kalshi_threshold:
        return 1.0
    
    # Calculate relative difference
    max_val = max(abs(pm_threshold), abs(kalshi_threshold))
    if max_val == 0:
        return 0.0
    
    relative_diff = abs(pm_threshold - kalshi_threshold) / max_val
    
    if relative_diff < 0.01:  # Within 1%
        return 0.95
    elif relative_diff < 0.05:  # Within 5%
        return 0.8
    elif relative_diff < 0.10:  # Within 10%
        return 0.6
    elif relative_diff < 0.20:  # Within 20%
        return 0.4
    else:
        return 0.0


def keyword_overlap_score(pm_keywords: set, kalshi_keywords: set) -> float:
    """Score based on keyword overlap."""
    if not pm_keywords or not kalshi_keywords:
        return 0.0
    
    intersection = pm_keywords & kalshi_keywords
    union = pm_keywords | kalshi_keywords
    
    if not union:
        return 0.0
    
    # Jaccard similarity
    return len(intersection) / len(union)


def score_pair(
    pm_features: Dict[str, any],
    kalshi_features: Dict[str, any],
    weights: Dict[str, float] = None
) -> float:
    """
    Score a PM-Kalshi market pair.
    
    Default weights:
    - name_similarity: 0.35
    - person_exact: 0.25
    - office: 0.15
    - jurisdiction: 0.10
    - year: 0.10
    - date_proximity: 0.05
    
    Args:
        pm_features: Features extracted from Polymarket market
        kalshi_features: Features extracted from Kalshi market
        weights: Optional custom weights dict
        
    Returns:
        Score between 0.0 and 1.0
    """
    if weights is None:
        weights = {
            'name_similarity': 0.35,
            'person_exact': 0.25,
            'office': 0.15,
            'jurisdiction': 0.10,
            'year': 0.10,
            'date_proximity': 0.05,
        }
    
    scores = {}
    
    # Text similarity (title)
    scores['name_similarity'] = text_similarity(
        pm_features.get('title', ''),
        kalshi_features.get('title', '')
    )
    
    # Person match
    scores['person_exact'] = person_match_score(
        pm_features.get('persons', []),
        kalshi_features.get('persons', [])
    )
    
    # Office match
    scores['office'] = office_match_score(
        pm_features.get('office'),
        kalshi_features.get('office')
    )
    
    # Jurisdiction match
    scores['jurisdiction'] = jurisdiction_match_score(
        pm_features.get('jurisdiction'),
        kalshi_features.get('jurisdiction')
    )
    
    # Year match
    scores['year'] = year_match_score(
        pm_features.get('year'),
        kalshi_features.get('year')
    )
    
    # Date proximity (for expiry dates)
    # Note: This would need actual datetime objects
    scores['date_proximity'] = 0.0  # Placeholder
    
    # Calculate weighted score
    total_score = sum(scores[key] * weights[key] for key in weights.keys())
    
    return total_score


def score_pair_with_market_type(
    pm_features: Dict[str, any],
    kalshi_features: Dict[str, any]
) -> float:
    """
    Score a pair using market-type-specific weights.
    
    Different market types emphasize different features:
    - Election: Person names, office, jurisdiction, year
    - Crypto: Threshold, date, ticker
    - Corporate: Person names, keywords
    - Economy: Keywords, threshold, date
    """
    pm_type = pm_features.get('market_type', 'other')
    kalshi_type = kalshi_features.get('market_type', 'other')
    
    # If market types don't match, penalize heavily
    if pm_type != kalshi_type and pm_type != 'other' and kalshi_type != 'other':
        return 0.0
    
    # Market-type-specific weights
    if pm_type == 'election':
        weights = {
            'name_similarity': 0.25,
            'person_exact': 0.35,
            'office': 0.20,
            'jurisdiction': 0.10,
            'year': 0.10,
            'date_proximity': 0.00,
        }
    elif pm_type == 'crypto':
        # For crypto, we'd want threshold and ticker to matter more
        # But since we use fixed weights, adjust accordingly
        weights = {
            'name_similarity': 0.40,
            'person_exact': 0.00,
            'office': 0.00,
            'jurisdiction': 0.00,
            'year': 0.30,
            'date_proximity': 0.30,
        }
    elif pm_type == 'corporate':
        weights = {
            'name_similarity': 0.35,
            'person_exact': 0.40,
            'office': 0.00,
            'jurisdiction': 0.00,
            'year': 0.15,
            'date_proximity': 0.10,
        }
    else:
        # Default weights
        weights = {
            'name_similarity': 0.35,
            'person_exact': 0.25,
            'office': 0.15,
            'jurisdiction': 0.10,
            'year': 0.10,
            'date_proximity': 0.05,
        }
    
    return score_pair(pm_features, kalshi_features, weights)

