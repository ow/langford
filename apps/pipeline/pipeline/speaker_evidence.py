"""Speaker keys and acoustic timing evidence shared by ingestion and recovery."""
import re
import math


def label_key(label):
    match = re.fullmatch(r'(?:speaker)[_ ]0*(\d+)', label or '', re.I)
    return f'SPEAKER_{int(match[1]):02d}' if match else None


def has_temporal_support(segment):
    """A timing gate, not a probability that the named identity is correct."""
    coverage = segment.get('speaker_confidence', 0)
    competing = segment.get('competing_speaker_fraction', 0)
    return all(isinstance(value, (int, float)) and not isinstance(value, bool)
               and math.isfinite(value) and 0 <= value <= 1
               for value in (coverage, competing)) and coverage >= .90 and competing <= .10
