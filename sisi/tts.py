"""Озвучка відповідей. Зараз — Edge TTS (нейроголоси Microsoft, безкоштовно, потрібен інтернет).
Голос, швидкість і висота — у налаштуваннях. Пізніше сюди ж підключимо кращий емоційний голос."""
import asyncio
import queue
import re
import threading

import edge_tts
import miniaudio
import numpy as np
import sounddevice as sd

from . import settings
from .store import log_action

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")
_URL = re.compile(r"https?://\S+")


def clean_for_speech(text: str) -> str:
    text = _URL.sub("посилання", text)
    text = re.sub(r"[`*_#>|\[\]]", "", text)
    text = _EMOJI.sub("", text)
    text = text.replace("))", "").replace("((", "")
    return " ".join(text.split())


class TTS:
    """Два потоки: синтез іде наперед (поки грає перша бульбашка, друга вже готується),
    програвач грає готові шматки один за одним — без пауз між бульбашками."""

    def __init__(self):
        self._q = queue.Queue()       # текст -> синтез
        self._play_q = queue.Queue()  # готовий звук -> програвач
        self._gen = 0  # номер «покоління»: stop() скасовує все, що було в черзі
        threading.Thread(target=self._loop, daemon=True, name="sisi-tts").start()
        threading.Thread(target=self._player, daemon=True, name="sisi-tts-play").start()

    def say(self, text: str):
        if settings.get("paused") or not settings.get("tts"):
            return
        clean = clean_for_speech(text)
        if clean:
            self._q.put((self._gen, clean))

    def stop(self):
        self._gen += 1
        sd.stop()

    async def _synth(self, text):
        comm = edge_tts.Communicate(text, settings.get("tts_voice"),
                                    rate=settings.get("tts_rate"), pitch=settings.get("tts_pitch"))
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        return bytes(buf)

    def _loop(self):
        while True:
            gen, text = self._q.get()
            if gen != self._gen:
                continue
            try:
                mp3 = asyncio.run(self._synth(text))
                if gen != self._gen or not mp3:
                    continue
                dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16)
                audio = np.array(dec.samples, dtype=np.int16).reshape(-1, dec.nchannels)
                self._play_q.put((gen, audio, dec.sample_rate))
            except Exception as e:  # noqa: BLE001
                log_action("tts_error", str(e)[:200])

    def _player(self):
        while True:
            gen, audio, rate = self._play_q.get()
            if gen != self._gen:
                continue
            try:
                sd.play(audio, rate)
                sd.wait()
            except Exception as e:  # noqa: BLE001
                log_action("tts_error", str(e)[:200])
