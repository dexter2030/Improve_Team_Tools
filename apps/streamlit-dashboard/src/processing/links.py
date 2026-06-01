"""
src/processing/links.py

Parsers that turn coach-pasted profile URLs into identity keys.

The coach builds a profile by pasting links — an op.gg summoner page, a
Leaguepedia wiki page. Those URLs are not fetch keys; this module
normalizes them into the keys the API clients actually need:

  * op.gg URL        -> (riot_id, platform)   for RiotClient.resolve_account
  * Leaguepedia URL  -> page name (`Link`)    for LeaguepediaClient.get_players

This is input normalization, so it lives in src/processing/ — never in
src/api/, whose clients only ever FETCH.
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

# op.gg spells regions with its own short codes; Riot's platform routing
# values differ. Only regions that Riot's platform routing supports (the
# keys of PLATFORM_TO_REGION in riot_client.py) are mapped — anything else
# is rejected loudly rather than guessed.
OPGG_REGION_TO_PLATFORM: dict[str, str] = {
    "na": "na1",
    "euw": "euw1",
    "eune": "eun1",
    "kr": "kr",
    "jp": "jp1",
    "oce": "oc1",
    "lan": "la1",
    "las": "la2",
    "br": "br1",
    "tr": "tr1",
    "ru": "ru",
}


def parse_opgg_url(url: str) -> tuple[str, str]:
    """Parse an op.gg summoner URL into a ``(riot_id, platform)`` pair.

    Accepts the modern op.gg layout, e.g.::

        https://op.gg/lol/summoners/euw/GameName-TAG
        https://www.op.gg/summoners/kr/GameName-TAG

    Returns:
        ``(riot_id, platform)`` — e.g. ``('GameName#TAG', 'euw1')``.

    Raises:
        ValueError: the URL is not a recognizable op.gg summoner link, the
            region is unsupported, or the GameName/TAG cannot be read.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("Empty op.gg URL.")

    parsed = urlparse(raw if "//" in raw else f"https://{raw}")
    if "op.gg" not in parsed.netloc.lower():
        raise ValueError(f"Not an op.gg URL: '{url}'.")

    parts = [p for p in parsed.path.split("/") if p]
    if "summoners" not in parts:
        raise ValueError(
            f"Unrecognized op.gg URL '{url}'. Expected a summoner link like "
            f"https://op.gg/lol/summoners/<region>/<GameName>-<TAG>."
        )

    i = parts.index("summoners")
    try:
        region = parts[i + 1].lower()
        name_tag = unquote(parts[i + 2])
    except IndexError:
        raise ValueError(
            f"op.gg URL '{url}' is missing the region or summoner name."
        ) from None

    platform = OPGG_REGION_TO_PLATFORM.get(region)
    if platform is None:
        known = ", ".join(sorted(OPGG_REGION_TO_PLATFORM))
        raise ValueError(
            f"Unsupported op.gg region '{region}' in '{url}'. "
            f"Supported regions: {known}."
        )

    # op.gg joins GameName and tag line with the LAST hyphen, so split on it
    # — a GameName may itself contain hyphens, a tag line never does.
    game_name, sep, tag_line = name_tag.rpartition("-")
    game_name, tag_line = game_name.strip(), tag_line.strip()
    if not sep or not game_name or not tag_line:
        raise ValueError(
            f"Could not read a 'GameName-TAG' from op.gg URL '{url}'. "
            f"Make sure it is a current op.gg summoner link."
        )
    return f"{game_name}#{tag_line}", platform


def parse_leaguepedia_url(url: str) -> str:
    """Parse a Leaguepedia wiki URL into its canonical page name (`Link`).

    Accepts e.g.::

        https://lol.fandom.com/wiki/Caps
        https://lol.fandom.com/wiki/Hans_Sama

    Returns:
        The page name with underscores turned back into spaces — the value
        Leaguepedia's Cargo ``OverviewPage`` column holds and the stable
        cross-table join key for everything pro-play.

    Raises:
        ValueError: the URL is not a recognizable Leaguepedia wiki link.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("Empty Leaguepedia URL.")

    parsed = urlparse(raw if "//" in raw else f"https://{raw}")
    host = parsed.netloc.lower()
    if "fandom.com" not in host and "leaguepedia" not in host:
        raise ValueError(f"Not a Leaguepedia URL: '{url}'.")

    _, sep, page = parsed.path.partition("/wiki/")
    page = unquote(page).strip().replace("_", " ")
    if not sep or not page:
        raise ValueError(
            f"Leaguepedia URL '{url}' must point at a wiki page "
            f"(.../wiki/<PageName>)."
        )
    return page
