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
    run_flake8()
    run_tests()
    build_web()
    run_pyinstaller()

if __name__ == "__main__":
    main()
