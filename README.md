# HRV Biofeedback

Lokale Windows-Desktop-App für HRV-Biofeedback mit Mindfield eSense Pulse oder einem kompatiblen BLE-Herzfrequenzgerät.

## Stand: v0.35-startup-menu-bugfix

Diese Version konsolidiert den aktuellen Stand mit gezieltem Frontend- und Backend-Feinschliff. Die App bleibt bei der stabilen PySide6-/pyqtgraph-Basis, schützt den reduzierten Trainingsraum und macht BLE-Paketverarbeitung, Graph-Darstellung und No-Data-Abbruch robuster. Der Ablauf bleibt: **Sensor vorbereiten → HRV-Amplitude trainieren → kurz nachbereiten**.

## Leitprinzipien

- **Ein Hauptsignal:** HRV-Amplitude. Der Kreis folgt diesem Signal; andere Werte stabilisieren oder dokumentieren nur im Hintergrund.
- **Ein Hauptweg:** Vorbereitung, Training, Nachbereitung.
- **Ein klares Feedback:** grüner Kreis + eine HRV-Spur, ohne konkurrierende Score-Anzeigen.
- **Expertentiefe bei Bedarf:** Diagnose, Logs, Rohdaten, Metadaten, Modellwerte und Supportpakete liegen im Hintergrund.
- **Wertfreie Sprache:** Beobachtung, Wahlmöglichkeiten und kleine nächste Schritte statt Leistungslabels.

## Startup- und Menü-Bugfix in v0.35

- behoben: App-Start brach ab, weil der Menüpunkt **Dashboard zurücksetzen** auf eine fehlende Methode zeigte
- wiederhergestellt: Menüziele für Sitzungsordner, Datenordner, Logdatei, Debugordner, Windows-Einstellungen, Display-Info und Tastenkürzel
- **Dashboard zurücksetzen** setzt nur Ansichts-/Layoutzustände zurück; Sitzungen, Logs und BLE-Daten bleiben erhalten
- neuer statischer UI-Startvertragstest schützt Menüaktionen vor fehlenden Methoden

## Konsolidierung und Bugfixes in v0.34

- `ui_components.py` enthält wiederverwendbare UI-Bausteine; `main.py` bleibt stärker Workflow-orientiert.
- `hrv_ble_state.py` trennt sichtbar zwischen „verbunden“, „GATT geprüft“, „warte auf RR“ und „RR aktiv“.
- `hrv_product_contract.py` dokumentiert den sichtbaren Produktkern: ein Signal, drei Phasen, Expertentiefe nur bei Bedarf.
- `hrv_adaptive_ui.py` steuert die adaptive Sichtbarkeit: Kreis als Primärfeedback, HRV-Spur als Kontext, kurze Hinweise als Orientierung und Kernzahlen nur bei Bedarf.
- `hrv_guided_session.py` plant den nächsten kleinen Schritt: Sensor vorbereiten, RR-Signal reparieren, ruhiger Einstieg mit Baseline oder direktes Training.
- `hrv_evidence.py` übersetzt aktuelle HRV-/HRVB-Evidenz in Produktregeln: RR-Qualität vor Interpretation, kurze wiederholbare Übungsfenster, keine Diagnosen, 0.1-Hz-/RF-Information nur als optionaler Kontext.
- `hrv_ui_capabilities.py` erkennt vorhandene und optionale Bibliotheken lokal und ordnet sie nach Nutzen, Risiko und Integrationsentscheidung.
- `hrv_visual_feedback.py` erzeugt eine ruhigere, display-only HRV-Spur mit Glättung und stabiler Y-Skalierung; Rohdaten und Exporte bleiben unverändert.
- `hrv_interaction_design.py` bewertet die aktuelle sensorische/kognitive Last und steuert reduzierte Bewegung, Detailsichtbarkeit, Graph-Kontext und nächste kleine Schritte.
- Backend-Bugfix: BLE-RR-Werte werden vor Zustandswechseln und Zählern defensiv gefiltert; leere Pakete zählen nicht mehr als BPM-only.
- Frontend-Bugfix: HRV-Spur und Y-Skalierung werden beim Sitzungsstart und beim Umschalten der ruhigen Spur sauber zurückgesetzt.
- Frontend-Bugfix: Stop ohne Daten führt wieder eindeutig in die Vorbereitung zurück und leert Graph-/Timerzustand.
- Frontend-Robustheit: Der Feedbackkreis klemmt nicht-finite Werte ab, damit fehlerhafte Zwischenwerte kein Zeichnen unterbrechen.
- Der Selbstcheck ist bewusst auf drei sichtbare Skalen reduziert. Die Exportlogik hält das Schema stabil.
- Nachbereitung bleibt kurz: Kerndaten, optionaler Selbstcheck, optionale Beobachtung, kleiner Transfer und konservative Evidenzhinweise.

