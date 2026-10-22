"""Wrapper attorno a ffmpeg/ffprobe: lettura, audio, fotogrammi, montaggio."""

import json
import os
import subprocess
from collections import deque

from .paths import find_binary

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd):
    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_NOWIN,
    )


def probe_duration(video) -> float:
    r = _run([find_binary("ffprobe"), "-v", "error", "-show_entries",
              "format=duration", "-of", "json", str(video)])
    if r.returncode != 0:
        raise RuntimeError("Impossibile leggere il video: "
                           + r.stderr.decode(errors="replace")[-300:])
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (KeyError, ValueError):
        raise RuntimeError("Impossibile leggere la durata del video.")


def has_audio(video) -> bool:
    r = _run([find_binary("ffprobe"), "-v", "error", "-select_streams", "a",
              "-show_entries", "stream=index", "-of", "csv=p=0", str(video)])
    return r.returncode == 0 and bool(r.stdout.strip())


def run_with_progress(cmd, total_seconds, callback=None):
    """Esegue ffmpeg leggendo l'avanzamento. Il callback riceve una frazione 0..1.

    Se il callback solleva un'eccezione (es. Cancelled) ffmpeg viene fermato.
    """
    full = [cmd[0], "-progress", "pipe:1", "-nostats", "-loglevel", "error"] + cmd[1:]
    p = subprocess.Popen(
        full, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        creationflags=_NOWIN,
    )
    tail = deque(maxlen=30)
    try:
        for line in p.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    sec = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                if callback and total_seconds:
                    callback(max(0.0, min(1.0, sec / total_seconds)))
            elif "=" not in line or line.startswith("["):
                tail.append(line)
        rc = p.wait()
    except BaseException:
        p.kill()
        p.wait()
        raise
    if rc != 0:
        raise RuntimeError("ffmpeg ha dato errore:\n" + "\n".join(tail))


def extract_audio_raw(video, out_raw, total_seconds, callback=None):
    """Audio mono 16 kHz, 16 bit, senza intestazione."""
    cmd = [find_binary("ffmpeg"), "-y", "-hide_banner", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", str(out_raw)]
    run_with_progress(cmd, total_seconds, callback)


def extract_frame(video, t, out_png, width=480) -> bool:
    cmd = [find_binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
           "-vf", f"scale={width}:-2", str(out_png)]
    r = _run(cmd)
    return r.returncode == 0 and os.path.exists(out_png)


def export_montage(video, ranges, out, *, fade=0.25, crf=18, preview=False,
                   progress=None):
    """Taglia gli intervalli (start, end) e li unisce in un unico video.

    Un solo passaggio di ffmpeg: ogni clip ha una breve dissolvenza da/verso nero.
    In modalita' anteprima la qualita' e' bassa e il file e' molto piu' veloce da creare.
    """
    ranges = [(float(s), float(e)) for s, e in ranges if e - s > 0.5]
    if not ranges:
        raise ValueError("Nessuna clip da esportare.")
    audio = has_audio(video)
    inputs, parts, labels = [], [], []
    for i, (s, e) in enumerate(ranges):
        d = e - s
        f = min(fade, d / 4)
        inputs += ["-ss", f"{s:.3f}", "-t", f"{d:.3f}", "-i", str(video)]
        v = (f"[{i}:v:0]setpts=PTS-STARTPTS,"
             f"fade=t=in:st=0:d={f:.3f},fade=t=out:st={d - f:.3f}:d={f:.3f}")
        if preview:
            v += ",scale=-2:480"
        v += f",format=yuv420p[v{i}]"
        parts.append(v)
        label = f"[v{i}]"
        if audio:
            parts.append(
                f"[{i}:a:0]asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={f:.3f},afade=t=out:st={d - f:.3f}:d={f:.3f}[a{i}]")
            label += f"[a{i}]"
        labels.append(label)
    n = len(ranges)
    concat = "".join(labels) + f"concat=n={n}:v=1:a={1 if audio else 0}[outv]"
    if audio:
        concat += "[outa]"
    cmd = [find_binary("ffmpeg"), "-y", "-hide_banner", *inputs,
           "-filter_complex", ";".join(parts + [concat]), "-map", "[outv]"]
    if audio:
        cmd += ["-map", "[outa]"]
    cmd += ["-c:v", "libx264",
            "-preset", "ultrafast" if preview else "medium",
            "-crf", "28" if preview else str(crf)]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k" if preview else "192k"]
    cmd += ["-movflags", "+faststart", str(out)]
    total = sum(e - s for s, e in ranges)
    run_with_progress(cmd, total, progress)
