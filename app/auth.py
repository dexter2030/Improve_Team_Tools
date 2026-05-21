"""
app/auth.py — prosta bramka hasłowa dla deploymentu.

Streamlit Community Cloud nie ma wbudowanego logowania, a chcemy żeby
strona była online ale niedostępna dla obcych. Mechanika jest celowo
najprostsza:

  * Hasło trzymane w APP_PASSWORD (st.secrets lub .env, ładowane przez
    src.config.bootstrap_secrets).
  * require_password() pokazuje formularz; po poprawnym haśle ustawia
    flagę w st.session_state i wywołuje st.stop() dopóki user się nie
    zaloguje.
  * Hasło porównujemy przez hmac.compare_digest żeby nie wyciekać
    informacji timingowych.

Brak zarządzania użytkownikami, brak rotacji sesji, brak rate-limitu —
to MVP dla małej, prywatnej strony. Jeśli kiedyś będzie potrzeba kont
i ról, podmienić na streamlit-authenticator albo Auth0.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st


def require_password() -> None:
    """Blokuje renderowanie reszty strony do momentu poprawnego logowania.

    Jeśli APP_PASSWORD nie jest ustawione w środowisku, strona zostaje
    otwarta — to bezpieczny domyślny tryb dla developmentu lokalnego.
    Na produkcji ustaw APP_PASSWORD w sekretach Streamlit Cloud, żeby
    bramka się włączyła.
    """
    expected = os.environ.get("APP_PASSWORD", "").strip()
    if not expected:
        return

    if st.session_state.get("auth_ok"):
        return

    st.set_page_config(page_title="LoL Scouting Dashboard", layout="centered")
    st.title("🔒 LoL Scouting Dashboard")
    st.caption("Strona prywatna — podaj hasło żeby kontynuować.")

    with st.form("login_form", clear_on_submit=False):
        password = st.text_input("Hasło", type="password")
        submitted = st.form_submit_button("Zaloguj", type="primary")

    if submitted:
        if hmac.compare_digest(password, expected):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Złe hasło.")

    st.stop()
