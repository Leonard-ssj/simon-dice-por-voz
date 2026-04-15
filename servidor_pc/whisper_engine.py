# ============================================================
# whisper_engine.py — Pipeline de audio + Whisper
#
# Encapsula el mismo pipeline probado en test_hardware/test_whisper.py:
#   1. HPF 80Hz    — elimina DC bias del MAX4466
#   2. LPF 3400Hz  — banda de voz telefónica
#   3. noisereduce — sustracción espectral (prop=0.55)
#   4. Normaliza   — lleva el pico al 90%
#   5. Resample    — 8kHz → 16kHz (Whisper requiere 16kHz)
#   6. Whisper     — transcripción en español con initial_prompt del vocab
#
# Uso:
#   engine = WhisperEngine()
#   engine.cargar()                          # carga el modelo (~5-8s)
#   texto, comando = engine.transcribir(pcm_bytes)
# ============================================================

import os
import time
import wave
import numpy as np
from scipy import signal as sp_signal

try:
    import noisereduce as nr
    _TIENE_NR = True
except ImportError:
    _TIENE_NR = False
    print("[WhisperEngine] WARN: noisereduce no instalado → pip install noisereduce")

from config import SAMPLE_RATE, WHISPER_SR, WHISPER_MODEL, DEBUG
from validador import texto_a_comando


# ─── Prompt de contexto para Whisper ─────────────────────────────────────────
# IGUAL al de test_hardware/test_whisper.py — el que demostró funcionar bien
# con el MAX4466 real (ADC analógico, SNR bajo).
#
# Por qué el prompt largo ayuda:
#   - Le dice a Whisper exactamente qué esperar → reduce confusión fonética.
#   - Los ejemplos de pronunciación ('a-sul' es azul) anclan palabras difíciles.
#   - "Transcribe solo esa palabra" impide que invente frases completas.
#
# Por qué era peligroso antes (ya no lo es):
#   - Antes el botón GPIO0 grababa en boot / durante TTS → audio malo →
#     Whisper no entendía nada → se "escapaba" al prompt y generaba "Subtítulos".
#   - Ahora el botón está eliminado y _reservar_ventana_tts() bloquea el PTT
#     mientras el narrador habla → el audio llega limpio → el prompt ayuda.
#   - Además, _ALUCINACIONES_CONOCIDAS filtra cualquier caso residual.
#
# Adaptado de test_whisper.py: usa "empieza/para" en vez de "start/stop"
# porque eso es lo que los jugadores dicen naturalmente en español.
_INITIAL_PROMPT = (
    "Juego Simon Dice. El jugador dice exactamente UNA palabra del vocabulario en español: "
    "rojo, verde, azul, amarillo, empieza, para, pausa, repite, reiniciar, "
    "arriba, abajo, izquierda, derecha, sí, no. "
    "Ejemplos de pronunciación: "
    "'a-sul' es azul. 'ro-jo' es rojo. 'ber-de' es verde. 'a-ma-ri-yo' es amarillo. "
    "'em-pie-za' es empieza. 'pa-ra' es para. "
    "'a-rri-ba' es arriba. 'a-ba-jo' es abajo. "
    "'iz-kier-da' es izquierda. 're-i-ni-siar' es reiniciar. "
    "Transcribe solo esa palabra, sin puntuación, sin mayúsculas extra: "
    "rojo verde azul amarillo empieza para pausa repite reiniciar "
    "arriba abajo izquierda derecha sí no."
)

# ─── Alucinaciones conocidas de Whisper ──────────────────────────────────────
# Segunda línea de defensa: si a pesar del buen audio Whisper genera uno de
# estos textos (bug conocido del modelo en español), lo descartamos.
# Con audio limpio y temperature=0.0 esto casi nunca ocurre, pero es un seguro.
_ALUCINACIONES_CONOCIDAS = [
    "amara.org",
    "subtítulos",
    "subtitulos",
    "gracias por ver",
    "suscríbete",
    "suscribete",
    "hasta la próxima",
    "hasta la proxima",
    "translated by",
    "traducido por",
    "community subtitles",
    "next episode",
]


