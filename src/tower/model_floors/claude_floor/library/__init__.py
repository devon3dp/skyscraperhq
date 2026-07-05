"""Claude floor library — refusals, snippets, aphorisms.

DB-backed (not JSONL). The library is structured for lookup/similarity rather
than append-only chronology.
"""
from .refusals import RefusalLibrary
from .snippets import SnippetLibrary
from .aphorisms import AphorismLibrary

__all__ = ["RefusalLibrary", "SnippetLibrary", "AphorismLibrary"]
