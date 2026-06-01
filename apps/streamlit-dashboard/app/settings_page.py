"""
settings_page.py — zakładka „Settings": edycja kluczy API.

Pozwala wprowadzić / podmienić:
  * RIOT_API_KEY            — klucz Riot dev (wygasa co 24h),
  * LEAGUEPEDIA_USERNAME    — login bot-passworda (Format: Name@BotName),
  * LEAGUEPEDIA_PASSWORD    — hasło bot-passworda.

Wartości zapisywane są do pliku `.env` w katalogu projektu (przez
`python-dotenv.set_key`), a jednocześnie wstawiane do `os.environ`,
żeby działały od razu — bez restartu Streamlita. `st.cache_resource`
jest czyszczone, więc klienci API (Riot / Leaguepedia) zostaną
zbudowani na nowo z aktualnymi credencjalami przy następnym użyciu.

App jest single-user (lokalna instalacja), więc wartości pokazujemy
jawnym tekstem — nic nie maskujemy. Nie ma sensu chować ich przed
sobą samym.

Punkt wejścia to render() — app/main.py wywołuje ją w miejscu zakładki.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import set_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def render() -> None:
    """Renderuje zakładkę Settings. Wywołać raz w miejscu zakładki."""
    st.title("🔧 Settings")
    st.caption(
        "API keys are saved to .env in the project root. Values take effect "
        "immediately — Streamlit clears the client cache and rebuilds them "
        "with the current keys. Single-user app, so values are shown in plain text."
    )

    if not ENV_PATH.exists():
        st.info(
            f"`.env` does not exist — it will be created on first save:\n\n`{ENV_PATH}`"
        )

    # Komunikat z poprzedniej akcji — przeżywa st.rerun() w session_state.
    msg = st.session_state.pop("settings_msg", None)
    if msg is not None:
        {"ok": st.success, "err": st.error}[msg[0]](msg[1])

    current_riot = os.environ.get("RIOT_API_KEY", "")
    current_user = os.environ.get("LEAGUEPEDIA_USERNAME", "")
    current_pass = os.environ.get("LEAGUEPEDIA_PASSWORD", "")

    # --- Riot API -----------------------------------------------------------
    st.subheader("Riot API")
    st.caption(
        "Dev key expires every 24h — refresh from "
        "developer.riotgames.com and paste below."
    )
    new_riot = st.text_input(
        "Riot key",
        value=current_riot,
        placeholder="RGAPI-...",
        key="settings_riot",
    )

    st.divider()

    # --- Leaguepedia --------------------------------------------------------
    st.subheader("Leaguepedia (bot-password)")
    st.caption(
        "Create a bot-password at **lol.fandom.com/Special:BotPasswords**. "
        "Without it the client runs anonymously (lower API limit)."
    )
    new_user = st.text_input(
        "Leaguepedia username",
        value=current_user,
        placeholder="YourName@BotName",
        help="Format: AccountName@BotName.",
        key="settings_lp_user",
    )
    new_pass = st.text_input(
        "Leaguepedia password",
        value=current_pass,
        placeholder="...",
        key="settings_lp_pass",
    )

    st.divider()

    col_save, col_clear, _ = st.columns([1, 1, 3])
    if col_save.button("💾 Save", type="primary",
                       use_container_width=True):
        _save(new_riot, current_riot, new_user, current_user,
              new_pass, current_pass)
    if col_clear.button("🧹 Clear client cache",
                        use_container_width=True,
                        help="Forces Riot + Leaguepedia clients to be rebuilt "
                             "with the current keys from .env."):
        st.cache_resource.clear()
        try:
            from draft_analyzer.leaguepedia import reset_client
            reset_client()
        except Exception:
            pass
        st.session_state["settings_msg"] = (
            "ok",
            "Client cache cleared — next fetch will use the current keys."
        )
        st.rerun()


def _save(
    new_riot: str, current_riot: str,
    new_user: str, current_user: str,
    new_pass: str, current_pass: str,
) -> None:
    """Zapisuje pola, które faktycznie się zmieniły, do .env i os.environ;
    czyści cache klientów. Brak masek — porównujemy wartości wprost."""
    updates: list[tuple[str, str]] = []
    if new_riot.strip() and new_riot.strip() != current_riot:
        updates.append(("RIOT_API_KEY", new_riot.strip()))
    if new_user.strip() and new_user.strip() != current_user:
        updates.append(("LEAGUEPEDIA_USERNAME", new_user.strip()))
    if new_pass.strip() and new_pass.strip() != current_pass:
        updates.append(("LEAGUEPEDIA_PASSWORD", new_pass.strip()))

    if not updates:
        st.session_state["settings_msg"] = (
            "err",
            "Nothing to save — all fields unchanged."
        )
        st.rerun()
        return

    try:
        ENV_PATH.touch(exist_ok=True)
        for key, value in updates:
            # set_key cytuje wartości, więc spacje / znaki specjalne są OK.
            set_key(str(ENV_PATH), key, value)
            # Wstaw też do bieżącego procesu — działa od razu, bez restartu.
            os.environ[key] = value
    except Exception as e:
        st.session_state["settings_msg"] = ("err", f"Save error: {e}")
        st.rerun()
        return

    # Klienci Riot / Leaguepedia są singletonami w @st.cache_resource —
    # bez wyczyszczenia trzymaliby się starych kluczy aż do restartu
    # Streamlita. Po czyszczeniu zostaną utworzeni na nowo przy
    # pierwszym wywołaniu get_resolver() / get_riot_client() /
    # get_leaguepedia_client() w main.py.
    st.cache_resource.clear()
    # Singleton LeaguepediaClient w draft_analyzer.leaguepedia jest
    # modułowy (nie @st.cache_resource), więc trzeba go zresetować
    # osobno — inaczej dalej siedziałby na starym (anonimowym) trybie.
    try:
        from draft_analyzer.leaguepedia import reset_client
        reset_client()
    except Exception:
        pass

    st.session_state["settings_msg"] = (
        "ok",
        f"Saved: {', '.join(k for k, _ in updates)}. "
        f"API clients refreshed — next fetch will use the new keys."
    )
    st.rerun()