class WhisperEngine:
    """
    Pipeline de audio limpieza + transcripción con Whisper.
    Thread-safe: usa un lock para que solo una transcripción corra a la vez.
    """

    def __init__(self):
        self._modelo  = None
        self._listo   = False
        import threading
        self._lock = threading.Lock()

    # ── Carga del modelo ──────────────────────────────────────────────────────

    def cargar(self, modelo: str = None) -> bool:
        """
        Carga el modelo Whisper en memoria.
        La primera vez descarga el modelo (~244MB para 'small').
        Retorna True si se cargó correctamente.
        """
        modelo = modelo or WHISPER_MODEL
        print(f"[Whisper] Cargando modelo '{modelo}'...")
        print(f"          (primera vez: descarga ~244MB a ~/.cache/whisper/)")
        try:
            import whisper
            t0 = time.time()
            self._modelo = whisper.load_model(modelo)
            self._listo  = True
            print(f"[Whisper] Modelo '{modelo}' listo en {time.time()-t0:.1f}s")
            return True
        except Exception as e:
            print(f"[Whisper] ERROR al cargar: {e}")
            self._listo = False
            return False

    @property
    def listo(self) -> bool:
        return self._listo

    # ── Pipeline de preprocesamiento ─────────────────────────────────────────

    def preprocesar(self, pcm_bytes: bytes) -> np.ndarray:
        """
        Convierte bytes PCM raw (int16 LE, 8kHz) en array float32 16kHz
        listo para Whisper.

        Capas:
          1. int16 → float32 normalizado [-1, 1]
          2. HPF 80Hz  (scipy filtfilt, fase cero — sin distorsión de fase)
          3. LPF 3400Hz (scipy filtfilt, fase cero)
          4. noisereduce estaticionario (sustracción espectral, prop=0.55)
          5. Normalización al 90% del pico
          6. Resample 8kHz → 16kHz
        """
        # Capa 0: bytes → float32 [-1, 1]
        muestras = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Capas 1+2: HPF 80Hz + LPF 3400Hz (scipy filtfilt — fase cero)
        # Aunque el firmware ya aplica biquad HPF+LPF, REPETIRLOS aquí con
        # filtfilt (fase cero) es necesario porque:
        #   a) El biquad del firmware es causal → introduce distorsión de fase.
        #      filtfilt la corrige al reprocesar.
        #   b) noisereduce necesita audio ya band-limitado para estimar el perfil
        #      de ruido correctamente. Sin esto, incluye frecuencias fuera de la
        #      banda de voz en su estimación y suprime de forma errática.
        # Esta combinación (firmware biquad + Python filtfilt) es exactamente
        # lo que tenía el test_hardware que funcionó bien.
        b, a     = sp_signal.butter(2, 80.0 / (SAMPLE_RATE / 2.0), btype="high")
        muestras = sp_signal.filtfilt(b, a, muestras)
        b, a     = sp_signal.butter(2, 3400.0 / (SAMPLE_RATE / 2.0), btype="low")
        muestras = sp_signal.filtfilt(b, a, muestras)
        if DEBUG:
            print("  [Audio] Capa 1+2 OK: HPF 80Hz + LPF 3400Hz (filtfilt, fase cero)")

        # Capa 3: Sustracción espectral
        # Valores idénticos al test_hardware/test_whisper.py que funcionó:
        #   prop_decrease=0.55: elimina 55% del ruido (0.80 borraba consonantes)
        #   n_std_thresh_stationary=2.0: conservador → preserva sibilantes (S,Z,CH,R)
        # IMPORTANTE: umbral 2.0 (no 1.5). Con 1.5 noisereduce era más agresivo
        # y borraba parte de la señal de voz del MAX4466, degradando el SNR.
        if _TIENE_NR:
            muestras = nr.reduce_noise(
                y=muestras,
                sr=SAMPLE_RATE,
                stationary=True,
                prop_decrease=0.55,
                n_std_thresh_stationary=2.0,   # igual que test_whisper.py — no 1.5
            )
            if DEBUG:
                print("  [Audio] Capa 3 OK: noisereduce espectral (prop=0.55)")
        else:
            if DEBUG:
                print("  [Audio] Capa 3 OMITIDA: noisereduce no instalado")

        # Capa 4: Normalización al 90% del pico
        pico = float(np.max(np.abs(muestras)))
        if pico > 0.001:
            muestras = muestras * (0.90 / pico)
        if DEBUG:
            print(f"  [Audio] Capa 4 OK: normalizado (pico anterior={pico:.4f})")

        # Capa 5: Resample 8kHz → 16kHz
        n_destino    = int(len(muestras) * WHISPER_SR / SAMPLE_RATE)
        muestras_16k = sp_signal.resample(muestras, n_destino)
        if DEBUG:
            print(f"  [Audio] Capa 5 OK: resample → {WHISPER_SR}Hz ({len(muestras_16k)} muestras)")

        return muestras_16k.astype(np.float32)

    # ── Transcripción ─────────────────────────────────────────────────────────

    def transcribir(self, pcm_bytes: bytes, guardar_wav: bool = False) -> tuple[str, str]:
        """
        Recibe bytes PCM int16 LE @ 8kHz del ESP32.
        Aplica el pipeline de audio y transcribe con Whisper.

        Retorna (texto_raw, comando_canonico).
        texto_raw  = transcripción cruda de Whisper (ej: "rojo")
        comando    = palabra del vocabulario (ej: "ROJO") o "DESCONOCIDO"
        """
        if not self._listo or self._modelo is None:
            return "", "DESCONOCIDO"

        if len(pcm_bytes) < SAMPLE_RATE * 2 // 4:   # < 0.25s de audio
            if DEBUG:
                print(f"  [Whisper] Audio demasiado corto ({len(pcm_bytes)} bytes), ignorando.")
            return "", "DESCONOCIDO"

        # ── Detección de silencio / alucinación preventiva ────────────────────
        # Si el micrófono capturó solo ruido de fondo (botón mantenido sin hablar),
        # Whisper alucina repitiendo el initial_prompt o genera "AAAA...".
        # Calculamos el RMS ANTES del pipeline: el ADC del MAX4466 en silencio
        # genera ruido ~0.002–0.004 RMS (float32 normalizado). Voz normal ≥ 0.015.
        muestras_raw = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(muestras_raw ** 2)))
        if DEBUG:
            print(f"  [Whisper] RMS audio crudo: {rms:.5f}")
        if rms < 0.008:
            print(f"[Whisper] Silencio detectado (RMS={rms:.5f} < 0.008) — omitiendo Whisper.")
            return "", "DESCONOCIDO"

        # ── Planitud espectral (Spectral Flatness) ─────────────────────────────
        # El ruido de fondo es espectralmente plano (flatness ≈ 1.0).
        # La voz humana tiene picos formánticos que bajan la flatness.
        # UMBRAL 0.72: el MAX4466 con voz débil/distante puede dar flatness 0.5-0.65.
        # Solo bloqueamos ruido puro (ventiladores, AC) que suele estar > 0.72.
        _seg = muestras_raw[len(muestras_raw)//4 : 3*len(muestras_raw)//4]
        _espectro = np.abs(np.fft.rfft(_seg)) + 1e-9
        _geo = float(np.exp(np.mean(np.log(_espectro))))
        _ari = float(np.mean(_espectro))
        flatness = _geo / _ari
        if DEBUG:
            print(f"  [Whisper] Flatness espectral: {flatness:.3f}  (< 0.72 → Whisper | > 0.72 → ruido puro)")
        if flatness > 0.72:
            print(f"[Whisper] Ruido puro detectado (flatness={flatness:.3f} > 0.72) — omitiendo Whisper.")
            return "", "DESCONOCIDO"

        # Preprocesar audio
        audio_16k = self.preprocesar(pcm_bytes)

        # Guardar WAVs de depuración (siempre en DEBUG — para escuchar qué llegó a Whisper)
        if guardar_wav or DEBUG:
            self._guardar_wavs(pcm_bytes, audio_16k)

        # Transcribir
        t0 = time.time()
        try:
            with self._lock:
                resultado = self._modelo.transcribe(
                    audio_16k,
                    language="es",
                    fp16=False,                          # CPU no soporta fp16 (True si hay GPU NVIDIA)
                    condition_on_previous_text=False,
                    temperature=0.0,                     # DETERMINÍSTICO — no alucina vocales cortas.
                                                         # Con tupla (0.0,0.2,0.4) Whisper reintentaba
                                                         # con temp alta y generaba "ah","e","y" en ruido.
                    no_speech_threshold=0.50,            # igual que test_whisper.py (default de Whisper).
                                                         # 0.40 era demasiado estricto: rechazaba voz
                                                         # del MAX4466 (SNR bajo) como "sin habla".
                                                         # temperature=0.0 evita alucinar con 0.50.
                    logprob_threshold=-0.8,              # igual que test_whisper.py — -1.0 era más
                                                         # permisivo pero el test usó -0.8 y funcionó
                    compression_ratio_threshold=2.4,     # descarta AAAA... (ratio muy alto = repetición)
                    initial_prompt=_INITIAL_PROMPT,      # vocabulario mínimo
                    beam_size=5,
                )
            texto_raw = resultado["text"].strip()
        except Exception as e:
            print(f"[Whisper] ERROR en transcripción: {e}")
            return "", "DESCONOCIDO"

        duracion = time.time() - t0
        print(f'[Whisper] ({duracion:.1f}s): "{texto_raw}"')

        # Rechazar alucinaciones conocidas antes de cualquier otro procesamiento.
        # Ocurren con audio corto/ruidoso: Whisper genera texto de subtítulos
        # o frases del propio prompt en vez de transcribir lo que se dijo.
        texto_lower = texto_raw.lower()
        for alu in _ALUCINACIONES_CONOCIDAS:
            if alu in texto_lower:
                print(f"[Whisper] Alucinación detectada ('{alu}') — descartando.")
                return "", "DESCONOCIDO"

        # Detectar alucinaciones de caracteres repetitivos (AAAA..., eeee..., etc.).
        # compression_ratio_threshold=2.4 debería atraparlas, pero a veces se escapan.
        # Si el texto tiene > 8 chars y ≤ 2 chars únicos (ignorando espacios y puntos)
        # es casi seguro una alucinación de Whisper, no habla real.
        if len(texto_raw) > 8:
            _solo_letras = texto_raw.lower().replace(" ", "").replace(".", "").replace(",", "")
            _chars_unicos = len(set(_solo_letras))
            if _chars_unicos <= 2:
                print(f"[Whisper] Alucinación repetitiva (chars únicos={_chars_unicos}) — descartando.")
                return "", "DESCONOCIDO"

        # Descartar outputs que son claramente ruido/respiración:
        # vocales sueltas ("a","e","o"), interjecciones cortísimas ("ah","uh","mm"),
        # o outputs de un solo token que no pertenecen al vocabulario.
        # Un comando válido mínimo tiene 2 caracteres (NO, SI).
        palabras_output = texto_raw.strip().split()
        if len(texto_raw.strip()) <= 2 and len(palabras_output) == 1:
            # Verificar si esa palabra corta está en el vocabulario (SI, NO)
            posible_cmd = texto_a_comando(texto_raw)
            if posible_cmd == "DESCONOCIDO":
                print(f"[Whisper] Descartado — output muy corto y no es vocabulario: '{texto_raw}'")
                return "", "DESCONOCIDO"

        # Convertir texto → comando canónico
        comando = texto_a_comando(texto_raw)
        print(f'[Whisper] → {comando}')

        return texto_raw, comando

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _guardar_wavs(self, pcm_bytes: bytes, audio_16k: np.ndarray) -> None:
        """
        Guarda los WAVs de debug en servidor_pc/ para escuchar qué llegó a Whisper.

        Archivos generados (se sobreescriben en cada grabación):
          debug_crudo_8k.wav      — audio tal como salió del ESP32 (8kHz int16)
          debug_procesado_16k.wav — audio después del pipeline, lo que escucha Whisper (16kHz)

        Abrir con cualquier reproductor (VLC, Windows Media Player, Audacity, etc.).
        """
        carpeta = os.path.dirname(os.path.abspath(__file__))
        try:
            # WAV crudo del ESP32 (8kHz int16)
            ruta_crudo = os.path.join(carpeta, "debug_crudo_8k.wav")
            with wave.open(ruta_crudo, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm_bytes)

            # WAV procesado que Whisper recibe (16kHz float32 → int16)
            ruta_proc = os.path.join(carpeta, "debug_procesado_16k.wav")
            muestras_int16 = np.clip(audio_16k * 32767, -32768, 32767).astype(np.int16)
            with wave.open(ruta_proc, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(WHISPER_SR)
                wf.writeframes(muestras_int16.tobytes())

            print(f"  [Audio] WAVs guardados → {ruta_crudo}")
            print(f"  [Audio]               → {ruta_proc}")
        except Exception as e:
            print(f"  [Audio] No se pudieron guardar WAVs: {e}")
