from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal

RESCUE_SIGNALS: dict[str, list[str]] = {
    "spoilage": [
        "before it goes bad", "about to expire", "going bad", "gone off",
        "about to go off", "will expire", "past its prime", "past their prime",
        "bozulmadan", "sona ermeden", "çürümeden", "bitmeden", "bozulacak",
        "son kullanma", "bozulma",
    ],
    "no_storage": [
        "no freezer", "no fridge", "without freezer", "without fridge",
        "minimal freezer", "no space", "can't freeze", "cannot freeze",
        "dondurucu yok", "buzdolabı yok", "dondurucum yok",
        "soğutucum yok", "saklayamıyorum",
    ],
    "leftovers": [
        "leftovers", "use up", "use them up", "leftover", "use before",
        "need to use", "got a bunch", "too many", "excess",
        "artık", "kullanmak", "fazla", "çok var", "kullanmalıyım",
        "tüketmem lazım",
    ],
    "time_pressure": [
        "today", "tonight", "right now", "asap", "urgent", "quickly",
        "by tonight", "by today", "this afternoon",
        "bugün", "bu gece", "hemen", "acil", "çabuk", "şimdi",
        "bu akşam", "bu öğleden sonra",
    ],
    "budget": [
        "cheap", "budget", "affordable", "save money", "don't waste",
        "food waste", "zero waste", "on a budget",
        "bütçe", "ekonomik", "israf etme", "ziyan etme", "ucuz",
        "para biriktir",
    ],
}

_PEOPLE_COUNT_RE = re.compile(
    r"(?:family of|for|feeding)\s+(\d+)|(\d+)\s+(?:people|persons|kişi|kişilik)",
    re.IGNORECASE,
)

_TIME_PRESSURE_MAP: dict[str, Literal["today", "tonight", "tomorrow", "this_week"]] = {
    "today": "today", "bugün": "today",
    "tonight": "tonight", "bu gece": "tonight", "this evening": "tonight",
    "tomorrow": "tomorrow", "yarın": "tomorrow",
    "this week": "this_week", "bu hafta": "this_week",
}


@dataclass
class IntentResult:
    is_food_rescue: bool
    score: int
    matched_signals: list[str]
    no_freezer: bool = False
    people_count: int = 1
    time_pressure: Literal["today", "tonight", "tomorrow", "this_week"] | None = None
    rescue_signal_names: list[str] = field(default_factory=list)


def detect_intent(text: str, has_image: bool = False) -> IntentResult:
    lower = text.lower()
    matched: list[str] = []
    categories_hit: list[str] = []

    for category, keywords in RESCUE_SIGNALS.items():
        for kw in keywords:
            if kw in lower:
                matched.append(kw)
                categories_hit.append(category)
                break  # one match per category is enough for scoring

    score = len(categories_hit)
    # having an image alone is a mild signal — food photos often pair with rescue intent
    if has_image:
        score += 1

    no_freezer = "no_storage" in categories_hit or any(
        kw in lower for kw in RESCUE_SIGNALS["no_storage"]
    )

    people_count = 1
    m = _PEOPLE_COUNT_RE.search(text)
    if m:
        people_count = int(m.group(1) or m.group(2))
        people_count = max(1, min(20, people_count))

    time_pressure = None
    for phrase, value in _TIME_PRESSURE_MAP.items():
        if phrase in lower:
            time_pressure = value
            break

    return IntentResult(
        is_food_rescue=score >= 2,
        score=score,
        matched_signals=matched,
        no_freezer=no_freezer,
        people_count=people_count,
        time_pressure=time_pressure,
        rescue_signal_names=categories_hit,
    )
