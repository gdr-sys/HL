import subprocess
import wave

import numpy as np
import pytest

SR = 16000
DURATION = 120


def _make_audio(path):
    rng = np.random.default_rng(0)
    n = DURATION * SR
    t = np.arange(n) / SR
    bg = np.convolve(rng.normal(0, 1, n), np.ones(8) / 8, mode="same") * 0.02

    def crowd(t0, t1, level):
        env = np.zeros(n)
        env[int(t0 * SR):int(t1 * SR)] = 1.0
        env = np.convolve(env, np.ones(SR // 2) / (SR // 2), mode="same")
        return np.convolve(rng.normal(0, 1, n), np.ones(4) / 4, mode="same") * level * env

    def whistle(t0, d):
        m = (t >= t0) & (t < t0 + d)
        sig = np.zeros(n)
        sig[m] = 0.4 * np.sin(2 * np.pi * 3200 * t[m] + 3 * np.sin(2 * np.pi * 35 * t[m]))
        return sig

    audio = bg + crowd(40, 48, 0.15) + crowd(92, 98, 0.10)
    for t0 in (18.0, 42.0, 90.0):
        audio = audio + whistle(t0, 0.8)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    wav = d / "audio.wav"
    mp4 = d / "match.mp4"
    _make_audio(wav)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={DURATION}",
         "-i", str(wav), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(mp4)],
        check=True)
    return mp4
