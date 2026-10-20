
from datetime import datetime
from pathlib import Path
import csv
import io
import math
import os
import sqlite3
import tempfile

from flask import (
    Flask, render_template, request, redirect, url_for,
    send_file, abort
)

app = Flask(__name__)

VERSION = "0.01"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "daten.db"

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

# Plausibilitätsgrenzen: inklusive Grenzwerte
GRENZEN = {
    "z_eg": (40, 200),
    "z_og": (40, 200),
    "z_dg": (40, 200),
    "vl": (28, 70),
    "rl": (28, 70),
    "temp_ged": (-10, 25),
    "temp": (-10, 25),
    "kessel_soll": (20, 90),
    "kessel_ist": (20, 90),
    "ww_soll": (20, 80),
    "ww_ist": (20, 80),
    "raum_temp_soll": (10, 30),
}

ZAEHLER = {"z_eg", "z_og", "z_dg"}


def verbinden():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_db():
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


def zahl_einlesen(eingabe):
    """Zahlen mit deutschem Dezimalkomma oder Punkt akzeptieren."""
    return float(eingabe.strip().replace(",", "."))


def pruefe_steigende_zaehler(db, zahlen):
    """Prüft neue Zählerstände gegen den letzten gespeicherten Stand.

       später verbessern: nicht gegen den letzten gespeicherten, 
       sondern gegen den, der zeitlich davor liegt (z.B. wenn man ältere 
       Stände nachträgt.)
    """
    fehler = []

    bezeichnungen = {
        "z_eg": "Zählerstand Wärmemenge EG",
        "z_og": "Zählerstand Wärmemenge OG",
        "z_dg": "Zählerstand Wärmemenge DG",
    }

    letzter = db.execute("""
        SELECT z_eg, z_og, z_dg
        FROM messwerte
        ORDER BY datum DESC, uhrzeit DESC, id DESC
        LIMIT 1
    """).fetchone()

    # Noch keine Messwerte vorhanden.
    if letzter is None:
        return fehler

    for name, bedeutung in bezeichnungen.items():
        neu = zahlen.get(name)

        # Bereichsfehler werden bereits separat gemeldet.
        if neu is None:
            continue

        alt = letzter[name]

        if neu <= alt:
            fehler.append(
                f"{bedeutung}: Der neue Wert ({neu:g} MWh) "
                f"muss größer als der letzte gespeicherte Wert "
                f"({alt:g} MWh) sein."
            )

    return fehler


