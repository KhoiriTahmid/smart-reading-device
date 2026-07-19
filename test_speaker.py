"""
Standalone speaker test - no encoder/GPIO dependency.
Run directly: python3 test_speaker.py
"""
import subprocess
import sys
import time

DEVICE = "plughw:2,0"  # match your speaker's card,device — see list_devices() below


def list_devices() -> None:
    """List available ALSA playback devices so you can confirm the right card/device index."""
    print("=== Available playback devices (aplay -l) ===")
    subprocess.run(["aplay", "-l"])
    print()


def test_tone(duration_s: int = 2, freq: int = 440) -> None:
    """Generate and play a pure test tone using speaker-test (no file needed)."""
    print(f"Playing {freq}Hz test tone for {duration_s}s on {DEVICE} ...")
    try:
        subprocess.run(
            ["speaker-test", "-D", DEVICE, "-t", "sine", "-f", str(freq), "-l", "1"],
            timeout=duration_s,
        )
    except subprocess.TimeoutExpired:
        pass  # expected — speaker-test runs until killed
    print("Tone test done.\n")


def test_wav(path: str, volume: int = 80) -> None:
    print(f"Playing WAV: {path} at volume={volume}")
    cmd = ["aplay", "-q", "-D", DEVICE, path]
    try:
        subprocess.run(cmd, check=True)
        print("WAV playback OK\n")
    except Exception as e:
        print(f"WAV playback FAILED: {e}\n")


def test_mp3(path: str, volume: int = 80) -> None:
    scale = int(volume / 100 * 32768)
    print(f"Playing MP3: {path} at volume={volume} (scale={scale})")
    cmd = ["mpg123", "-q", "--scale", str(scale), "-a", DEVICE, path]
    try:
        subprocess.run(cmd, check=True)
        print("MP3 playback OK\n")
    except Exception as e:
        print(f"MP3 playback FAILED: {e}\n")


def test_volume_sweep(path: str, ext: str = "wav") -> None:
    """Play the same sound at a few volume levels to sanity-check scaling."""
    for vol in [20, 50, 80, 100]:
        print(f"--- Volume {vol} ---")
        if ext == "wav":
            test_wav(path, vol)
        else:
            test_mp3(path, vol)
        time.sleep(0.5)


if __name__ == "__main__":
    list_devices()

    # 1. Basic tone test — confirms wiring/amp/speaker hardware works at all,
    #    independent of your mp3/wav files or volume-scaling code.
    test_tone(duration_s=2, freq=440)

    # 2. Test with an actual file from your project (adjust path as needed)
    # test_wav("sounds/beep_up.wav")
    # test_mp3("sounds/id/start_scan.mp3")

    # 3. Test volume scaling behavior
    # test_volume_sweep("sounds/beep_up.wav")