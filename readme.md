# Categories
![Hauptfenster](screenshots/screenshot.png)

**Categories** ist eine grafische Anwendung für GNOME/Linux, mit der sich Kontakte anhand ihrer vCard-Kategorien filtern und bearbeiten lassen. Zudem wird das Senden von Emails an die gefilterten Kontakte vorebreitet.

Die Idee zu diesem Projekt entstand aus dem Wunsch, nicht für verschiedene Anwendungen eigene Emailverteilerlisten anlegen zu müssen, welche sich oft schlecht synchronisieren lassen und auch gut gepflegt sein müssen. Zudem lässt sich bei einer alternativen Organisation der Kontakte in verschiedenen Adressbüchern nur eine eindimensionale Gruppierung realisieren. 

Die Anwendung greift auf die Kontaktadressbücher des **Evolution Data Server (EDS)** zu. Sie richtet sich an Nutzerinnen und Nutzer, die ihre Kontakte bereits über GNOME, Evolution oder kompatible Adressbuchquellen verwalten und diese anhand von Kategorien organisieren möchten.

**Categories** versteht sich nicht als Adressbuch, weshalb über die vCard-Kategorien ("categories") hinaus keine Bearbeitung von Kontakten möglich sein wird. Auch eine Dublettensuche wird nicht zur Verfügung gestellt.   

## Funktionen

- **Kontakte anzeigen:** Kontakte aus den verfügbaren EDS-Adressbüchern laden und alphabetisch sortiert anzeigen.
- **Nach Kategorien filtern:** Kontakte anhand ihrer vCard-Kategorien suchen und eingrenzen.
- **Kategorien verknüpfen:** Mehrere ausgewählte Kategorien über ODER- beziehungsweise UND-Verknüpfungen kombinieren.
- **Erweiterte Filter:** Eigene Filterausdrücke mit `AND`, `OR`, `NOT` und Klammern formulieren.
- **Kategorien bearbeiten:** Kategorien bei ausgewählten Kontakten hinzufügen, entfernen und neu anlegen.
- **Änderungen speichern:** Bearbeitete Kategorien in die jeweiligen Adressbücher zurückschreiben.
- **E-Mails adressieren:** E-Mails an ausgewählte Kontakte vorbereiten beziehungsweise adressieren.

## Voraussetzungen

Categories benötigt eine Linux-Umgebung mit den folgenden Komponenten:

- Python 3
- GTK 4
- libadwaita
- PyGObject (`gi`)
- Evolution Data Server einschließlich der Python-Introspektionsschnittstellen
- Eingerichtete und zugängliche Kontaktadressbücher im Evolution Data Server

Die genaue Verfügbarkeit der benötigten Pakete hängt von der verwendeten Linux-Distribution ab.

## Installation und Start

Categories wird zunächst direkt aus dem Quellcode ausgeführt. Ein distributionsübergreifendes Installationspaket ist derzeit nicht enthalten.

### 1. Repository herunterladen

Lade das Repository über GitHub herunter und entpacke es. Alternativ kannst du das Repository mit Git klonen:

```bash
git clone https://github.com/chcervus/Categories.git
cd Categories
```

### 2. Abhängigkeiten installieren

Installiere Python 3, GTK 4, libadwaita, PyGObject und die benötigten Evolution-Data-Server-Komponenten über die Paketverwaltung deiner Distribution.

### 3. Anwendung starten

Starte die Anwendung aus dem Projektverzeichnis:

```bash
python3 categories-frontend.py
```

Auf Fedora kann dafür beispielsweise der folgende Befehl verwendet werden:

```bash
/usr/bin/python3 categories-frontend.py
```

Die Anwendung benötigt Zugriff auf den Evolution Data Server und die dort eingerichteten Adressbücher.

## Projektstruktur

- `categories-frontend.py` enthält die grafische Benutzeroberfläche und die Anwendungslogik.
- `kontakt_backend.py` enthält die Funktionen für den Zugriff auf Kontakte und Kategorien sowie die Filterauswertung.
- `data/icons/` enthält das Anwendungsicon für die GNOME-Integration.

## Lizenz

Categories wird unter der **GNU General Public License v3.0 or later (GPL-3.0-or-later)** veröffentlicht.

Der vollständige Lizenztext befindet sich in der Datei `LICENSE`.

## Entwicklungsstatus

Categories befindet sich in Entwicklung. Die Anwendung wird zunächst als Quellcode veröffentlicht. Installation und Ausführung erfolgen vorerst manuell.

**Fehlerberichte, Verbesserungsvorschläge und Beiträge sind willkommen.** Das Projekt befindet sich in der **Testphase**

### To do:
- [ ] Verbesserungen an der Oberfläche: Filter-, Selektierinformationen besser anordnen
- [ ] Symbole einfügen 
- [ ] Hovereffekt korrigieren (Rechtecke erscheinen)
- [ ] Speicherprobleme testen
- [ ] Language - Pack einrichten

### Bemerkung zu KI

Die Anwendung wurde mit Unterstützung von LLMs erstellt. Diese dienen mir als Werkzeuge beim Programmieren. 
Die Unterstützung umfasste insbesondere:

- Erklärungen zu Python, GTK und Evolution Data Server (EDS)  
- Unterstützung bei der Fehlersuche
- Vrbesserung und Erweiterung der Filterlogik
- Unterstützung bei der Gestaltung des Speichervorgangs, insbesondere bei Versionsprüfungen, Hintergrundthreads und der Rückmeldung an die GTK-Oberfläche
- Überlegungen zur Fehlerbehandlung und zum Schutz personenbezogener Kontaktdaten

Die Vorschläge wurden im Zusammenhang mit dem bestehenden Code geprüft und schrittweise übernommen oder angepasst. 

Die Ideen, die Gestaltung und der Aufbau des Projekts liegen in meiner Verantwortung.