@app.route("/", methods=["GET", "POST"])
def index():
    jetzt = datetime.now().astimezone()

    werte = {
        "datum": jetzt.strftime("%Y-%m-%d"),
        "uhrzeit": jetzt.strftime("%H:%M"),
        **{name: "" for name, _, _ in FELDER},
        "raum_temp_soll": "20",
    }

    fehler = []
    korrigierte_felder = []
    gespeichert = request.args.get("gespeichert") == "1"

    if request.method == "POST":
        werte = {
            "datum": request.form.get("datum", ""),
            "uhrzeit": request.form.get("uhrzeit", ""),
            **{
                name: request.form.get(name, "").strip()
                for name, _, _ in FELDER
            },
        }

        zahlen = {}

        try:
            datetime.strptime(werte["datum"], "%Y-%m-%d")
        except ValueError:
            fehler.append("Bitte ein gültiges Datum angeben.")

        try:
            datetime.strptime(werte["uhrzeit"], "%H:%M")
        except ValueError:
            fehler.append("Bitte eine gültige Uhrzeit angeben.")

        for name, bedeutung, einheit in FELDER:
            try:
                zahl = zahl_einlesen(werte[name])

                if not math.isfinite(zahl):
                    raise ValueError

                # Zählerstände über 1000 werden als kWh interpretiert.
                if name in ZAEHLER and zahl > 1000:
                    zahl /= 1000
                    korrigierte_felder.append(name)

                minimum, maximum = GRENZEN[name]

                if not minimum <= zahl <= maximum:
                    fehler.append(
                        f"{bedeutung}: {zahl:g} {einheit} liegt "
                        f"außerhalb des erlaubten Bereichs "
                        f"({minimum:g} bis {maximum:g} {einheit})."
                    )
                else:
                    zahlen[name] = zahl

            except (ValueError, TypeError):
                fehler.append(
                    f"{bedeutung}: Bitte eine gültige Zahl eingeben."
                )

        if not fehler:
            with verbinden() as db:
                fehler.extend(pruefe_steigende_zaehler(db, zahlen))

        if not fehler:
            spalten = ["datum", "uhrzeit"] + [
                name for name, _, _ in FELDER
            ]
            platzhalter = ", ".join("?" for _ in spalten)
            spalten_sql = ", ".join(spalten)

            try:
                with verbinden() as db:
                    db.execute(
                        f"INSERT INTO messwerte ({spalten_sql}) "
                        f"VALUES ({platzhalter})",
                        [
                            werte["datum"],
                            werte["uhrzeit"],
                            *[zahlen[name] for name, _, _ in FELDER],
                        ],
                    )

                return redirect(url_for(
                    "index",
                    gespeichert=1,
                    korrigiert=",".join(korrigierte_felder),
                ))

            except sqlite3.Error:
                app.logger.exception("Fehler beim Speichern")
                fehler.append(
                    "Speichern fehlgeschlagen. "
                    "Bitte prüfe die Datenbank."
                )

    korrigiert = request.args.get("korrigiert", "").split(",")
    korrigiert = [
        name for name in korrigiert
        if name in ZAEHLER
    ]

    with verbinden() as db:
        eintraege = db.execute("""
            SELECT * FROM messwerte
            ORDER BY datum DESC, uhrzeit DESC, id DESC
            LIMIT 20
        """).fetchall()

    return render_template(
        "index.html",
        version=VERSION,
        felder=FELDER,
        werte=werte,
        fehler=fehler,
        gespeichert=gespeichert,
        korrigiert=korrigiert,
        eintraege=eintraege,
    )


@app.route("/export/csv")
def export_csv():
    """Messwerte mit verständlichen Spaltenüberschriften exportieren."""
    with verbinden() as db:
        eintraege = db.execute("""
            SELECT * FROM messwerte
            ORDER BY datum, uhrzeit, id
        """).fetchall()

    ausgabe = io.StringIO(newline="")
    writer = csv.writer(ausgabe, delimiter=";", lineterminator="\n")

    spalten = [
        ("id", "ID"),
        ("datum", "Datum"),
        ("uhrzeit", "Uhrzeit"),
    ] + [
        (name, f"{name} [{einheit}]")
        for name, _, einheit in FELDER
    ]

    writer.writerow([titel for _, titel in spalten])

    for eintrag in eintraege:
        writer.writerow([eintrag[name] for name, _ in spalten])

    datei = io.BytesIO(ausgabe.getvalue().encode("utf-8-sig"))
    datei.seek(0)

    return send_file(
        datei,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name="waermedaten.csv",
    )


@app.route("/export/sqlite")
def export_sqlite():
    """Konsistenten Snapshot der gesamten SQLite-Datenbank herunterladen."""
    temp = tempfile.NamedTemporaryFile(
        prefix="heizungsdaten_",
        suffix=".db",
        delete=False,
    )
    temp_path = temp.name
    temp.close()

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as quelle:
            with sqlite3.connect(temp_path) as ziel:
                quelle.backup(ziel)

        antwort = send_file(
            temp_path,
            mimetype="application/vnd.sqlite3",
            as_attachment=True,
            download_name="heizungsdaten.db",
        )
        antwort.call_on_close(
            lambda: os.path.exists(temp_path)
            and os.unlink(temp_path)
        )
        return antwort

    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


init_db()

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