## Enthalten

- Drei exklusive Hauptansichten: **Vorbereitung**, **Training**, **Nachbereitung**
- Vorbereitung mit zentralem Button **Sensor vorbereiten**
- kurzer Selbstcheck vor/nach dem Training mit drei sichtbaren 0-10-Skalen
- Lernfokus als optionaler Aufmerksamkeitsrahmen
- adaptiver Sitzungsplan: verbindet Signalstatus, Selbstcheck und letzte Sitzung, ohne ein zweites Trainingsziel zu erzeugen
- Evidenzrahmen aus aktuellen HRV-/HRVB-Arbeiten: transparente Messqualität, kurze Praxisfenster, vorsichtige medizinisch-psychologische Interpretation
- Training als reduzierter Fokusraum
- grüner Kreis als positive Rückmeldung über HRV-Amplitude
- genau ein Graph: **HRV-Spur** für HRV-Amplitude im 60-s-Fenster
- optionale **Ruhige HRV-Spur**: visuelle Glättung und stabilere Skala, ohne Messdaten zu verändern
- Option **Reduzierte Bewegung**: konservative Bewegungs-/Animationspolitik für einen ruhigeren Windows-Trainingsraum
- Expertenbereich **Bibliotheken & UX-Potenzial** mit lokalem Capability-Scan
- Expertenbereich **Interaktionsdesign & Adaptivität** mit aktueller Komplementaritäts- und Belastungspolitik
- adaptive Detailschicht: HRV-Amplitude, Signalqualität und Herzrate erscheinen auf Wunsch oder bei Signalproblemen
- Nachbereitung mit Kurzrückblick, Selbstcheck, Reflexionsnotiz und Transferidee
- BLE-/RR-Diagnostik, Supportpaket, Logs und Debugdaten im Expertenbereich
- CSV-, Metadaten-, Segment- und Reflexionsexport bleiben erhalten
- Produktkern-Vertrag, BLE-State-Machine, adaptive UI-Policy und wiederverwendbare UI-Komponenten reduzieren Kopplung und schützen die Trainingsoberfläche


## Aktuelle Evidenzschicht

Die App speichert eine auditable Evidenzschicht in Metadaten und Reflexionen. Eingearbeitet sind unter anderem:

- HR/HRV-Publikationsleitlinien 2024: Messmethode, Kontext, Artefaktregeln und Interpretationsgrenzen dokumentieren.
- Remote-HRVB-Metaanalysen 2025: kurze, wiederholbare Praxisfenster und klare Bildschirmrückmeldung unterstützen Adhärenz; Stressbefunde bleiben vorsichtig zu interpretieren.
- Umbrella-Review 2025 zu HRV und psychischen Störungen: HRV nicht als Diagnose- oder Symptommarker in der App verwenden.
- Große HRVB-App-Daten 2025 und RF-vs.-0.1-Hz-RCT 2026: 0.1-Hz-/Resonanzinformationen sind relevant, werden aber nicht als verpflichtendes sichtbares Ziel eingeführt.

## Installation mit Mini Anaconda / Conda

```bash
conda create -n hrv-biofeedback python=3.13
conda activate hrv-biofeedback
pip install -r requirements.txt
python main.py
```

## Tests

```bash
python -m py_compile main.py ui_components.py hrv_core.py hrv_sem.py hrv_diagnostics.py hrv_windows.py hrv_security.py hrv_ble_strategy.py hrv_psychology.py hrv_adaptation.py hrv_ble_state.py hrv_product_contract.py hrv_adaptive_ui.py hrv_guided_session.py hrv_evidence.py hrv_ui_capabilities.py hrv_visual_feedback.py hrv_interaction_design.py
python -m unittest discover -s tests -v
```

## Empfohlener Ablauf

### 1. Vorbereitung

1. eSense Pulse anlegen.
2. **Sensor vorbereiten** klicken.
3. Warten, bis RR-Daten aktiv sind.
4. Optional Selbstcheck und Lernfokus setzen.
5. Den vorgeschlagenen Sitzungsplan prüfen und Training starten.

### 2. Training

