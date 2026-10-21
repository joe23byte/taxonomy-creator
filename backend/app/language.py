"""Analysis language: detected from the L1/L2 taxonomy, used for every generated label and description."""
from __future__ import annotations

import re
import sqlite3

from . import db

META_KEY = "taxonomy_language"
NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch"}

_STOPWORDS = {
    "en": "the and of to for with or in on is are not a an by from about your their when which customer customers "
          "account billing payment request requests issue issues problem".split(),
    "de": "der die das und oder für mit von zu zur zum im in ist sind nicht ein eine einer kunde kunden fragen "
          "anliegen antrag anträge beim bei auf über rund sowie".split(),
    "fr": "le la les et ou pour avec de du des en est sont pas un une client clients demande demandes sur".split(),
    "es": "el la los las y o para con de del en es son no un una cliente clientes solicitud solicitudes sobre".split(),
    "it": "il lo la gli le e o per con di del della in è sono non un una cliente clienti richiesta richieste".split(),
    "nl": "de het en of voor met van te in is zijn niet een klant klanten vraag vragen aanvraag over".split(),
}
_STOPWORDS = {code: frozenset(words) for code, words in _STOPWORDS.items()}


def detect(texts: list[str]) -> str:
    words = re.findall(r"[a-zäöüßàâçéèêëîïôûùÿñáíóúì]+", " ".join(texts).lower())
    scores = {code: sum(1 for w in words if w in stop) for code, stop in _STOPWORDS.items()}
    scores["de"] += sum(1 for w in words if re.search(r"[äöüß]", w))
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "en"


def detect_categories(categories: list[dict]) -> str:
    return detect([f"{c.get('label', '')}. {c.get('description', '')}" for c in categories])


def get(conn: sqlite3.Connection) -> str:
    stored = db.get_meta(conn, META_KEY)
    if stored in NAMES:
        return stored
    rows = conn.execute("SELECT label, description FROM taxonomy_nodes WHERE level<=2 AND status='active'").fetchall()
    return detect_categories([dict(r) for r in rows]) if rows else "en"


def store(conn: sqlite3.Connection, code: str) -> None:
    if code not in NAMES:
        raise ValueError(f"Unsupported language {code}")
    db.set_meta(conn, META_KEY, code)


def name(code: str) -> str:
    return NAMES.get(code, "English")


def rule(code: str) -> str:
    """Instruction appended to every prompt that produces taxonomy text."""
    if code == "en":
        return "\nLanguage: write every label, description, intent and summary in English. Labels use Title Case."
    lang = name(code)
    return (f"\nLanguage: the taxonomy is in {lang}. Write every label, description, intent, summary and rationale "
            f"in {lang}, never in English, using natural {lang} wording and the normal capitalization rules of "
            f"{lang} (no English Title Case). Keep only established product or brand names unchanged."
            + _EXAMPLES.get(code, ""))


_EXAMPLES = {
    "de": ' Example label: "Krankengeld nicht ausgezahlt", not "Krankengeld Nicht Ausgezahlt".',
    "fr": ' Example label: "Remboursement non reçu", not "Remboursement Non Reçu".',
    "es": ' Example label: "Reembolso no recibido", not "Reembolso No Recibido".',
    "it": ' Example label: "Rimborso non ricevuto", not "Rimborso Non Ricevuto".',
    "nl": ' Example label: "Terugbetaling niet ontvangen", not "Terugbetaling Niet Ontvangen".',
}

# German labels: function words are never capitalised after the first word (nouns stay as written).
_DE_LOWER = frozenset(
    "nicht kein keine keinen von vom aus in im ins für mit zu zur zum bei beim und oder auf über nach an am ohne "
    "wegen trotz der die das den dem des ein eine einer eines einem einen bis seit unter vor durch gegen als wie "
    "nur noch bereits doppelt falsch fehlerhaft".split())


def tidy_label(label: str, code: str) -> str:
    if code != "de":
        return label
    words = label.split()
    return " ".join(w if i == 0 or w.lower() not in _DE_LOWER else w.lower() for i, w in enumerate(words))
