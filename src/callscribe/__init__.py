"""CallScribe — local macOS call recorder + speaker-labeled transcript.

Flow: ``start`` spawns a detached dual-track recorder → on ``stop``, mixdown to
stereo ``call.wav`` (L=me / R=remote) → optional background ASR + pyannote
diarization → ``transcript.json`` / ``transcript.md``. Models run on-device;
only ``setup`` may use the network.
"""

__version__ = "0.1.0"
