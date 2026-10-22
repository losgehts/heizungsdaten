# Anleitung: Wärmedaten-App auf dem Raspberry Pi Zero installieren

Diese Anleitung beschreibt die Installation der Flask-Anwendung auf einem Raspberry Pi Zero mit Raspberry Pi OS Lite.

Voraussetzungen:
- SSH-Zugriff auf den Raspberry Pi
- Raspberry Pi OS Lite
- Netzwerkverbindung über Ethernet
- Die lokal entwickelte App mit `app.py` und `templates/index.html`

Die Anwendung verwendet Flask und SQLite. Die Datenbank wird automatisch angelegt, sobald die Anwendung startet.

## 1. Per SSH mit dem Raspberry Pi verbinden

Öffne auf deinem Linux-Mint-Rechner ein Terminal.
```bash
ssh BENUTZERNAME@192.168.1.50
```

## 2. System aktualisieren

Installiere zunächst die aktuellen Paketinformationen und Updates:

```bash
sudo apt update
sudo apt upgrade -y
```

## 3. Python und benötigte Pakete installieren

Installiere die benötigten Komponenten:

```bash
sudo apt install -y python3 python3-venv
```

## 4. Projektverzeichnis anlegen

```bash
mkdir -p ~/heizungsdaten/templates
cd ~/heizungsdaten
```

Die Verzeichnisstruktur sieht später so aus:

```text
~/heizungsdaten/
├── app.py
├── templates/
│   └── index.html
├── daten.db
└── .venv/
```

Die Dateien `app.py` und `templates/index.html` enthalten den entwickelten Anwendungscode. Die Datei `daten.db` wird automatisch erstellt.

## 5. Anwendung vom Linux-Mint-Rechner übertragen

Führe diese Befehle auf deinem Linux-Mint-Rechner aus, nicht innerhalb der SSH-Sitzung.

Wenn dein lokales Projekt unter `~/heizungsdaten/` liegt:

```bash
scp ~/heizungsdaten/app.py BENUTZERNAME@raspberrypi.local:~/heizungsdaten/
scp ~/heizungsdaten/templates/index.html BENUTZERNAME@raspberrypi.local:~/heizungsdaten/templates/
```

Ersetze `BENUTZERNAME` und gegebenenfalls `raspberrypi.local`.

### Optional: Bestehende Datenbank übertragen

Wenn du deine bereits erfassten Messwerte vom Entwicklungsrechner übernehmen möchtest, kopiere auch die Datenbank:

```bash
scp ~/heizungsdaten/daten.db BENUTZERNAME@raspberrypi.local:~/heizungsdaten/
```

**Wichtig:** Wenn auf dem Pi bereits eine Datenbank mit Messwerten existiert, überschreibe sie nicht versehentlich. Sichere die vorhandene Datei vorher.

Wenn du die App auf dem Pi ganz neu einrichten möchtest, überspringe diesen optionalen Schritt.

## 6. Python-Umgebung einrichten

Verbinde dich wieder per SSH mit dem Pi:

```bash
ssh BENUTZERNAME@raspberrypi.local
```

Wechsle in das Projektverzeichnis:

```bash
cd ~/heizungsdaten
```

Erstelle eine virtuelle Python-Umgebung:

```bash
python3 -m venv .venv
```

Installiere Flask:

```bash
.venv/bin/pip install Flask
```

## 7. Anwendung erstmals starten

Starte die App manuell:

```bash
cd ~/heizungsdaten
.venv/bin/python app.py
```

Beim ersten Start wird die SQLite-Datenbank automatisch angelegt, sofern sie noch nicht existiert.

Standardmäßig lauscht Flask auf Port 5000 und auf allen Netzwerkinterfaces, weil die Anwendung `host="0.0.0.0"` verwendet.

Beende den Testlauf mit `Ctrl+C`.

## 9. Automatischen Start mit systemd einrichten

Damit die App nach einem Neustart automatisch läuft, richten wir einen Systemdienst ein.

Öffne auf dem Pi eine neue Dienstdatei:

```bash
sudo nano /etc/systemd/system/heizungsdaten.service
```

Füge folgenden Inhalt ein. Ersetze `BENUTZERNAME` durch deinen tatsächlichen Linux-Benutzernamen:

