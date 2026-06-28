from pathlib import Path
import unittest


class UiTextContractTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.main_text = (root / "main.py").read_text(encoding="utf-8")
        self.readme_text = (root / "README.md").read_text(encoding="utf-8")

    def test_live_verlauf_removed_in_favor_of_hrv_trace(self):
        self.assertNotIn("Live-Verlauf", self.main_text)
        self.assertNotIn("BPM und Feedback-Score", self.main_text)
        self.assertIn("HRV-Spur", self.main_text)
        self.assertIn("HRV-Amplitude", self.main_text)

    def test_default_menu_is_reduced(self):
        self.assertNotIn('menu_bar.addMenu("Feedback")', self.main_text)
        self.assertNotIn('menu_bar.addMenu("Werkzeuge")', self.main_text)
        self.assertIn('menu_bar.addMenu("Start")', self.main_text)
        self.assertIn('menu_bar.addMenu("Sitzung")', self.main_text)
        self.assertIn('menu_bar.addMenu("Gerät")', self.main_text)
        self.assertIn('menu_bar.addMenu("Ansicht")', self.main_text)
        self.assertIn('menu_bar.addMenu("Auswertung")', self.main_text)
        self.assertIn('menu_bar.addMenu("Hilfe")', self.main_text)
        self.assertIn('help_menu.addMenu("Expertenbereich")', self.main_text)

    def test_sensor_preparation_is_primary_language(self):
        self.assertIn("Sensor vorbereiten", self.main_text)
        self.assertIn("Ein Hauptsignal", self.readme_text)
        self.assertIn("Ein Hauptweg", self.readme_text)

    def test_training_surface_uses_one_signal_language(self):
        self.assertNotIn("Feedback-Score", self.main_text)
        self.assertNotIn("HRV-Score", self.main_text)
        self.assertNotIn("adaptive Schwelle", self.main_text)
        self.assertIn("HRV-Amplitude", self.main_text)
        self.assertIn("Stabile Phasen", self.main_text)


if __name__ == "__main__":
    unittest.main()
