"""Suggest a better-matching station when a song's reactions fit another station's feelings."""
from __future__ import annotations

from typing import Dict, List, Optional

from radio.services.recommend import feeling_keyword


def _norm(value: str) -> str:
    return (value or '').strip().replace('️', '').casefold()


def _keys(value: str) -> set:
    return {_norm(value), _norm(feeling_keyword(value))}


def matched_reactions(reactions: List[str], feelings: List[str]) -> List[str]:
    """Reactions that match a feeling directly or through the shared emoji→keyword map (🌙 ~ "late night")."""
    feeling_keys = set().union(*(_keys(feeling) for feeling in feelings)) if feelings else set()
    return [reaction for reaction in reactions if _keys(reaction) & feeling_keys]


def suggest_station(reactions: List[str], current, stations) -> Optional[Dict]:
    if not reactions:
        return None
    current_score = len(matched_reactions(reactions, current.feelings or [])) if current else 0
    scored = []
    for station in stations:
        if current is not None and station.id == current.id:
            continue
        matched = matched_reactions(reactions, station.feelings or [])
        if matched:
            scored.append((len(matched), station, matched))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best, matched = scored[0]
    # Ties (with the current station or between candidates) → no suggestion.
    if best_score <= current_score or (len(scored) > 1 and scored[1][0] == best_score):
        return None
    return {'stationId': str(best.id), 'name': best.name, 'matched': matched}
