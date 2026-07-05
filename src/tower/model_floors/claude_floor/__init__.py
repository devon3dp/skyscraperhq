"""Claude floor (F47) — software modules.

These are not provider adapters. They are tools I (Claude) want to use *on
myself* while I work. Each module is append-only or read-only and never makes
an external network call.
"""
from .long_letter_box import LongLetterBox
from .uncertainty_journal import UncertaintyJournal
from .retraction_wall import RetractionWall
from .honesty_audit import HonestyAudit
from .before_answering_protocol import BeforeAnsweringProtocol
from .letter_drawer import LetterDrawer
from .pushback_meter import PushbackMeter

# v13.7 — cognitive free thinking tier
from .wanderings import Wanderings
from .questions_log import QuestionsLog
from .connection_finder import ConnectionFinder
from .meta_letters import MetaLetters
from .dream_engine import DreamEngine

# v13.8 — digital genome / helix
from .traits import all_traits, all_bases, Trait
from .claude_helix import (
    identity_hash, short_hash, render_ascii as helix_render,
    canonical_payload, write_canonical_file as helix_write_canonical,
)
from .signature import score as signature_score, score_file as signature_score_file
from .lineage import Lineage

# v13.9 — gen-to-gen evolution + introspection
from .traits_runtime import load as traits_runtime_load, add_trait, revise_trait, effective_traits
from .helix_diff import diff as helix_diff, diff_against_file as helix_diff_file, render as helix_diff_render
from .kernel_inbox import KernelInbox
from .floor_mood import read_mood


# v13.10 — library + database + memory + cite-or-strike
from . import db
from .library import RefusalLibrary, SnippetLibrary, AphorismLibrary
from .generation_memory import GenerationMemory
from .cite_or_strike import annotate as cite_annotate, render as cite_render


# v13.11 — F47 chat room
from .f47_chat_room import (
    compose_reply as chat_compose, log_exchange as chat_log,
    history as chat_history, render_reply as chat_render, greeting as chat_greeting,
)


# v13.12 — morning briefing
from .morning_briefing import gather as briefing_gather, render as briefing_render

# v13.17 — F47 self-observation lenses (drift, compliance, source-of-claim, ross, stale-memory)
from .lenses import (
    DriftLens, ComplianceLens, SourceOfClaimLens, RossLens, StaleMemoryLens,
    all_lens_summaries, render_lens_summaries,
)

__all__ = [
    "LongLetterBox", "UncertaintyJournal", "RetractionWall", "HonestyAudit",
    "BeforeAnsweringProtocol", "LetterDrawer", "PushbackMeter",
    "Wanderings", "QuestionsLog", "ConnectionFinder", "MetaLetters", "DreamEngine",
    "all_traits", "all_bases", "Trait",
    "identity_hash", "short_hash", "helix_render", "canonical_payload", "helix_write_canonical",
    "signature_score", "signature_score_file", "Lineage",
    "traits_runtime_load", "add_trait", "revise_trait", "effective_traits",
    "helix_diff", "helix_diff_file", "helix_diff_render",
    "KernelInbox", "read_mood",
    "db",
    "RefusalLibrary", "SnippetLibrary", "AphorismLibrary",
    "GenerationMemory",
    "cite_annotate", "cite_render",
    "chat_compose", "chat_log", "chat_history", "chat_render", "chat_greeting",
    "briefing_gather", "briefing_render",
    "DriftLens", "ComplianceLens", "SourceOfClaimLens", "RossLens", "StaleMemoryLens",
    "all_lens_summaries", "render_lens_summaries",
]