```ini
[Unit]
Description=heizungsdaten Flask Anwendung
After=network.target

[Service]
Type=simple
User=BENUTZERNAME
WorkingDirectory=/home/BENUTZERNAME/heizungsdaten
ExecStart=/home/BENUTZERNAME/heizungsdaten/.venv/bin/python /home/BENUTZERNAME/heizungsdaten/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Speichern und schließen:

Lade die Dienstdefinition neu:

```bash
sudo systemctl daemon-reload
```

Aktiviere den automatischen Start:

```bash
sudo systemctl enable heizungsdaten.service
```

Starte den Dienst:

```bash
sudo systemctl start heizungsdaten.service
```

Prüfe den Status:

```bash
sudo systemctl status heizungsdaten.service
```

Wenn der Dienst erfolgreich läuft, sollte der Status `active (running)` angezeigt werden.

## 10. Protokolle ansehen

Falls die Anwendung nicht startet oder Fehler auftreten:

```bash
sudo journalctl -u heizungsdaten.service -n 100 --no-pager
```

Die laufenden Protokolle kannst du so verfolgen:

```bash
sudo journalctl -u heizungsdaten.service -f
```

Beende die Live-Anzeige mit `Ctrl+C`.

## 11. Datenbank und Exporte prüfen

Die Datenbank liegt hier:

```text
/home/BENUTZERNAME/heizungsdaten/daten.db
```

Sie enthält:
- `messwerte`: alle gespeicherten Messungen
- `spalten_info`: die Beschreibung der Spalten mit Bedeutung und Einheit

Auf der Webseite stehen die beiden Exportfunktionen zur Verfügung:
- CSV für LibreOffice Calc
- SQLite für eine vollständige Datenbanksicherung oder Weiterverarbeitung

Die App verwendet einen konsistenten SQLite-Datenbank-Snapshot für den Datenbankdownload.

## 12. Datenbank regelmäßig sichern

Eine SQLite-Datenbank ist nur eine Datei. Trotzdem solltest du regelmäßig eine Kopie auf einem anderen Gerät speichern.

Für eine manuelle Sicherung auf deinem Linux-Mint-Rechner:

```bash
scp BENUTZERNAME@raspberrypi.local:~/heizungsdaten/daten.db ~/heizungsdaten-sicherung.db
```

## 13. Anwendung aktualisieren

Wenn du später den Code auf Linux Mint änderst, übertrage die geänderten Dateien erneut:

```bash
scp ~/heizungsdaten/app.py BENUTZERNAME@raspberrypi.local:~/heizungsdaten/
scp ~/heizungsdaten/templates/index.html BENUTZERNAME@raspberrypi.local:~/heizungsdaten/templates/
```

Starte danach den Dienst auf dem Pi neu:

```bash
sudo systemctl restart heizungsdaten.service
```

Prüfe anschließend:

```bash
sudo systemctl status heizungsdaten.service
```

**Achtung:** Übertrage nicht bei jeder Codeänderung unüberlegt die lokale `daten.db`. Sonst könntest du die inzwischen auf dem Pi gespeicherten Messwerte überschreiben.

## 14. Sicherheitshinweise

- Die Anwendung ist für den Zugriff im heimischen Netzwerk vorgesehen.
- Leite Port 5000 nicht im Router ins Internet weiter.
- Der eingebaute Flask-Entwicklungsserver eignet sich für Tests und einen kleinen privaten Prototyp. Für einen langfristigen Dauerbetrieb sollte die App auf einen produktionsgeeigneten WSGI-Server umgestellt werden, beispielsweise Waitress oder Gunicorn, soweit für dein Betriebssystem verfügbar.
- Die automatische Zählerkorrektur und Plausibilitätsprüfungen bleiben Bestandteil der Anwendung.
- Sichere die Datenbank regelmäßig außerhalb des Raspberry Pi.

## 15. Kurze Checkliste

- [ ] SSH-Zugriff funktioniert
- [ ] Python und `python3-venv` sind installiert
- [ ] `app.py` wurde übertragen
- [ ] `templates/index.html` wurde übertragen
- [ ] Virtuelle Umgebung und Flask sind eingerichtet
- [ ] App startet manuell
- [ ] Webseite ist vom Smartphone erreichbar
- [ ] CSV-Export funktioniert
- [ ] SQLite-Export funktioniert
- [ ] systemd-Dienst startet automatisch
- [ ] Datenbank wird regelmäßig gesichert

Damit läuft deine Wärmedaten-App auf dem Raspberry Pi Zero und ist von Laptop und Smartphone im heimischen Netzwerk erreichbar.
