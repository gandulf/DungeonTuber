import subprocess
import sys
import os

def run_flake8():

    try:
        subprocess.run(
            [sys.executable, "-m", "flake8"],
            check=True,
        )
        print("\n[OK] Flake8 completed")
    except subprocess.CalledProcessError:
        print("\n[FEHLER] Flake8 ist fehlgeschlagen.")
        sys.exit(1)



def compile_translations():
    """Kompiliert alle .po Dateien zu .mo Dateien vor dem Build."""
    print("--- Schritt 1: Dynamische Übersetzungssuche ---")

    locales_dir = "locales"

    if not os.path.exists(locales_dir):
        print(f" [!] Hinweis: Ordner '{locales_dir}' nicht gefunden. Überspringe...")
        return

    # Liste alle Unterordner im locales-Verzeichnis auf
    found_languages = [f for f in os.listdir(locales_dir) if os.path.isdir(os.path.join(locales_dir, f))]

    if not found_languages:
        print(" [!] Keine Sprachordner in 'locales' gefunden.")
        return

    for lang in found_languages:
        po_path = os.path.join("locales", lang, "LC_MESSAGES", "DungeonTuber.po")
        mo_path = os.path.join("locales", lang, "LC_MESSAGES", "DungeonTuber.mo")

        if os.path.exists(po_path):
            try:
                # Führt den msgfmt Befehl aus
                subprocess.run(['msgfmt', '-o', mo_path, po_path], check=True)
                print(f" [OK] {lang} erfolgreich kompiliert.")
            except subprocess.CalledProcessError:
                print(f" [FEHLER] Syntaxfehler in {po_path}.")
                sys.exit(1)
            except FileNotFoundError:
                print(" [FEHLER] 'msgfmt' nicht gefunden. Bitte gettext-tools installieren.")
                sys.exit(1)
        else:
            print(f" [INFO] Übersprungen: {po_path} nicht gefunden.")

def build_web():
    """Baut das Web-Frontend (web/dist) fuer die Desktop-/Server-Variante."""
    print("\n--- Web-Frontend wird gebaut ---")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    try:
        subprocess.run([npm, "--prefix", "web", "ci"], check=True)
        subprocess.run([npm, "--prefix", "web", "run", "build"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n[FEHLER] Web-Build ist fehlgeschlagen (ist Node.js installiert?).")
        sys.exit(1)


def run_tests():
    try:
        subprocess.run([sys.executable, "-m", "pytest", "-q"], check=True)
    except subprocess.CalledProcessError:
        print("\n[FEHLER] Tests sind fehlgeschlagen.")
        sys.exit(1)


def run_pyinstaller(spec_file: str = "DungeonTuber.spec"):
    """Startet den PyInstaller Build-Prozess."""
    print("\n--- Schritt 2: PyInstaller Build wird gestartet ---")

    if not os.path.exists(spec_file):
        print(f" [FEHLER] {spec_file} wurde nicht gefunden!")
        sys.exit(1)

    # Befehl: pyinstaller DungeonTuber.spec
    build_cmd = ["pyinstaller", "--noconfirm", spec_file]

    try:
        subprocess.run(build_cmd, check=True)
        print("\n[FERTIG] Build erfolgreich abgeschlossen!")
    except subprocess.CalledProcessError:
        print("\n[FEHLER] PyInstaller-Build ist fehlgeschlagen.")
        sys.exit(1)

def main():
    compile_translations()
    run_flake8()
    run_tests()
    build_web()
    run_pyinstaller()

if __name__ == "__main__":
    main()
