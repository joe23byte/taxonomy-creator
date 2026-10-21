"""Generate a reproducible synthetic GKV (German statutory health insurance) dataset (100 conversations, German).

Outputs (backend/data/examples/gkv/):
- gkv_taxonomy_l1_l2.json  L1/L2 base structure for "Import → L1/L2 taxonomy"
- gkv_transcripts.json     canonical import format (no labels)
- gkv_transcripts.csv      same data, one row per conversation with a transcript column ("Kunde:" / "Mitarbeiter:")
- gkv_ground_truth.json    intended intent per conversation, for your own comparison only (do not import)

Run:  python scripts/generate_gkv_sample.py
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261021
N_CONVERSATIONS = 100
OUT = Path(__file__).resolve().parent.parent / "data" / "examples" / "gkv"

TAXONOMY = {
    "name": "GKV Kundenservice – Basisstruktur",
    "version": 1,
    "categories": [
        {"id": "L1-MIT", "level": 1, "parent_id": None, "label": "Mitgliedschaft & Versicherung",
         "description": "Fragen rund um Versicherungsverhältnis, Familienversicherung, Stammdaten und Gesundheitskarte."},
        {"id": "L2-MIT-FAM", "level": 2, "parent_id": "L1-MIT", "label": "Familienversicherung",
         "description": "Beitragsfreie Mitversicherung von Kindern oder Ehepartnern: Anmeldung, Voraussetzungen, Einkommensgrenzen, Ende."},
        {"id": "L2-MIT-BEG", "level": 2, "parent_id": "L1-MIT", "label": "Beginn & Ende der Mitgliedschaft",
         "description": "Mitgliedsbescheinigungen, Kassenwechsel, Kündigung, Beginn oder Ende der Versicherung."},
        {"id": "L2-MIT-DAT", "level": 2, "parent_id": "L1-MIT", "label": "Stammdaten & Gesundheitskarte",
         "description": "Adresse, Name oder Bankverbindung ändern, elektronische Gesundheitskarte (eGK) beantragen, ersetzen oder Foto hochladen."},
        {"id": "L1-BEI", "level": 1, "parent_id": None, "label": "Beiträge & Finanzen",
         "description": "Beitragshöhe, Beitragszahlungen und finanzielle Vorteile wie Bonusprogramme."},
        {"id": "L2-BEI-HOE", "level": 2, "parent_id": "L1-BEI", "label": "Beitragshöhe & Einstufung",
         "description": "Wie der Beitrag berechnet wird: Einstufung freiwillig Versicherter und Selbständiger, Einkommensnachweise, Zusatzbeitrag."},
        {"id": "L2-BEI-ZAH", "level": 2, "parent_id": "L1-BEI", "label": "Beitragszahlung & Rückstände",
         "description": "Zahlung der Beiträge: Lastschrift, Überweisung, Mahnungen, Rückstände, Stundung und Ratenzahlung."},
        {"id": "L2-BEI-BON", "level": 2, "parent_id": "L1-BEI", "label": "Bonusprogramm & Wahltarife",
         "description": "Bonuspunkte sammeln und einlösen, Prämien, Wahltarife und deren Auszahlung."},
        {"id": "L1-LEI", "level": 1, "parent_id": None, "label": "Leistungen & Anträge",
         "description": "Anträge auf und Fragen zu Leistungen der Krankenkasse."},
        {"id": "L2-LEI-KRG", "level": 2, "parent_id": "L1-LEI", "label": "Krankengeld",
         "description": "Krankengeld und Kinderkrankengeld: Anspruch, Arbeitsunfähigkeitsbescheinigung, Berechnung, Auszahlung."},
        {"id": "L2-LEI-HHM", "level": 2, "parent_id": "L1-LEI", "label": "Hilfs- & Heilmittel",
         "description": "Genehmigung und Kostenübernahme für Hilfsmittel (z. B. Rollator, Hörgerät) und Heilmittel (z. B. Physiotherapie)."},
        {"id": "L2-LEI-ZAN", "level": 2, "parent_id": "L1-LEI", "label": "Zahnersatz & Zahnbehandlung",
         "description": "Heil- und Kostenplan, Festzuschuss, Bonusheft und Kosten für Zahnbehandlungen."},
        {"id": "L2-LEI-ERS", "level": 2, "parent_id": "L1-LEI", "label": "Kostenerstattung & Zuzahlungen",
         "description": "Eingereichte Rechnungen erstatten lassen, Zuzahlungen und Befreiung von Zuzahlungen."},
        {"id": "L2-LEI-REH", "level": 2, "parent_id": "L1-LEI", "label": "Vorsorge & Reha",
         "description": "Anträge auf Rehabilitation, Kuren und Vorsorgemaßnahmen."},
        {"id": "L1-SER", "level": 1, "parent_id": None, "label": "Service & Digitales",
         "description": "Digitale Angebote, Bearbeitungsstände, Beschwerden und Unterstützung bei der Arztsuche."},
        {"id": "L2-SER-APP", "level": 2, "parent_id": "L1-SER", "label": "App & Online-Geschäftsstelle",
         "description": "Registrierung, Login und Funktionen der App oder Online-Geschäftsstelle, elektronische Patientenakte (ePA)."},
        {"id": "L2-SER-BES", "level": 2, "parent_id": "L1-SER", "label": "Widerspruch & Beschwerde",
         "description": "Kunde ist mit einer Entscheidung oder dem Service nicht einverstanden: Widerspruch gegen Bescheide, Beschwerden."},
        {"id": "L2-SER-ARZ", "level": 2, "parent_id": "L1-SER", "label": "Arzt- & Terminsuche",
         "description": "Unterstützung bei der Suche nach Ärzten, Fachärzten oder Terminen, Terminservice."},
    ],
}

# key: (label, l1, l2, occurrences, segment constraint)
INTENTS = {
    "krankengeld_auszahlung": ("Krankengeld-Auszahlung verzögert", "L1-LEI", "L2-LEI-KRG", 11, "pflichtversichert"),
    "egk_ersatz": ("Ersatz für verlorene Gesundheitskarte", "L1-MIT", "L2-MIT-DAT", 10, None),
    "kind_familienversichern": ("Kind familienversichern", "L1-MIT", "L2-MIT-FAM", 10, None),
    "mitgliedsbescheinigung": ("Mitgliedsbescheinigung für Arbeitgeber", "L1-MIT", "L2-MIT-BEG", 9, "pflichtversichert"),
    "kostenerstattung_status": ("Status Kostenerstattung", "L1-LEI", "L2-LEI-ERS", 7, None),
    "zuzahlungsbefreiung": ("Zuzahlungsbefreiung beantragen", "L1-LEI", "L2-LEI-ERS", 7, None),
    "app_login": ("Login in die App funktioniert nicht", "L1-SER", "L2-SER-APP", 7, None),
    "physio_genehmigung": ("Genehmigung Physiotherapie", "L1-LEI", "L2-LEI-HHM", 6, None),
    "zahnersatz_hkp": ("Zuschuss Zahnersatz / Heil- und Kostenplan", "L1-LEI", "L2-LEI-ZAN", 6, None),
    "bonus_einloesen": ("Bonuspunkte einlösen", "L1-BEI", "L2-BEI-BON", 6, None),
    "beitrag_selbststaendig": ("Beitragseinstufung Selbständige", "L1-BEI", "L2-BEI-HOE", 5, "freiwillig"),
    "zusatzbeitrag": ("Frage zur Erhöhung des Zusatzbeitrags", "L1-BEI", "L2-BEI-HOE", 4, None),
    "beitragsrueckstand": ("Mahnung wegen Beitragsrückstand", "L1-BEI", "L2-BEI-ZAH", 4, "freiwillig"),
    "kassenwechsel": ("Kündigung / Kassenwechsel", "L1-MIT", "L2-MIT-BEG", 4, None),
    "kinderkrankengeld": ("Kinderkrankengeld beantragen", "L1-LEI", "L2-LEI-KRG", 4, "pflichtversichert"),
    "hilfsmittel_rollator": ("Kostenübernahme Rollator", "L1-LEI", "L2-LEI-HHM", 3, None),
    "adresse_aendern": ("Adressänderung", "L1-MIT", "L2-MIT-DAT", 3, None),
    "reha_antrag": ("Reha-Antrag stellen", "L1-LEI", "L2-LEI-REH", 2, None),
    "widerspruch": ("Widerspruch gegen Ablehnung", "L1-SER", "L2-SER-BES", 2, None),
    "facharzttermin": ("Hilfe bei Facharzttermin", "L1-SER", "L2-SER-ARZ", 2, None),
    "reiseimpfung": ("Erstattung Reiseimpfung", "L1-LEI", "L2-LEI-ERS", 1, None),
    "epa_einrichten": ("Elektronische Patientenakte einrichten", "L1-SER", "L2-SER-APP", 1, None),
}

T: dict[str, dict[str, list[str]]] = {
    "krankengeld_auszahlung": {
        "opener": [
            "Hallo, ich bin seit sechs Wochen krankgeschrieben und habe noch kein Krankengeld bekommen.",
            "Ich warte seit über zwei Wochen auf mein Krankengeld, wann wird das endlich überwiesen?",
            "Mein Arbeitgeber zahlt seit dem {datum} nicht mehr, und von Ihnen kam bisher nichts.",
            "Guten Tag, das Krankengeld für den letzten Zeitraum fehlt auf meinem Konto.",
            "Ich habe die Folgebescheinigung längst geschickt, aber die Zahlung ist nicht da.",
        ],
        "detail": ["Die Arbeitsunfähigkeitsbescheinigung hat mein Arzt direkt elektronisch übermittelt.",
                   "Die Entgeltbescheinigung hat mein Arbeitgeber laut Personalabteilung schon geschickt.",
                   "Ich bin seit dem {datum} durchgehend arbeitsunfähig."],
        "agent_q": ["Das tut mir leid. Darf ich kurz Ihre Versichertennummer aufnehmen?",
                    "Ich schaue gleich nach. Seit wann sind Sie arbeitsunfähig?"],
        "resolve": ["Die Entgeltbescheinigung lag erst gestern vor. Ich habe die Zahlung angewiesen, das Geld ist in zwei bis drei Werktagen auf Ihrem Konto.",
                    "Es fehlte die Folgebescheinigung für eine Woche. Die liegt jetzt vor, die Auszahlung von {betrag} ist veranlasst."],
        "also": ["Und dann noch etwas: Mein Krankengeld für diesen Monat ist auch noch nicht da.",
                 "Außerdem warte ich noch auf die Krankengeldzahlung, können Sie da auch mal schauen?"],
        "vague": ["Ich bin ja schon länger krank und irgendwie kommt kein Geld, ich weiß gar nicht, wer da jetzt zuständig ist."],
    },
    "egk_ersatz": {
        "opener": [
            "Ich habe meine Gesundheitskarte verloren und brauche eine neue.",
            "Hallo, mir wurde das Portemonnaie gestohlen, die Versichertenkarte war mit drin.",
            "Meine Karte ist gebrochen, der Arzt kann sie nicht mehr einlesen. Wie komme ich an eine neue?",
            "Guten Tag, meine elektronische Gesundheitskarte ist weg, ich habe nächste Woche einen Arzttermin.",
        ],
        "detail": ["Ich habe nächste Woche einen Termin beim Hausarzt.",
                   "Die Karte war erst ein Jahr alt.",
                   "Brauche ich dafür ein neues Foto?"],
        "agent_q": ["Kein Problem. Ich sperre die alte Karte. Ist Ihre Adresse noch aktuell?",
                    "Das bekommen wir hin. Sollen wir das vorhandene Foto weiterverwenden?"],
        "resolve": ["Die alte Karte ist gesperrt, die neue kommt in etwa zehn Tagen. Für den Arzttermin schicke ich Ihnen eine Ersatzbescheinigung.",
                    "Ich habe die Ersatzkarte bestellt. Bis dahin kann die Praxis Ihren Versicherungsnachweis online bei uns abrufen."],
        "also": ["Ach, und meine Gesundheitskarte ist auch weg, ich brauche eine neue.",
                 "Außerdem ist meine Versichertenkarte kaputt, kann ich die gleich mit ersetzen lassen?"],
        "vague": [],
    },
    "kind_familienversichern": {
        "opener": [
            "Wir haben im {monat} ein Baby bekommen, wie kann ich unsere Tochter bei Ihnen mitversichern?",
            "Hallo, ich möchte meinen Sohn in die Familienversicherung aufnehmen.",
            "Kann mein Kind beitragsfrei über mich versichert werden? Mein Mann ist privat versichert.",
            "Guten Tag, ich brauche das Formular für die Familienversicherung meines Kindes.",
        ],
        "detail": ["Die Geburtsurkunde habe ich schon da.",
                   "Mein Partner verdient mehr als ich, ist das ein Problem?",
                   "Unser Kind ist jetzt drei Wochen alt."],
        "agent_q": ["Herzlichen Glückwunsch! Sind Sie und der andere Elternteil beide gesetzlich versichert?",
                    "Gern. Ich brauche den Namen und das Geburtsdatum des Kindes."],
        "resolve": ["Ich habe Ihnen den Fragebogen zur Familienversicherung in die App gelegt. Sobald er zurück ist, ist Ihr Kind ab Geburt versichert.",
                    "Ihr Kind ist ab Geburt familienversichert, die Gesundheitskarte schicken wir in etwa zwei Wochen zu."],
        "also": ["Und ich möchte noch mein Kind bei Ihnen familienversichern.",
                 "Außerdem: Wie bekomme ich unser Neugeborenes in die Familienversicherung?"],
        "vague": [],
    },
    "mitgliedsbescheinigung": {
        "opener": [
            "Mein neuer Arbeitgeber braucht eine Mitgliedsbescheinigung von Ihnen.",
            "Hallo, ich fange am Ersten eine neue Stelle an und soll eine Bescheinigung der Krankenkasse vorlegen.",
            "Können Sie meinem Arbeitgeber bitte bestätigen, dass ich bei Ihnen versichert bin?",
            "Guten Tag, die Personalabteilung fragt nach meiner Mitgliedsbescheinigung.",
        ],
        "detail": ["Ich starte am {datum} bei der neuen Firma.",
                   "Die Personalabteilung hat gesagt, das geht inzwischen elektronisch.",
                   "Ich brauche das relativ schnell."],
        "agent_q": ["Gerne. Wie heißt Ihr neuer Arbeitgeber und ab wann beginnt die Beschäftigung?",
                    "Kein Problem. Soll die Bescheinigung direkt an den Arbeitgeber gehen?"],
        "resolve": ["Die Mitgliedsbescheinigung ist elektronisch an Ihren Arbeitgeber übermittelt. Eine Kopie finden Sie in der App.",
                    "Ich habe die Bescheinigung erstellt, sie liegt in Ihrem Postfach in der Online-Geschäftsstelle."],
        "also": ["Und ich brauche noch eine Mitgliedsbescheinigung für meinen neuen Job.",
                 "Ach ja, mein Arbeitgeber will noch eine Bescheinigung von Ihnen."],
        "vague": [],
    },
    "kostenerstattung_status": {
        "opener": [
            "Ich habe vor vier Wochen eine Rechnung zur Erstattung eingereicht und noch nichts gehört.",
            "Hallo, wie ist der Stand bei meiner Kostenerstattung für die Osteopathie?",
            "Ich habe die Rechnung über {betrag} hochgeladen, wann bekomme ich das Geld?",
            "Guten Tag, meine eingereichte Arztrechnung ist immer noch nicht erstattet.",
        ],
        "detail": ["Ich habe die Rechnung über die App fotografiert und hochgeladen.",
                   "Es geht um {betrag}.",
                   "Ich habe keine Eingangsbestätigung bekommen."],
        "agent_q": ["Ich schaue nach. Wann haben Sie die Rechnung eingereicht?",
                    "Gern. Wissen Sie noch, auf welchem Weg Sie die Rechnung geschickt haben?"],
        "resolve": ["Die Rechnung ist geprüft, Sie bekommen {betrag} erstattet. Die Überweisung geht morgen raus.",
                    "Es fehlte die ärztliche Verordnung. Wenn Sie die nachreichen, erstatten wir sofort."],
        "also": ["Außerdem warte ich noch auf die Erstattung einer eingereichten Rechnung.",
                 "Und wie ist eigentlich der Stand bei meiner Kostenerstattung?"],
        "vague": ["Ich habe Ihnen da mal was geschickt und weiß nicht, ob das angekommen ist oder was jetzt passiert."],
    },
    "zuzahlungsbefreiung": {
        "opener": [
            "Ich habe dieses Jahr schon sehr viele Zuzahlungen geleistet, kann ich mich befreien lassen?",
            "Hallo, wie beantrage ich die Befreiung von den Zuzahlungen?",
            "Meine Mutter ist chronisch krank, gibt es da eine Obergrenze für Zuzahlungen?",
            "Guten Tag, ich möchte einen Antrag auf Zuzahlungsbefreiung stellen.",
        ],
        "detail": ["Ich habe alle Quittungen von Apotheke und Physiotherapie gesammelt.",
                   "Ich bekomme eine kleine Rente.",
                   "Mein Arzt hat eine chronische Erkrankung bescheinigt."],
        "agent_q": ["Gern. Die Belastungsgrenze liegt bei zwei Prozent des Bruttoeinkommens, bei chronisch Kranken bei einem Prozent. Haben Sie Ihre Quittungen?",
                    "Ich helfe Ihnen. Möchten Sie die Befreiung für den Rest des Jahres beantragen?"],
        "resolve": ["Ich habe Ihnen den Antrag geschickt. Schicken Sie ihn mit den Quittungen zurück, dann stellen wir den Befreiungsausweis aus.",
                    "Die Belastungsgrenze ist erreicht. Ihr Befreiungsausweis kommt per Post, zu viel gezahlte {betrag} erstatten wir."],
        "also": ["Und kann ich mich eigentlich von den Zuzahlungen befreien lassen?",
                 "Ach, und ich wollte noch die Zuzahlungsbefreiung beantragen."],
        "vague": [],
    },
    "app_login": {
        "opener": [
            "Ich komme nicht mehr in Ihre App, der Login schlägt immer fehl.",
            "Hallo, der Freischaltcode für die App ist nie bei mir angekommen.",
            "Seit dem Handywechsel kann ich mich in der App nicht mehr anmelden.",
            "Guten Tag, die App sagt immer 'Identifizierung fehlgeschlagen'.",
        ],
        "detail": ["Ich habe ein neues Smartphone.",
                   "Ich habe es schon dreimal versucht.",
                   "Der Brief mit dem Code kam nicht."],
        "agent_q": ["Das klären wir. Haben Sie das Gerät gewechselt oder die App neu installiert?",
                    "Kein Problem. Wann haben Sie sich zuletzt erfolgreich angemeldet?"],
        "resolve": ["Ich habe Ihr altes Gerät abgemeldet und einen neuen Freischaltcode verschickt. Der kommt in drei Tagen per Post.",
                    "Ihr Konto war nach mehreren Fehlversuchen gesperrt. Es ist entsperrt, Sie können sich wieder anmelden."],
        "also": ["Und übrigens komme ich auch nicht mehr in die App rein.",
                 "Außerdem funktioniert mein Login in der App nicht."],
        "vague": ["Mit dem Handy und Ihrem Programm da klappt irgendwas nicht, ich bin da nicht so fit."],
    },
    "physio_genehmigung": {
        "opener": [
            "Mein Orthopäde hat mir Physiotherapie verordnet, muss die Krankenkasse das genehmigen?",
            "Hallo, ich habe eine Verordnung über 20 Einheiten Krankengymnastik, übernehmen Sie das?",
            "Meine Physiopraxis sagt, für die Folgeverordnung brauche ich eine Genehmigung von Ihnen.",
        ],
        "detail": ["Es geht um meinen Rücken nach einem Bandscheibenvorfall.",
                   "Die Praxis möchte nächste Woche anfangen.",
                   "Es ist schon die dritte Verordnung."],
        "agent_q": ["Ich schaue mir das an. Welche Diagnose steht auf der Verordnung?",
                    "Gern. Ist das eine Erst- oder eine Folgeverordnung?"],
        "resolve": ["Für diese Diagnose ist keine Genehmigung nötig, die Praxis kann direkt mit uns abrechnen.",
                    "Ich habe die Genehmigung erteilt, die Praxis bekommt heute eine Bestätigung."],
        "also": ["Und brauche ich für meine Physiotherapie eine Genehmigung?",
                 "Außerdem habe ich eine neue Verordnung für Krankengymnastik, geht die in Ordnung?"],
        "vague": [],
    },
    "zahnersatz_hkp": {
        "opener": [
            "Mein Zahnarzt hat mir einen Heil- und Kostenplan für eine Krone gegeben, was zahlen Sie dazu?",
            "Hallo, ich brauche eine Brücke und der Eigenanteil ist sehr hoch.",
            "Wie hoch ist der Festzuschuss für Zahnersatz bei Ihnen?",
            "Guten Tag, ich habe den Kostenplan für mein Implantat eingereicht, ist der genehmigt?",
        ],
        "detail": ["Der Plan geht über {betrag}.",
                   "Ich habe ein lückenloses Bonusheft seit zehn Jahren.",
                   "Der Zahnarzt möchte im {monat} anfangen."],
        "agent_q": ["Gern. Haben Sie ein Bonusheft und wie viele Jahre ist es lückenlos?",
                    "Ich schaue nach. Hat die Praxis den Plan schon digital an uns geschickt?"],
        "resolve": ["Der Plan ist genehmigt. Mit Ihrem Bonusheft bekommen Sie 75 Prozent Festzuschuss.",
                    "Der Kostenplan liegt vor, wir übernehmen {betrag}. Der Rest ist Ihr Eigenanteil."],
        "also": ["Und was zahlen Sie eigentlich beim Zahnersatz dazu?",
                 "Außerdem habe ich einen Heil- und Kostenplan vom Zahnarzt, können Sie den prüfen?"],
        "vague": [],
    },
    "bonus_einloesen": {
        "opener": [
            "Ich habe genug Punkte im Bonusprogramm gesammelt, wie bekomme ich das Geld?",
            "Hallo, meine Bonuspunkte für den Gesundheitscheck sind nicht gutgeschrieben.",
            "Wie kann ich meine Bonusprämie auszahlen lassen?",
            "Guten Tag, ich habe Nachweise für das Bonusprogramm hochgeladen, aber die Punkte fehlen.",
        ],
        "detail": ["Ich war beim Check-up und beim Zahnarzt.",
                   "In der App steht, dass ich {betrag} Prämie habe.",
                   "Ich habe die Nachweise vor drei Wochen hochgeladen."],
        "agent_q": ["Gern. Haben Sie die Nachweise über die App eingereicht?",
                    "Ich schaue nach. Für welches Jahr möchten Sie die Prämie einlösen?"],
        "resolve": ["Die Punkte sind jetzt gutgeschrieben. Ihre Prämie von {betrag} wird auf Ihr Konto überwiesen.",
                    "Ich habe die Auszahlung veranlasst, das Geld ist in etwa einer Woche da."],
        "also": ["Und wie löse ich eigentlich meine Bonuspunkte ein?",
                 "Ach ja, meine Punkte aus dem Bonusprogramm sind auch noch nicht da."],
        "vague": [],
    },
    "beitrag_selbststaendig": {
        "opener": [
            "Ich bin seit kurzem selbständig, wie berechnet sich mein Beitrag?",
            "Hallo, mein Beitrag als Selbständiger ist viel zu hoch, ich verdiene gar nicht so viel.",
            "Sie haben mich auf den Höchstbeitrag eingestuft, weil der Einkommensnachweis fehlte.",
            "Guten Tag, ich habe meinen Einkommensteuerbescheid bekommen, wo schicke ich den hin?",
        ],
        "detail": ["Mein Gewinn lag letztes Jahr deutlich unter dem, was Sie angesetzt haben.",
                   "Der Steuerbescheid ist von letzter Woche.",
                   "Ich zahle aktuell {betrag} im Monat."],
        "agent_q": ["Ich helfe Ihnen. Liegt Ihnen der aktuelle Einkommensteuerbescheid vor?",
                    "Gern. Seit wann sind Sie selbständig tätig?"],
        "resolve": ["Laden Sie den Steuerbescheid in der App hoch, dann stufen wir Sie rückwirkend neu ein und erstatten zu viel gezahlte Beiträge.",
                    "Ich habe Ihre Einstufung angepasst. Ihr neuer Beitrag beträgt {betrag} im Monat."],
        "also": ["Und wie wird eigentlich mein Beitrag als Selbständiger berechnet?",
                 "Außerdem habe ich einen neuen Steuerbescheid, ändert sich dann mein Beitrag?"],
        "vague": ["Das mit meinem Beitrag verstehe ich nicht, das ist irgendwie anders als früher."],
    },
    "zusatzbeitrag": {
        "opener": [
            "Ich habe einen Brief bekommen, dass der Zusatzbeitrag steigt. Warum?",
            "Hallo, um wie viel wird mein Beitrag durch den neuen Zusatzbeitrag teurer?",
            "Der Zusatzbeitrag wird schon wieder erhöht, was bedeutet das für mich?",
        ],
        "detail": ["Der Brief kam letzte Woche.",
                   "Ich verdiene etwa 3.500 Euro brutto.",
                   "Andere Kassen sind günstiger, habe ich gelesen."],
        "agent_q": ["Ich erkläre es Ihnen gern. Sind Sie angestellt?",
                    "Gern. Möchten Sie wissen, wie viel Sie konkret mehr zahlen?"],
        "resolve": ["Bei Ihrem Einkommen sind das etwa {betrag} mehr im Monat, die Hälfte trägt Ihr Arbeitgeber.",
                    "Die Erhöhung gilt ab Januar. Sie haben dadurch ein Sonderkündigungsrecht bis Ende des Monats."],
        "also": ["Und warum steigt eigentlich der Zusatzbeitrag?",
                 "Außerdem habe ich gelesen, dass der Zusatzbeitrag erhöht wird, stimmt das?"],
        "vague": [],
    },
    "beitragsrueckstand": {
        "opener": [
            "Ich habe eine Mahnung wegen offener Beiträge bekommen.",
            "Hallo, ich bin mit meinen Beiträgen im Rückstand, kann ich in Raten zahlen?",
            "Sie haben mir einen Säumniszuschlag berechnet, dabei habe ich überwiesen.",
        ],
        "detail": ["Es geht um {betrag}.",
                   "Ich hatte die letzten Monate finanzielle Schwierigkeiten.",
                   "Die Lastschrift ist zurückgegangen, weil ich das Konto gewechselt habe."],
        "agent_q": ["Ich schaue mir Ihr Beitragskonto an. Welche Monate sind betroffen?",
                    "Gern. Möchten Sie eine Ratenzahlung vereinbaren?"],
        "resolve": ["Ich habe eine Ratenzahlung über sechs Monate eingerichtet, das Mahnverfahren ruht.",
                    "Die Zahlung ist inzwischen eingegangen. Den Säumniszuschlag nehme ich zurück."],
        "also": ["Und ich habe da noch eine Mahnung wegen offener Beiträge.",
                 "Außerdem bin ich mit meinen Beiträgen etwas hinterher, geht Ratenzahlung?"],
        "vague": [],
    },
    "kassenwechsel": {
        "opener": [
            "Ich möchte meine Mitgliedschaft kündigen und zu einer anderen Kasse wechseln.",
            "Hallo, wie lange ist die Kündigungsfrist, wenn ich die Krankenkasse wechseln will?",
            "Ich ziehe ins Ausland und muss meine Versicherung bei Ihnen beenden.",
        ],
        "detail": ["Ich bin seit fünf Jahren bei Ihnen.",
                   "Die andere Kasse ist günstiger.",
                   "Ich ziehe im {monat} nach Österreich."],
        "agent_q": ["Schade, dass Sie gehen möchten. Darf ich fragen, warum?",
                    "Ich prüfe das. Haben Sie sich schon bei der neuen Kasse angemeldet?"],
        "resolve": ["Die neue Kasse meldet den Wechsel elektronisch, eine Kündigung bei uns ist nicht nötig. Die Frist beträgt zwei Monate zum Monatsende.",
                    "Ihre Mitgliedschaft endet mit dem Wegzug. Bitte schicken Sie uns die Abmeldebescheinigung."],
        "also": ["Und ich überlege, die Kasse zu wechseln, wie geht das?",
                 "Außerdem möchte ich kündigen, welche Frist gilt da?"],
        "vague": [],
    },
    "kinderkrankengeld": {
        "opener": [
            "Mein Kind ist krank und ich muss zu Hause bleiben. Bekomme ich Kinderkrankengeld?",
            "Hallo, wie beantrage ich Kinderkrankengeld?",
            "Wie viele Kinderkrankentage habe ich noch dieses Jahr?",
        ],
        "detail": ["Meine Tochter ist fünf und hat Fieber.",
                   "Der Kinderarzt hat eine Bescheinigung ausgestellt.",
                   "Ich bin alleinerziehend."],
        "agent_q": ["Gute Besserung für Ihr Kind. Hat der Kinderarzt die Bescheinigung schon ausgestellt?",
                    "Gern. Wie alt ist Ihr Kind?"],
        "resolve": ["Schicken Sie die Bescheinigung über die App, das Kinderkrankengeld zahlen wir dann direkt an Sie aus.",
                    "Als Alleinerziehende haben Sie dieses Jahr noch zwölf Tage Anspruch. Der Antrag ist angelegt."],
        "also": ["Und bekomme ich eigentlich Kinderkrankengeld, wenn mein Kind krank ist?",
                 "Außerdem wollte ich wegen Kinderkrankengeld fragen."],
        "vague": [],
    },
    "hilfsmittel_rollator": {
        "opener": [
            "Meine Mutter braucht einen Rollator, übernimmt die Kasse die Kosten?",
            "Hallo, der Arzt hat mir einen Rollator verschrieben, wo bekomme ich den?",
            "Das Sanitätshaus sagt, es wartet auf Ihre Genehmigung für den Rollator.",
        ],
        "detail": ["Sie kann nach der Hüft-OP nicht mehr sicher laufen.",
                   "Das Rezept ist von gestern.",
                   "Das Sanitätshaus hat den Antrag letzte Woche geschickt."],
        "agent_q": ["Gern. Liegt schon eine ärztliche Verordnung vor?",
                    "Ich schaue nach. Welches Sanitätshaus ist es?"],
        "resolve": ["Der Rollator ist genehmigt. Das Sanitätshaus liefert ihn, Sie zahlen nur die gesetzliche Zuzahlung von zehn Euro.",
                    "Ich habe den Antrag bevorzugt bearbeitet, die Genehmigung ist raus."],
        "also": ["Und meine Mutter bräuchte noch einen Rollator, zahlen Sie den?"],
        "vague": [],
    },
    "adresse_aendern": {
        "opener": [
            "Ich bin umgezogen und möchte meine neue Adresse mitteilen.",
            "Hallo, bitte ändern Sie meine Anschrift.",
        ],
        "detail": ["Die neue Adresse ist in {stadt}.", "Ich wohne seit dem {datum} dort."],
        "agent_q": ["Gern. Wie lautet Ihre neue Anschrift?", "Kein Problem. Ab wann gilt die neue Adresse?"],
        "resolve": ["Ich habe Ihre Adresse geändert. Eine neue Karte brauchen Sie nicht.",
                    "Die neue Anschrift ist gespeichert, die Post geht ab sofort dorthin."],
        "also": ["Ach, und ich bin umgezogen, können Sie meine Adresse ändern?"],
        "vague": [],
    },
    "reha_antrag": {
        "opener": [
            "Mein Arzt empfiehlt mir eine Reha, wie stelle ich den Antrag?",
            "Hallo, ich möchte eine Mutter-Kind-Kur beantragen.",
        ],
        "detail": ["Ich bin seit Monaten erschöpft.", "Der Arzt hat das Attest schon ausgefüllt."],
        "agent_q": ["Gern. Sind Sie berufstätig? Dann ist eventuell die Rentenversicherung zuständig.",
                    "Ich helfe Ihnen. Liegt schon eine ärztliche Bescheinigung vor?"],
        "resolve": ["Ich schicke Ihnen den Antrag zu. Wir prüfen, wer zuständig ist, und leiten ihn bei Bedarf weiter.",
                    "Der Antrag ist angelegt, die Entscheidung bekommen Sie innerhalb von drei Wochen."],
        "also": ["Und wie beantrage ich eigentlich eine Reha?"],
        "vague": [],
    },
    "widerspruch": {
        "opener": [
            "Sie haben meinen Antrag abgelehnt, dagegen möchte ich Widerspruch einlegen.",
            "Hallo, ich bin mit dem Bescheid nicht einverstanden. Wie lege ich Widerspruch ein?",
        ],
        "detail": ["Der Bescheid ist vom {datum}.", "Mein Arzt hält die Behandlung für notwendig."],
        "agent_q": ["Das verstehe ich. Um welchen Bescheid geht es genau?",
                    "Gern. Haben Sie eine Begründung oder ein ärztliches Schreiben?"],
        "resolve": ["Ich nehme Ihren Widerspruch auf. Er wird erneut geprüft, die Frist ist gewahrt.",
                    "Schicken Sie den Widerspruch schriftlich innerhalb eines Monats, ich gebe Ihnen die Adresse."],
        "also": ["Und gegen die Ablehnung möchte ich noch Widerspruch einlegen."],
        "vague": [],
    },
    "facharzttermin": {
        "opener": [
            "Ich bekomme seit Wochen keinen Termin beim Neurologen, können Sie helfen?",
            "Hallo, haben Sie einen Terminservice für Fachärzte?",
        ],
        "detail": ["Die Praxen sagen, frühestens in vier Monaten.", "Ich habe eine Überweisung vom Hausarzt."],
        "agent_q": ["Ich helfe gern. Haben Sie eine Überweisung mit Dringlichkeitscode?",
                    "Gern. In welcher Region suchen Sie?"],
        "resolve": ["Ich habe Sie an unseren Terminservice weitergegeben, der meldet sich innerhalb von zwei Tagen mit einem Termin.",
                    "Mit dem Dringlichkeitscode vermittelt die Terminservicestelle einen Termin innerhalb von vier Wochen."],
        "also": ["Und können Sie mir auch bei einem Facharzttermin helfen?"],
        "vague": [],
    },
    "reiseimpfung": {
        "opener": ["Übernehmen Sie die Kosten für meine Reiseimpfung gegen Typhus?"],
        "detail": ["Ich fliege im {monat} nach Thailand."],
        "agent_q": ["Gern. Haben Sie die Rechnung von der Impfung schon?"],
        "resolve": ["Ja, wir erstatten Reiseimpfungen. Reichen Sie die Rechnung über die App ein."],
        "also": ["Und zahlen Sie eigentlich Reiseimpfungen?"],
        "vague": [],
    },
    "epa_einrichten": {
        "opener": ["Wie richte ich die elektronische Patientenakte ein?"],
        "detail": ["Ich möchte, dass mein Hausarzt die Befunde dort ablegt."],
        "agent_q": ["Gern. Haben Sie unsere App schon installiert?"],
        "resolve": ["Die ePA ist automatisch angelegt. In der App können Sie festlegen, welche Praxen zugreifen dürfen."],
        "also": ["Und wie funktioniert eigentlich die elektronische Patientenakte?"],
        "vague": [],
    },
}

SMALL_TALK = [
    ("Entschuldigung, ich bin gerade im Auto, es kann etwas rauschen.", "Kein Problem, ich verstehe Sie gut."),
    ("Ich hänge schon eine Weile in der Warteschleife, die Musik kann ich jetzt mitsingen.",
     "Entschuldigen Sie die Wartezeit, und danke für Ihre Geduld!"),
    ("Schönes Wetter heute, oder? Endlich mal Sonne.", "Ja, wirklich! Hoffentlich können Sie es nachher genießen."),
    ("Mein Hund bellt im Hintergrund, tut mir leid.", "Ach, das macht gar nichts."),
    ("Wie geht es Ihnen heute? Viel los, oder?", "Ja, es ist einiges los, aber gut, danke der Nachfrage!"),
    ("Schönes Wochenende schon mal, falls ich es nachher vergesse.", "Danke, Ihnen auch!"),
]

FOLLOW_UPS = [
    ("Wie lange dauert das ungefähr?", "In der Regel ist das innerhalb weniger Werktage erledigt."),
    ("Bekomme ich dazu eine Bestätigung?", "Ja, die Bestätigung kommt in Ihr Postfach in der App."),
    ("Muss ich sonst noch etwas tun?", "Nein, von Ihrer Seite ist nichts weiter nötig."),
    ("Und das passiert nicht noch mal?", "Ich habe einen Vermerk angelegt, damit wir das im Blick behalten."),
]

GREET = {
    "voice": "Guten Tag, Ihre Krankenkasse, mein Name ist {agent}. Was kann ich für Sie tun?",
    "web_messaging": "Hallo, hier ist {agent} vom Kundenservice. Wie kann ich Ihnen im Chat helfen?",
    "email": "Sehr geehrte Damen und Herren, vielen Dank für Ihre Nachricht. Mein Name ist {agent}, ich kümmere mich um Ihr Anliegen.",
}
CLOSING_CUSTOMER = ["Vielen Dank, das hilft mir sehr.", "Super, danke schön.", "Alles klar, das war's, danke.",
                    "Danke für die Hilfe.", "Prima, vielen Dank."]
CLOSING_AGENT = ["Gern geschehen! Kann ich sonst noch etwas für Sie tun?", "Sehr gern. Ich wünsche Ihnen einen schönen Tag!",
                 "Gerne. Bleiben Sie gesund!"]
AGENTS = ["Frau Becker", "Herr Yilmaz", "Frau Nowak", "Herr Schulz", "Frau Krüger", "Herr Wagner", "Frau Hoffmann"]
CITIES = ["Hannover", "Leipzig", "Bielefeld", "Freiburg", "Kassel", "Rostock"]
MONTHS = ["Januar", "März", "Mai", "Juli", "September", "November"]

CHANNELS = [("voice", "pflichtversichert", 40), ("voice", "freiwillig", 20), ("web_messaging", None, 22), ("email", None, 18)]


def fill(rng: random.Random, text: str) -> str:
    amount = rng.choice([38.5, 64.2, 89.9, 124.0, 186.75, 240.0, 312.4, 455.0, 980.0])
    return text.format(
        betrag=f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."),
        stadt=rng.choice(CITIES), monat=rng.choice(MONTHS),
        datum=rng.choice(["1. März", "15. April", "3. Juni", "20. August", "1. Oktober"]),
    )


def plan_conversations(rng: random.Random) -> list[list[str]]:
    keys = list(INTENTS)
    occurrences = [k for k in keys for _ in range(INTENTS[k][3])]
    rng.shuffle(occurrences)
    primaries = list(keys)
    pool = occurrences.copy()
    for k in keys:
        pool.remove(k)
    extra_needed = N_CONVERSATIONS - len(primaries)
    primaries += pool[:extra_needed]
    secondaries = pool[extra_needed:]
    rng.shuffle(primaries)
    convs = [[p] for p in primaries]

    def segment_of(intents: list[str]) -> str | None:
        segs = {INTENTS[i][4] for i in intents} - {None}
        return segs.pop() if len(segs) == 1 else (None if not segs else "conflict")

    for s in secondaries:
        for _ in range(200):
            c = rng.choice(convs)
            if s in c or len(c) >= 3 or (len(c) == 2 and rng.random() < 0.85):
                continue
            if segment_of(c + [s]) == "conflict":
                continue
            c.append(s)
            break
    return convs


def build_conversation(rng: random.Random, intents: list[str], channel: str, small_talk: bool,
                       ambiguous: bool) -> tuple[list[dict], list[str]]:
    agent = rng.choice(AGENTS)
    short = channel != "voice" and len(intents) == 1 and not small_talk and rng.random() < 0.3
    turns = [] if short else [{"speaker": "agent", "text": GREET[channel].format(agent=agent)}]
    tags = []
    if small_talk:
        st = rng.choice(SMALL_TALK)
        turns += [{"speaker": "customer", "text": st[0]}, {"speaker": "agent", "text": st[1]}]
        tags.append("small_talk")
    first = T[intents[0]]
    if ambiguous and first["vague"]:
        opener = rng.choice(first["vague"])
        tags.append("ambiguous")
    else:
        opener = rng.choice(first["opener"])
    turns.append({"speaker": "customer", "text": fill(rng, opener)})
    turns.append({"speaker": "agent", "text": fill(rng, rng.choice(first["agent_q"]))})
    turns.append({"speaker": "customer", "text": fill(rng, rng.choice(first["detail"]))})
    turns.append({"speaker": "agent", "text": fill(rng, rng.choice(first["resolve"]))})
    if short:
        return turns, tags
    if rng.random() < 0.35:
        turns += [{"speaker": s, "text": t} for s, t in zip(("customer", "agent"), rng.choice(FOLLOW_UPS))]
    for extra in intents[1:]:
        tp = T[extra]
        turns.append({"speaker": "customer", "text": fill(rng, rng.choice(tp["also"]))})
        if rng.random() < 0.6:
            turns.append({"speaker": "agent", "text": fill(rng, rng.choice(tp["agent_q"]))})
            turns.append({"speaker": "customer", "text": fill(rng, rng.choice(tp["detail"]))})
        turns.append({"speaker": "agent", "text": fill(rng, rng.choice(tp["resolve"]))})
    if len(intents) > 1:
        tags.append("multi_intent")
    if rng.random() < 0.7 or len(turns) < 6:
        turns.append({"speaker": "customer", "text": rng.choice(CLOSING_CUSTOMER)})
        turns.append({"speaker": "agent", "text": rng.choice(CLOSING_AGENT)})
    return turns[:12], tags


def generate() -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    convs = plan_conversations(rng)
    channel_slots = [(ch, seg) for ch, seg, n in CHANNELS for _ in range(n)]
    rng.shuffle(channel_slots)
    ambiguous_idx = set(rng.sample([i for i, c in enumerate(convs) if T[c[0]]["vague"]], 6))
    small_talk_idx = set(rng.sample(range(N_CONVERSATIONS), 12))
    start = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)
    transcripts, truth = [], []
    for i, intents in enumerate(convs):
        need = {INTENTS[k][4] for k in intents} - {None}
        need_seg = need.pop() if need else None
        slot_i = next((j for j, (_, seg) in enumerate(channel_slots) if need_seg is None or seg in (None, need_seg)), None)
        if slot_i is None:
            channel, seg = channel_slots.pop(0)
            seg = None
        else:
            channel, seg = channel_slots.pop(slot_i)
        segment = seg or need_seg or rng.choice(["pflichtversichert", "freiwillig", "rentner", "familienversichert"])
        turns, tags = build_conversation(rng, intents, channel, i in small_talk_idx, i in ambiguous_idx)
        cid = f"GKV-{i + 1:04d}"
        ts = start + timedelta(minutes=rng.randint(0, 45 * 24 * 60))
        queue = {"voice": "Servicecenter Telefon", "web_messaging": "Online-Chat", "email": "Posteingang E-Mail"}[channel]
        transcripts.append({"conversation_id": cid, "channel": channel, "segment": segment, "language": "de",
                            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "queue": queue, "turns": turns})
        truth.append({"conversation_id": cid, "tags": tags,
                      "intents": [{"key": k, "label": INTENTS[k][0], "l1_id": INTENTS[k][1], "l2_id": INTENTS[k][2]}
                                  for k in intents]})
    gt = {"seed": SEED, "note": "Reference only. Do not import; Intent Studio's ground-truth check reads only the telco sample.",
          "intent_types": [{"key": k, "label": v[0], "l1_id": v[1], "l2_id": v[2]} for k, v in INTENTS.items()],
          "conversations": truth}
    return transcripts, gt


def write(out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    l2_ids = {c["id"] for c in TAXONOMY["categories"] if c["level"] == 2}
    assert all(v[2] in l2_ids for v in INTENTS.values())
    transcripts, gt = generate()
    (out / "gkv_taxonomy_l1_l2.json").write_text(json.dumps(TAXONOMY, indent=2, ensure_ascii=False) + "\n")
    (out / "gkv_transcripts.json").write_text(json.dumps(transcripts, indent=2, ensure_ascii=False) + "\n")
    (out / "gkv_ground_truth.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False) + "\n")
    with (out / "gkv_transcripts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["conversation_id", "channel", "segment", "language", "timestamp", "queue", "transcript"])
        for t in transcripts:
            text = "\n".join(f"{'Kunde' if x['speaker'] == 'customer' else 'Mitarbeiter'}: {x['text']}" for x in t["turns"])
            w.writerow([t["conversation_id"], t["channel"], t["segment"], t["language"], t["timestamp"], t["queue"], text])
    n_intents = sum(len(c["intents"]) for c in gt["conversations"])
    tags: dict[str, int] = {}
    for c in gt["conversations"]:
        for tag in c["tags"]:
            tags[tag] = tags.get(tag, 0) + 1
    print(f"Wrote {len(transcripts)} conversations, {n_intents} intents, {len(INTENTS)} intent types, tags={tags} → {out}")


if __name__ == "__main__":
    write()
