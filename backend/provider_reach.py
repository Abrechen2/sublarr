"""Provider reach — did any provider actually answer during one wanted-item run?

``record_search_outcome(kind="no_result")`` charges an item's search budget.
That is only fair when a provider was asked and had nothing. Prod 2026-09-25:
90 % of slow-mode items got there on searches in which every provider was
skipped before being asked (``rate_limited``, ``budget_exhausted``,
``auto_disabled``), so the budget burned on silence.

The tracker lives in a ``ContextVar`` like the decision log and is fed by the
same instrumentation helpers in ``decision_log`` — but it is started by
``process_wanted_item`` unconditionally, so outcome booking never depends on
the ``decision_log_enabled`` diagnostics setting. All recording happens on the
coordinating thread (see ``decision_log``'s module docstring).
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass, field

#: Skip/failure reasons that say "not now", not "never". A search where every
#: provider fell into one of these was never answered.
TRANSIENT_REASONS = frozenset(
    {
        "rate_limited",
        "budget_exhausted",
        "pool_cooling",
        "auto_disabled",
        "circuit_open",
        "timeout",
        "error",
    }
)


@dataclass
class _Reach:
    answered: int = 0
    unavailable: list[str] = field(default_factory=list)


_current: ContextVar[_Reach | None] = ContextVar("sublarr_provider_reach", default=None)


def start() -> Token:
    """Begin tracking for the current run; pass the token to :func:`finish`."""
    return _current.set(_Reach())


def finish(token: Token) -> None:
    _current.reset(token)


def note_answered() -> None:
    """A provider returned a response (hits or not), or the result cache did."""
    reach = _current.get()
    if reach is not None:
        reach.answered += 1


def note_unavailable(name: str, reason: str) -> None:
    """A provider was skipped or failed. Only transient reasons are kept."""
    reach = _current.get()
    if reach is not None and reason in TRANSIENT_REASONS:
        reach.unavailable.append(f"{name} {reason}")


def unanswered_summary() -> str | None:
    """Describe why nobody answered, or None when the miss is genuine.

    None when tracking is inactive, when any provider answered, or when every
    skip was permanent (language not served, excluded, not applicable) — those
    will never be answered and must keep escalating toward ``unsourceable``.
    """
    reach = _current.get()
    if reach is None or reach.answered or not reach.unavailable:
        return None
    return "No provider answered: " + ", ".join(dict.fromkeys(reach.unavailable))
