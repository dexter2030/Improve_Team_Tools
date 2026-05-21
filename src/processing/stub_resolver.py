"""
src/processing/stub_resolver.py

A STAND-IN resolver for testing the app without hitting any API.

It mimics ProfileResolver.resolve() exactly — same ResolutionResult
shape — but fabricates deterministic mock data instead of calling the
Riot or Leaguepedia APIs. Swap `StubResolver` for the real
`ProfileResolver` for offline use; the app code does not change.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from .profiles import ScoutingProfile, SoloQIdentity
from .resolver import ResolutionResult, SourceOutcome, SourceReport


def _fake_puuid(seed: str) -> str:
    """Deterministic fake PUUID so re-resolving a profile is stable."""
    return hashlib.sha256(seed.encode()).hexdigest()[:78]


def _fake_level(seed: str) -> int:
    """Deterministic fake summoner level in a plausible range."""
    return 30 + (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 600)


class StubResolver:
    """Drop-in replacement for ProfileResolver — no network, mock data."""

    def resolve(self, profile: ScoutingProfile) -> ResolutionResult:
        reports: list[SourceReport] = []

        # --- SoloQ: fabricate a PUUID + level for each op.gg account ---
        resolved_accounts: list[SoloQIdentity] = []
        for account in profile.soloq:
            level = _fake_level(account.riot_id)
            resolved_accounts.append(replace(
                account,
                puuid=_fake_puuid(account.riot_id),
                summoner_level=level,
            ))
            reports.append(SourceReport(
                f"soloq · {account.riot_id}", SourceOutcome.RESOLVED,
                f"[STUB] Fabricated PUUID (summoner level {level})."
            ))
        if not profile.soloq:
            reports.append(SourceReport(
                "soloq", SourceOutcome.SKIPPED, "No op.gg accounts."
            ))

        working = profile
        if profile.soloq:
            working = working.with_soloq_accounts(tuple(resolved_accounts))

        # --- Pro play: pretend the Leaguepedia page exists ---
        if profile.proplay is not None:
            verified = replace(
                profile.proplay, current_team="Stub Esports", verified=True
            )
            working = working.with_proplay(verified)
            reports.append(SourceReport(
                "proplay", SourceOutcome.RESOLVED,
                f"[STUB] Verified fake page "
                f"'{profile.proplay.leaguepedia_link}'."
            ))
        else:
            reports.append(SourceReport(
                "proplay", SourceOutcome.SKIPPED, "No Leaguepedia link."
            ))

        working = working._recomputed_state()
        return ResolutionResult(profile=working, reports=tuple(reports))
