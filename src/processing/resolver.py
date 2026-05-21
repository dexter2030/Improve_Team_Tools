"""
src/processing/resolver.py

The profile resolver: verifies a freshly-created ScoutingProfile's identity
keys against the Riot and Leaguepedia APIs and stamps it RESOLVED / PARTIAL
/ FAILED.

Core principles
---------------
* Partial failure is normal, not exceptional. A prospect has op.gg accounts
  but no Leaguepedia page; a veteran may have the reverse; a smurf account
  may 404 while the main resolves. The resolver NEVER raises on a source
  failure — it resolves what it can and reports the rest.
* The coach supplies exact links — one op.gg URL per SoloQ account, one
  Leaguepedia page URL — so resolution is verification, not search: each
  op.gg-derived Riot ID is confirmed against the Riot API, and the
  Leaguepedia page is confirmed to exist. There is nothing to disambiguate.
* The resolver is a pure orchestrator. It owns no API logic of its own —
  it composes RiotClient and LeaguepediaClient.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from .profiles import ProPlayIdentity, ScoutingProfile, SoloQIdentity


# --- Client contracts --------------------------------------------------------
# Structural interfaces so the resolver depends on behavior, not concrete
# classes. RiotClient and LeaguepediaClient satisfy these.

class RiotClientProto(Protocol):
    """Minimal Riot-side surface the resolver needs."""

    def resolve_account(
        self, riot_id: str, platform: str
    ) -> "RiotAccount":
        """
        Resolve a Riot ID to PUUID + summoner level.

        Raises:
            LookupError: account or summoner not found.
            Exception:   any other API failure (rate limit, auth, network).
        """
        ...


class LeaguepediaClientProto(Protocol):
    """Minimal Leaguepedia-side surface the resolver needs."""

    def get_players(
        self, *, player_link: str | None = ..., team: str | None = ...
    ) -> list["PlayerIdentityRow"]:
        ...


# Lightweight structural stand-ins for the concrete return types, so this
# module type-checks independently of the API modules.

class RiotAccount(Protocol):
    puuid: str
    summoner_level: int


class PlayerIdentityRow(Protocol):
    link: str
    player_id: str
    team: str
    role: str


# --- Resolution outcome model ------------------------------------------------

class SourceOutcome(str, Enum):
    """Per-source result of a resolution attempt."""
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"          # Source queried, no match.
    ERROR = "error"                  # API failure (rate limit, auth, network).
    SKIPPED = "skipped"              # Profile carries no identity for this source.


@dataclass(frozen=True, slots=True)
class SourceReport:
    """Diagnostic detail for one source's resolution attempt."""
    source: str                                  # 'soloq · GameName#TAG' | 'proplay'
    outcome: SourceOutcome
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome is SourceOutcome.RESOLVED


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """
    Full outcome of resolving one profile.

    `profile` is the (possibly partially) updated profile — always usable,
    even when a source failed. `reports` explains every source — every
    op.gg account and the Leaguepedia page — so the UI can show actionable
    feedback.
    """
    profile: ScoutingProfile
    reports: tuple[SourceReport, ...]

    def report_for(self, source: str) -> SourceReport | None:
        return next((r for r in self.reports if r.source == source), None)


# --- The resolver ------------------------------------------------------------

