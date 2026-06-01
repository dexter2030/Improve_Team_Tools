"""
src/processing/profiles.py

The scouting-profile schema: the stable, hand-curated entity representing
a player you want to track.

Design principle
----------------
A profile holds ONLY:
  1. Identity keys — the minimum needed to FETCH stats from each source.
     SoloQ accounts are derived from the op.gg links the coach pastes; the
     pro-play block from a pasted Leaguepedia link.
  2. Scouting metadata — your hand-authored coach knowledge (age, country,
     notes, a lolpros reference link).
  3. Resolution state — whether identity keys have been verified against APIs.

It does NOT hold stats. Stats are derived, volatile, and cohort-relative;
they are always fetched fresh and cached, never frozen into a profile.
Freezing stats here would (a) rot your notes against stale numbers and
(b) destroy the ability to recompute Z-scores against a new cohort.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# --- Enumerations ------------------------------------------------------------

class Role(str, Enum):
    """Canonical role labels. Normalize all source data to these."""
    TOP = "Top"
    JUNGLE = "Jungle"
    MID = "Mid"
    BOT = "Bot"
    SUPPORT = "Support"


class ResolutionState(str, Enum):
    """
    Tracks whether a profile's identity keys have been verified.

    UNRESOLVED  — keys entered but not yet checked against APIs.
    RESOLVED    — all provided keys verified; fetching will succeed.
    PARTIAL     — at least one source verified, another failed/missing.
    FAILED      — verification attempted and no source resolved.
    """
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    PARTIAL = "partial"
    FAILED = "failed"


# --- Source-specific identity blocks ----------------------------------------

@dataclass(frozen=True, slots=True)
class SoloQIdentity:
    """
    Keys for fetching one SoloQ account via the Riot API.

    Derived from an op.gg link the coach pastes. `opgg_url` keeps that
    original link (for display / re-opening); `riot_id` ('GameName#TAG')
    and `platform` ('euw1', ...) are parsed out of it and are what the
    Riot API actually needs. `puuid` and `summoner_level` are populated by
    the resolver after a successful Account-V1 / Summoner-V4 lookup.

    A player may have several SoloQ accounts (smurfs, region accounts);
    each is its own SoloQIdentity — see `ScoutingProfile.soloq`.
    """
    riot_id: str
    platform: str                       # e.g. 'euw1' — drives Summoner-V4 routing.
    opgg_url: str | None = None         # Original op.gg link the coach pasted.
    puuid: str | None = None            # Populated on resolution.
    summoner_level: int | None = None   # Populated on resolution.

    @property
    def is_resolved(self) -> bool:
        return self.puuid is not None


@dataclass(frozen=True, slots=True)
class ProPlayIdentity:
    """
    Keys for fetching pro-play data via the Leaguepedia Cargo API.

    The coach pastes a Leaguepedia page URL directly. `leaguepedia_url`
    keeps that original link; `leaguepedia_link` is the canonical wiki page
    name parsed from it — the STABLE cross-table join key (see CLAUDE.md).
    `current_team` and `verified` are populated by the resolver once it
    confirms the page exists.
    """
    leaguepedia_link: str                # Canonical page name — the join key.
    leaguepedia_url: str = ""            # Original wiki URL the coach pasted.
    current_team: str | None = None      # Populated on resolution.
    verified: bool = False               # True once the wiki page is confirmed.

    @property
    def is_resolved(self) -> bool:
        return self.verified


# --- The profile -------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ScoutingProfile:
    """
    A tracked player. Immutable by design — mutations go through the
    `with_*` helpers, which return a new instance. This keeps an audit
    trail trivial and makes the object safe to cache.

    Fields
    ------
    profile_id   : internal UUID. The ONLY key used to join a profile to
                   fetched stats, notes, or comparison cohorts.
    display_name : the name you, the coach, refer to this player by.
    role         : primary role (a player may flex; track the main here).
    soloq        : tuple of SoloQ accounts — one per pasted op.gg link;
                   may be empty if no SoloQ account is tracked.
    proplay      : Pro-play identity block (may be None if not tracked).
    age          : optional; useful for prospect/age-curve filtering.
    nationality  : optional; the player's country / ERL-region eligibility.
    lolpros_url  : optional reference link to the player's lolpros.gg page.
                   A coach bookmark only — lolpros has no API, so it is
                   never fetched or resolved.
    notes        : your scouting notes — the IP that makes this dashboard yours.
    """

    # --- Identity ---
    profile_id: str
    display_name: str
    role: Role

    # --- Source identity blocks (at least one should be present) ---
    soloq: tuple[SoloQIdentity, ...] = field(default_factory=tuple)
    proplay: ProPlayIdentity | None = None

    # --- Hand-authored scouting metadata ---
    age: int | None = None
    nationality: str | None = None
    lolpros_url: str | None = None
    notes: str = ""

    # --- Bookkeeping ---
    resolution_state: ResolutionState = ResolutionState.UNRESOLVED
    created_utc: str = field(default_factory=lambda: _now_iso())
    updated_utc: str = field(default_factory=lambda: _now_iso())

    # -- Construction --------------------------------------------------------

    @classmethod
    def create(
        cls,
        display_name: str,
        role: Role,
        *,
        soloq: tuple[SoloQIdentity, ...] = (),
        proplay: ProPlayIdentity | None = None,
        age: int | None = None,
        nationality: str | None = None,
        lolpros_url: str | None = None,
        notes: str = "",
    ) -> "ScoutingProfile":
        """Create a fresh profile with a generated ID and timestamps."""
        soloq = tuple(soloq)
        if not soloq and proplay is None:
            raise ValueError(
                "A profile needs at least one source identity — an op.gg "
                "account and/or a Leaguepedia link — otherwise nothing can "
                "be fetched."
            )
        if age is not None and not (12 <= age <= 60):
            raise ValueError(f"Implausible age {age}; expected 12-60.")

        return cls(
            profile_id=str(uuid.uuid4()),
            display_name=display_name.strip(),
            role=role,
            soloq=soloq,
            proplay=proplay,
            age=age,
            nationality=nationality,
            lolpros_url=lolpros_url,
            notes=notes,
        )

    # -- Immutable mutators --------------------------------------------------

    def with_notes(self, notes: str) -> "ScoutingProfile":
        """Return a copy with updated notes and a refreshed timestamp."""
        return replace(self, notes=notes, updated_utc=_now_iso())

    def with_soloq_accounts(
        self, accounts: tuple[SoloQIdentity, ...]
    ) -> "ScoutingProfile":
        """Return a copy with the SoloQ account list replaced post-resolution.

        Does NOT recompute `resolution_state` — the resolver recomputes once,
        after every identity block has been updated, via `_recomputed_state`.
        """
        return replace(self, soloq=tuple(accounts), updated_utc=_now_iso())

    def with_proplay(self, proplay: ProPlayIdentity) -> "ScoutingProfile":
        """Return a copy with the pro-play block replaced post-resolution.

        Does NOT recompute `resolution_state` — see `with_soloq_accounts`.
        """
        if self.proplay is None:
            raise ValueError("Profile has no pro-play identity to update.")
        return replace(self, proplay=proplay, updated_utc=_now_iso())

    # -- Derived state -------------------------------------------------------

    def _recomputed_state(self) -> "ScoutingProfile":
        """Return a copy with `resolution_state` recomputed from the blocks.

        Every SoloQ account and the pro-play block each count as one block:
          * verification attempted, nothing resolved -> FAILED
          * every block resolved                     -> RESOLVED
          * some resolved, some not                  -> PARTIAL

        The resolver calls this after every resolution pass — including the
        all-failed path — so a fully-failed profile becomes FAILED rather
        than silently keeping its default UNRESOLVED.
        """
        blocks: list[SoloQIdentity | ProPlayIdentity] = list(self.soloq)
        if self.proplay is not None:
            blocks.append(self.proplay)

        if not blocks:
            return replace(self, resolution_state=ResolutionState.UNRESOLVED)

        resolved = [b for b in blocks if b.is_resolved]
        if not resolved:
            state = ResolutionState.FAILED
        elif len(resolved) == len(blocks):
            state = ResolutionState.RESOLVED
        else:
            state = ResolutionState.PARTIAL

        return replace(self, resolution_state=state)

    # -- Serialization (for the SQLite profile store) ------------------------

    def to_dict(self) -> dict[str, Any]:
        """Flatten to a JSON-serializable dict for persistence."""
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "role": self.role.value,
            "soloq": [_block_to_dict(s) for s in self.soloq],
            "proplay": _block_to_dict(self.proplay),
            "age": self.age,
            "nationality": self.nationality,
            "lolpros_url": self.lolpros_url,
            "notes": self.notes,
            "resolution_state": self.resolution_state.value,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoutingProfile":
        """Rehydrate a profile from its persisted dict form."""
        return cls(
            profile_id=data["profile_id"],
            display_name=data["display_name"],
            role=Role(data["role"]),
            soloq=_soloq_from_data(data.get("soloq")),
            proplay=_proplay_from_data(data.get("proplay")),
            age=data.get("age"),
            nationality=data.get("nationality"),
            lolpros_url=data.get("lolpros_url"),
            notes=data.get("notes", ""),
            resolution_state=ResolutionState(
                data.get("resolution_state", "unresolved")
            ),
            created_utc=data["created_utc"],
            updated_utc=data["updated_utc"],
        )


# --- Helpers -----------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _block_to_dict(block: Any) -> dict[str, Any] | None:
    """Flatten a frozen identity block to a dict, or None."""
    if block is None:
        return None
    return {f: getattr(block, f) for f in block.__slots__}


def _soloq_from_data(raw: Any) -> tuple[SoloQIdentity, ...]:
    """Rehydrate the SoloQ account tuple from persisted data.

    Tolerates the pre-multi-account format, where `soloq` was a single
    dict (or null) rather than a list.
    """
    if not raw:
        return ()
    if isinstance(raw, dict):           # legacy single-block format
        raw = [raw]
    return tuple(
        SoloQIdentity(
            riot_id=d["riot_id"],
            platform=d["platform"],
            opgg_url=d.get("opgg_url"),
            puuid=d.get("puuid"),
            summoner_level=d.get("summoner_level"),
        )
        for d in raw
    )


def _proplay_from_data(d: Any) -> ProPlayIdentity | None:
    """Rehydrate the pro-play block, or None."""
    if not d:
        return None
    link = d.get("leaguepedia_link")
    if not link:
        # A legacy un-resolved pro-play block carried only an in-game name;
        # without a canonical link there is nothing to rehydrate.
        return None
    return ProPlayIdentity(
        leaguepedia_link=link,
        leaguepedia_url=d.get("leaguepedia_url", ""),
        current_team=d.get("current_team"),
        verified=bool(d.get("verified", False)),
    )
