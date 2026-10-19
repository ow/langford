"""Canonical acoustic speaker keys shared by ingestion and recovery."""
import re


def label_key(label):
    match = re.fullmatch(r'(?:speaker)[_ ]0*(\d+)', label or '', re.I)
    return f'SPEAKER_{int(match[1]):02d}' if match else None