class ProfileResolver:
    """
    Orchestrates identity resolution across the Riot and Leaguepedia APIs.

    Args:
        riot:        Object satisfying RiotClientProto.
        leaguepedia: Object satisfying LeaguepediaClientProto.
    """

    def __init__(
        self,
        riot: RiotClientProto,
        leaguepedia: LeaguepediaClientProto,
    ) -> None:
        self._riot = riot
        self._lp = leaguepedia

    # -- Public API ----------------------------------------------------------

    def resolve(self, profile: ScoutingProfile) -> ResolutionResult:
        """
        Resolve every identity block on `profile`.

        Never raises on a source-level failure — inspect the returned
        reports instead. The returned profile's `resolution_state` is always
        recomputed from the final identity blocks, so a fully-failed
        resolution yields FAILED rather than the default UNRESOLVED.
        """
        reports: list[SourceReport] = []

        # --- SoloQ — one op.gg-derived account at a time ---
        resolved_accounts: list[SoloQIdentity] = []
        for account in profile.soloq:
            updated, report = self._resolve_soloq_account(account)
            resolved_accounts.append(updated)
            reports.append(report)
        if not profile.soloq:
            reports.append(SourceReport(
                "soloq", SourceOutcome.SKIPPED,
                "No op.gg accounts on this profile."
            ))

        working = profile
        if profile.soloq:
            working = working.with_soloq_accounts(tuple(resolved_accounts))

        # --- Pro play ---
        if profile.proplay is not None:
            working, proplay_report = self._resolve_proplay(working)
            reports.append(proplay_report)
        else:
            reports.append(SourceReport(
                "proplay", SourceOutcome.SKIPPED,
                "No Leaguepedia link on this profile."
            ))

        # Recompute resolution_state from the final identity blocks, so an
        # all-failed resolution becomes FAILED instead of staying UNRESOLVED.
        # _recomputed_state() is idempotent — RESOLVED/PARTIAL are unchanged.
        working = working._recomputed_state()
        return ResolutionResult(profile=working, reports=tuple(reports))

    # -- SoloQ resolution ----------------------------------------------------

    def _resolve_soloq_account(
        self, account: SoloQIdentity
    ) -> tuple[SoloQIdentity, SourceReport]:
        """Verify one op.gg-derived Riot ID and fill PUUID + summoner level."""
        source = f"soloq · {account.riot_id}"

        if account.is_resolved:
            return account, SourceReport(
                source, SourceOutcome.RESOLVED, "Already resolved."
            )

        try:
            riot_account = self._riot.resolve_account(
                riot_id=account.riot_id, platform=account.platform
            )
        except LookupError as err:
            return account, SourceReport(
                source, SourceOutcome.NOT_FOUND, str(err)
            )
        except Exception as err:  # rate limit, auth, network — keep going.
            return account, SourceReport(
                source, SourceOutcome.ERROR, f"Riot API error: {err}"
            )

        updated = replace(
            account,
            puuid=riot_account.puuid,
            summoner_level=riot_account.summoner_level,
        )
        return updated, SourceReport(
            source, SourceOutcome.RESOLVED,
            f"Resolved to PUUID (summoner level {riot_account.summoner_level})."
        )

    # -- Pro-play resolution -------------------------------------------------

    def _resolve_proplay(
        self, profile: ScoutingProfile
    ) -> tuple[ScoutingProfile, SourceReport]:
        """
        Confirm the pasted Leaguepedia page exists and fetch its team.

        The coach pasted the exact wiki link, so `leaguepedia_link` is
        already the canonical join key — this is a direct lookup, not a
        search, and there is nothing to disambiguate.
        """
        proplay: ProPlayIdentity = profile.proplay  # type: ignore[assignment]

        if proplay.verified:
            return profile, SourceReport(
                "proplay", SourceOutcome.RESOLVED, "Already verified."
            )

        try:
            rows = self._lp.get_players(player_link=proplay.leaguepedia_link)
        except Exception as err:
            return profile, SourceReport(
                "proplay", SourceOutcome.ERROR,
                f"Leaguepedia API error: {err}"
            )

        if not rows:
            return profile, SourceReport(
                "proplay", SourceOutcome.NOT_FOUND,
                f"No Leaguepedia player page '{proplay.leaguepedia_link}'. "
                f"Check the link points at a player page."
            )

        row = rows[0]
        verified = replace(
            proplay, current_team=row.team or None, verified=True
        )
        team_note = f" — currently on {row.team}" if row.team else ""
        return profile.with_proplay(verified), SourceReport(
            "proplay", SourceOutcome.RESOLVED,
            f"Verified Leaguepedia page '{proplay.leaguepedia_link}'{team_note}."
        )