- Der Kreis reagiert auf die individuell normalisierte HRV-Amplitude.
- Die HRV-Spur zeigt nur HRV-Amplitude.
- Kleine Hinweise erscheinen nur, wenn sie unmittelbar nützlich sind; der adaptive Sitzungsplan verändert Vorbereitung und Nachbereitung, nicht das Hauptfeedbacksignal.
- Kernzahlen bleiben standardmäßig ausgeblendet und werden nur per **Details** oder bei Signalproblemen sichtbar.
- Technische Details, Schwellen und interne Modellwerte bleiben aus dem Trainingsraum heraus.

### 3. Nachbereitung

- Kurzrückblick ansehen.
- Optional Nachher-Selbstcheck ausfüllen.
- Optional notieren, was beobachtbar war.
- Einen kleinen 2-Minuten-Alltagsschritt festhalten.

## Menüstruktur

```text
Start
  Sensor vorbereiten
  Training starten
  Baseline überspringen
  Mock-Test
  Einführung
  Status & Diagnose

Sitzung
  Referenzmessung 10 min
  Training starten
  Baseline überspringen
  Pause/Fortsetzen
  Stop & Speichern
  Audio-Belohnung
  Kontext bearbeiten

Gerät
  Sensor vorbereiten
  Status & Diagnose
  Details: BLE-Scan, manuell verbinden, trennen, Bluetooth-Diagnose, Verbindungsassistent

Ansicht
  Vollbild
  Fokusansicht
  HRV-Spur anzeigen
  Ruhige HRV-Spur
  Reduzierte Bewegung
  Dashboard zurücksetzen
  Darstellung: Systemdesign, Darkmode, Lightmode

Auswertung
  Letzte Sitzungen
  Sitzungsordner öffnen
  Diagnosebericht speichern

Hilfe
  Einführung
  Verbindungsassistent
  Tastenkürzel
  Über HRV Biofeedback
  Expertenbereich: Selbsttest, Bibliotheken & UX-Potenzial, Interaktionsdesign & Adaptivität, Supportpaket, Logdatei, Debugordner, Datenordner, Display-/Windows-Einstellungen
```


## Interaktionsdesign und Feinschliff in v0.34

Die Interaktionsschicht fragt nicht, welche Information zusätzlich angezeigt werden könnte, sondern welche Information im jeweiligen Moment wirklich hilft. Daraus entstehen drei Profile:

- **Vorbereitung:** Wahl, Sensorprüfung und Start bleiben gebündelt.
- **Training:** Kreis zuerst; HRV-Spur, Hinweise und Details sind ergänzende Kanäle.
- **Nachbereitung:** kurze Integration, keine Analysezentrale.

Bei Signalproblemen darf die App vorübergehend technischer werden. Sobald RR-Daten und Signalqualität wieder passen, reduziert sie die Oberfläche erneut. Die Einstellung **Reduzierte Bewegung** ist standardmäßig aktiv und schützt den Trainingsraum vor unnötiger visueller Dynamik.

## Bibliotheksstrategie

Die Pflichtabhängigkeiten bleiben bewusst klein: PySide6, pyqtgraph, NumPy und bleak. Weitere Bibliotheken sind in `requirements-optional.txt` dokumentiert, aber nicht automatisch aktiviert.

- PySide6 bleibt die native Windows-GUI-Basis.
- pyqtgraph bleibt die Live-Plot-Basis für die eine HRV-Spur.
- qasync oder PySide6.QtAsyncio werden als späteres BLE-Controller-Experiment behandelt.
- NeuroKit2 und SciPy sind für Offline-/Research-Export sinnvoll, aber nicht für das Live-Feedbacksignal.
- Fluent-Widget-Bibliotheken werden wegen Lizenz-/Kompatibilitätsfragen nicht automatisch integriert; ihre Designprinzipien werden vorsichtig nachgebaut.
- DearPyGui, Flet und NiceGUI bleiben Prototyp-/Laborkandidaten, nicht Hauptapp.

## Bluetooth-Hinweise

- Die App sucht den eSense Pulse direkt über BLE und bevorzugt Geräte mit Heart-Rate-Service.
- Für HRV werden echte RR-Intervalle benötigt; BPM-only wird nicht künstlich in HRV umgerechnet.
- Falls RR-Daten fehlen: andere Apps/Smartphones trennen, Kontakt prüfen, Sensor kurz neu aktivieren und erneut **Sensor vorbereiten** starten.
- Diagnoseberichte erklären verständlich, ob Sensor, GATT-Service, RR-Daten oder Windows-Bluetooth betroffen sind.

## Datenhaltung

Standardpfad:

```text
~/Documents/HRV Biofeedback/
  sessions/
  debug/
  logs/
```

Sitzungen bleiben lokal. Debug- und Supportpakete werden redaktiert, bevor sie weitergegeben werden.
