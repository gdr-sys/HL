"""Ricerca di ffmpeg e del modello vocale, sia da sorgente sia da programma installato."""

import os
import shutil
import sys
from pathlib import Path


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def find_binary(name: str) -> str:
    exe = name + (".exe" if os.name == "nt" else "")
    base = resource_dir()
    for folder in (
        base / "ffmpeg",
        base / "build_res" / "ffmpeg",
        Path(sys.executable).parent / "ffmpeg",
    ):
        candidate = folder / exe
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"{name} non trovato. Reinstalla il programma oppure installa ffmpeg."
    )


def find_vosk_model():
    """Cartella del modello vocale italiano, oppure None."""
    env = os.environ.get("RUGBY_VOSK_MODEL")
    if env and Path(env).is_dir():
        return env
    base = resource_dir()
    for models in (base / "models", base / "build_res" / "models"):
        if models.is_dir():
            for p in sorted(models.iterdir()):
                if p.is_dir() and (p / "am").exists():
                    return str(p)
    return None
