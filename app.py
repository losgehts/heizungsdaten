
from datetime import datetime
from pathlib import Path
import os
import sqlite3

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Die Datenbank liegt immer neben dieser Datei.
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "daten.db"


# Reihenfolge und Bedeutung der Messwerte
FELDER = [
    ("z_eg", "Zählerstand Wärmemenge EG", "MWh"),
    ("z_og", "Zählerstand Wärmemenge OG", "MWh"),
    ("z_dg", "Zählerstand Wärmemenge DG", "MWh"),
    ("vl", "Vorlauftemperatur", "°C"),
    ("rl", "Rücklauftemperatur", "°C"),
    ("temp_ged", "Außentemperatur gedeckelt", "°C"),
    ("temp", "Außentemperatur Ist", "°C"),
    ("kessel_soll", "Kessel Solltemperatur", "°C"),
    ("kessel_ist", "Kessel Isttemperatur", "°C"),
    ("ww_soll", "Warmwasser Solltemperatur", "°C"),
    ("ww_ist", "Warmwasser Isttemperatur", "°C"),
    ("raum_temp_soll", "Angestrebte Raumtemperatur", "°C"),
]


def verbinden():
    """Eine Verbindung zur SQLite-Datenbank öffnen."""
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """Tabellen und Spaltenbeschreibungen anlegen."""
    with verbinden() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS messwerte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datum TEXT NOT NULL,
                uhrzeit TEXT NOT NULL,
                z_eg REAL NOT NULL,
                z_og REAL NOT NULL,
                z_dg REAL NOT NULL,
                vl REAL NOT NULL,
                rl REAL NOT NULL,
                temp_ged REAL NOT NULL,
                temp REAL NOT NULL,
                kessel_soll REAL NOT NULL,
                kessel_ist REAL NOT NULL,
                ww_soll REAL NOT NULL,
                ww_ist REAL NOT NULL,
                raum_temp_soll REAL NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS spalten_info (
                spaltenname TEXT PRIMARY KEY,
                bedeutung TEXT NOT NULL,
                einheit TEXT NOT NULL
            )
        """)

        beschreibungen = [
            ("id", "Eindeutige Datensatznummer", "—"),
            ("datum", "Datum der Messwerterfassung", "—"),
            ("uhrzeit", "Uhrzeit der Messwerterfassung", "—"),
            *FELDER,
        ]

        db.executemany("""
            INSERT INTO spalten_info
                (spaltenname, bedeutung, einheit)
            VALUES (?, ?, ?)
            ON CONFLICT(spaltenname) DO UPDATE SET
                bedeutung = excluded.bedeutung,
                einheit = excluded.einheit
        """, beschreibungen)


@app.route("/", methods=["GET", "POST"])
def index():
    jetzt = datetime.now().astimezone()
    datum_default = jetzt.strftime("%Y-%m-%d")
    uhrzeit_default = jetzt.strftime("%H:%M")

    werte = {
        "datum": datum_default,
        "uhrzeit": uhrzeit_default,
        **{name: "" for name, _, _ in FELDER},
    }
    werte["raum_temp_soll"] = "20"

    fehler = None
    gespeichert = request.args.get("gespeichert") == "1"

    if request.method == "POST":
        # Eingaben beibehalten, falls die Validierung fehlschlägt.
        werte = {
            "datum": request.form.get("datum", ""),
            "uhrzeit": request.form.get("uhrzeit", ""),
            **{
                name: request.form.get(name, "").strip()
                for name, _, _ in FELDER
            },
        }

        try:
            # Datum und Uhrzeit prüfen.
            datetime.strptime(werte["datum"], "%Y-%m-%d")
            datetime.strptime(werte["uhrzeit"], "%H:%M")

            # Deutsche Dezimalkommas werden akzeptiert.
            zahlen = []
            for name, bedeutung, _ in FELDER:
                eingabe = werte[name].replace(",", ".")
                zahl = float(eingabe)

                if not __import__("math").isfinite(zahl):
                    raise ValueError(
                        f"{bedeutung}: Bitte eine gültige Zahl eingeben."
                    )

                zahlen.append(zahl)

            spalten = ["datum", "uhrzeit"] + [
                name for name, _, _ in FELDER
            ]
            platzhalter = ", ".join("?" for _ in spalten)
            spalten_sql = ", ".join(spalten)

            with verbinden() as db:
                db.execute(
                    f"INSERT INTO messwerte ({spalten_sql}) "
                    f"VALUES ({platzhalter})",
                    [werte["datum"], werte["uhrzeit"], *zahlen],
                )

            return redirect(url_for("index", gespeichert=1))

        except ValueError as exc:
            fehler = str(exc) or (
                "Bitte Datum, Uhrzeit und alle Zahlenwerte prüfen."
            )
        except sqlite3.Error:
            app.logger.exception("Fehler beim Speichern der Messwerte")
            fehler = (
                "Die Daten konnten nicht gespeichert werden. "
                "Bitte prüfe die Anwendung und die Datenbank."
            )

    with verbinden() as db:
        eintraege = db.execute("""
            SELECT * FROM messwerte
            ORDER BY datum DESC, uhrzeit DESC, id DESC
            LIMIT 20
        """).fetchall()

    return render_template(
        "index.html",
        felder=FELDER,
        werte=werte,
        fehler=fehler,
        gespeichert=gespeichert,
        eintraege=eintraege,
    )


# Auch beim Start mit einem WSGI-Server initialisieren.
init_db()

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
