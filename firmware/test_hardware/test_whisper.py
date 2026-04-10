"""
test_whisper.py — Test 6: Reconocimiento de voz con Whisper.

Flujo:
  1. Carga el modelo Whisper base (una sola vez, ~10 segundos la primera vez)
  2. Conecta al ESP32 por Serial
  3. Envia '6' para iniciar el test en el firmware
  4. Espera AUDIO_START, recibe el audio PCM
  5. Pipeline de limpieza de audio:
       HPF 80Hz + LPF 3400Hz  (scipy)   — elimina DC y ruido fuera de banda de voz
       noisereduce stationary             — sustraccion espectral del ruido ADC
       Normalizacion al 90% del pico
       Resample 8kHz → 16kHz
  6. Ejecuta Whisper en español
  7. Devuelve DETECTED:<PALABRA> al ESP32 para mostrarlo en el OLED

Uso:
  cd firmware/test_hardware
  python test_whisper.py

Requisitos:
  pip install pyserial openai-whisper numpy scipy noisereduce

Opcional (mejor calidad, mas lento):
  pip install deepfilternet        <- red neuronal de supresion de ruido
  Luego poner USE_DEEPFILTER = True abajo.

IMPORTANTE: cerrar el Serial Monitor del Arduino IDE antes de correr este script.
"""

import serial
import serial.tools.list_ports
import wave
import numpy as np
from scipy import signal as sp_signal
from difflib import SequenceMatcher
import whisper
import sys
import os
import time

# noisereduce — sustraccion espectral (ya instalado)
try:
    import noisereduce as nr
    TIENE_NOISEREDUCE = True
except ImportError:
    TIENE_NOISEREDUCE = False
    print('[WARN] noisereduce no instalado. Corre: pip install noisereduce')

# DeepFilterNet — supresion neuronal (opcional, mejor calidad)
# Para activar: pip install deepfilternet  y poner USE_DEEPFILTER = True
USE_DEEPFILTER = False
_df_enhance   = None   # funcion enhance (se carga una vez al inicio)
_df_model     = None   # modelo DeepFilterNet
_df_state     = None   # estado del modelo

# ─── Configuracion ──────────────────────────────────────────────────────────────
BAUD_RATE    = 921600
SAMPLE_RATE  = 8000          # debe coincidir con el firmware
WHISPER_SR   = 16000         # Whisper siempre necesita 16kHz internamente
OUTPUT_FILE  = "grabacion_test6.wav"
TIMEOUT_AUDIO   = 30         # segundos maximos recibiendo bytes de audio
TIMEOUT_DETECTA = 120        # segundos maximos esperando AUDIO_START (PTT: usuario tarda en presionar)

# Vocabulario del proyecto (vocabulario.h)
VOCABULARIO = [
    'ROJO', 'VERDE', 'AZUL', 'AMARILLO',
    'START', 'STOP', 'PAUSA', 'REPITE', 'REINICIAR',
    'ARRIBA', 'ABAJO', 'IZQUIERDA', 'DERECHA',
    'SI', 'NO',
]

# Correcciones comunes de Whisper en español (fonética → palabra del vocab)
# AZUL: fonéticamente corta (2 sílabas: A-ZUL) → Whisper la confunde con otras.
# Se agregan muchas variantes de cómo Whisper transcribe ese sonido.
# Variantes fonoticas en español de como Whisper puede transcribir cada palabra.
# Causas comunes: confusion b/v, j/h, ll/y, z/s, rr/r, acento, puntuacion suelta.
CORRECCIONES = {
    # ROJO: la J en español suena como H fuerte → Whisper a veces pone "roho", "roxo"
    'ROJO':      ['ROJO', 'ROXO', 'ROJA', 'ROHO', 'RROJO', 'ROGO',
                  'ROJI', 'ROCO', 'ROJO.', 'RO HO', 'ROJO,'],

    # VERDE: confusion b/v muy comun en español → "berde", "verdi"
    'VERDE':     ['VERDE', 'BERDE', 'VERDI', 'BERDI', 'VERD', 'BERD',
                  'VERDE.', 'VERDES', 'VÉRDE', 'BÉRDÉ'],

    # AZUL: palabra corta, 2 silabas A-ZUL → Whisper la confunde con frecuencia
    # z/s en español → "asul", "asuul"; a veces agrega tilde "azúl"
    'AZUL':      ['AZUL', 'ASUL', 'ASÚL', 'AZÚL', 'AZUUL', 'AZULL',
                  'A ZUL', 'A-ZUL', 'AZOL', 'ATZUL', 'ASUUL',
                  'AÇUL', 'AZÚL.', 'AZUL.', 'A SUL', 'ASOOL',
                  'HASUL', 'HAZUL', 'ADUL', 'AZAL'],

    # AMARILLO: ll/y → "amarilo", "amariya"; acento "amaríllo"
    'AMARILLO':  ['AMARILLO', 'AMARILO', 'AMARILLLO', 'AMARILLA',
                  'AMARIYA', 'AMARILIA', 'AMARÍLIA', 'AMARÍLLO',
                  'AMARILO.', 'AMARIYO', 'AMARIILLO'],

    # START / STOP: anglicismos — Whisper puede ponerlos en español o en inglés
    # Aqui solo variantes en español de como se oiria pronunciado en español
    'START':     ['START', 'ESTART', 'ESTARA', 'ESTÁRT', 'ESTÁR',
                  'ESTAL', 'INICIA', 'EMPIEZA', 'COMIENZA'],

    'STOP':      ['STOP', 'ESTOP', 'ESTOB', 'ESTOPE', 'PARA', 'PÁRATE',
                  'TOPE', 'ESTOPH', 'STOP.'],

    # PAUSA: au → "pauca"; p/b → "bausa"
    'PAUSA':     ['PAUSA', 'PAUCA', 'POSA', 'PAÚSA', 'BAUSA',
                  'PAWSA', 'PAUSA.', 'PAÚSA.', 'PAUZAR', 'PAUZA'],

    # REPITE: e final puede perderse → "repit"; acento → "répite"
    'REPITE':    ['REPITE', 'REPITA', 'REPIT', 'REPÍTE', 'RÉPITE',
                  'REPITEN', 'REPITI', 'REPITE.', 'REPITA.', 'REPITELO'],

    # REINICIAR: palabra larga, varios puntos de falla
    # rein → "rein", "reim"; ci → "si", "zi"; ar → "al"
    'REINICIAR': ['REINICIAR', 'REINICIA', 'RENICIA', 'REINISI',
                  'REINISIAR', 'REINISAR', 'REINIZIA', 'REINICEAR',
                  'REINICIAR.', 'RENISIAR', 'REINICYA', 'REINIZIO'],

    # ARRIBA: rr → r simple; b/v → "arriva"
    'ARRIBA':    ['ARRIBA', 'ARIBA', 'ARIVA', 'ARRIBA.', 'ARRIVA',
                  'ARRIBA,', 'ARIBA.', 'HARRIBA', 'ARRIBO'],

    # ABAJO: b/v → "avajo"; j/h → "abaho"
    'ABAJO':     ['ABAJO', 'AVAJO', 'ABAHO', 'ABAXO', 'AVAHO',
                  'ABAJO.', 'ABAHO.', 'HAVAJO', 'ABAXHO', 'AVAXO'],

    # IZQUIERDA: iz → "is", "es"; qu → "k", "c"; ie → "e"
    'IZQUIERDA': ['IZQUIERDA', 'ISQUIERDA', 'IZQUERDA', 'ESQUIERDA',
                  'ISKIERDA', 'IQUIERDA', 'IZQUIERDA.', 'ISKIERDA.',
                  'ESQUERDA', 'IZQUIERTA', 'ISQUERDA', 'ISCIERDA'],

    # DERECHA: ch → "c"; e final → "a"; acento
    'DERECHA':   ['DERECHA', 'DERECA', 'DERECHE', 'DERÉCHA',
                  'DERECHA.', 'DEREXA', 'DERESHA', 'DÉRECHA',
                  'DERECHE.', 'DERECHO', 'DERÉCHO'],

    # SI: palabra muy corta — Whisper puede transcribir como "sí", "sea", "ce"
    'SI':        ['SÍ', 'SI', 'SÍ.', 'SI.', 'SEA', 'CE', 'SY',
                  'SII', 'SÍI', 'CI', 'CHI'],

    # NO: corta pero difícil de confundir; posibles: "no.", "noo", "nou"
    'NO':        ['NO', 'NO.', 'NOO', 'NOU', 'NOH', 'NO,'],
}


# =============================================================================
#  Deteccion de puerto
# =============================================================================
def encontrar_puerto():
    puertos = serial.tools.list_ports.comports()
    candidatos = []
    for p in puertos:
        desc = (p.description or '').lower()
        if any(x in desc for x in ['cp210', 'ch340', 'ftdi', 'uart', 'usb serial', 'esp']):
            candidatos.append(p.device)
    if not candidatos:
        todos = [p.device for p in puertos]
        if not todos:
            print('[ERROR] No se encontro ningun puerto serial.')
            print('        Verifica que el ESP32 este conectado por USB.')
            sys.exit(1)
        return todos[0]
    return candidatos[0]


# =============================================================================
#  Pipeline de audio: filtros + normalizacion + resample a 16kHz
# =============================================================================
def preprocesar_audio(pcm_bytes: bytes) -> np.ndarray:
    """
    Convierte los bytes PCM raw (int16, 8kHz) en un array float32 a 16kHz
    listo para pasarle a Whisper, aplicando:
      1. HPF 80Hz   — elimina DC residual del MAX4466
      2. LPF 3400Hz — banda de voz telefonica, corta ruido ADC de alta frec.
      3. Normalizacion al 90% del pico (maximiza SNR sin saturar)
      4. Resample 8kHz → 16kHz (Whisper requiere 16kHz)
    """
    # PCM int16 → float32 normalizado a [-1.0, 1.0]
    muestras = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # ── CAPA 1: Filtros clasicos DSP (scipy, fase cero con filtfilt) ──────────
    # HPF 80Hz — elimina DC residual del MAX4466 y vibraciones de baja frec.
    b, a = sp_signal.butter(2, 80.0 / (SAMPLE_RATE / 2.0), btype='high')
    muestras = sp_signal.filtfilt(b, a, muestras)
    # LPF 3400Hz — banda de voz telefonica, corta ruido ADC de alta frecuencia
    b, a = sp_signal.butter(2, 3400.0 / (SAMPLE_RATE / 2.0), btype='low')
    muestras = sp_signal.filtfilt(b, a, muestras)
    print('  [AUDIO] Capa 1 OK: filtros HPF 80Hz + LPF 3400Hz aplicados')

    # ── CAPA 2: Sustraccion espectral del ruido ADC (noisereduce) ────────────
    # stationary=True: ruido ADC es constante → puede estimarse con precision
    # prop_decrease=0.55: elimina 55% del ruido (antes era 80% y cortaba consonantes)
    # n_std_thresh_stationary=2.0: umbral mas conservador → preserva Z,R,K,S,CH
    # Bajar prop_decrease es clave: las consonantes (IZQUIERDA, VERDE, etc.) viven
    # en alta frecuencia; con 0.80 se borraban y Whisper alucinaba.
    if TIENE_NOISEREDUCE:
        muestras = nr.reduce_noise(
            y=muestras,
            sr=SAMPLE_RATE,
            stationary=True,
            prop_decrease=0.55,
            n_std_thresh_stationary=2.0,
        )
        print('  [AUDIO] Capa 2 OK: noisereduce espectral aplicado (prop=0.55)')
    else:
        print('  [AUDIO] Capa 2 OMITIDA: noisereduce no instalado')

    # ── CAPA 3: Normalizacion al 90% del pico ────────────────────────────────
    # Maximiza el SNR antes de entregar a Whisper sin saturar
    pico = np.max(np.abs(muestras))
    if pico > 0.001:
        muestras = muestras * (0.90 / pico)
    print(f'  [AUDIO] Capa 3 OK: normalizado (pico anterior = {pico:.4f})')

    # ── CAPA 4: Resample 8kHz → 16kHz (Whisper requiere exactamente 16kHz) ──
    n_destino = int(len(muestras) * WHISPER_SR / SAMPLE_RATE)
    muestras_16k = sp_signal.resample(muestras, n_destino)
    print(f'  [AUDIO] Capa 4 OK: resample {SAMPLE_RATE}Hz → {WHISPER_SR}Hz ({len(muestras_16k)} muestras)')

    # ── CAPA 5 (opcional): Supresion neuronal DeepFilterNet ──────────────────
    # Red neuronal entrenada con miles de tipos de ruido real.
    # Para activar: pip install deepfilternet  y USE_DEEPFILTER = True arriba.
    if USE_DEEPFILTER and _df_model is not None:
        print('  [AUDIO] Capa 5: aplicando DeepFilterNet (red neuronal)...')
        try:
            import torch
            # DeepFilterNet trabaja a 48kHz internamente — resamplear, filtrar, volver
            n_48k      = int(len(muestras_16k) * 48000 / WHISPER_SR)
            audio_48k  = sp_signal.resample(muestras_16k, n_48k).astype(np.float32)
            tensor_48k = torch.from_numpy(audio_48k).unsqueeze(0)   # shape [1, N]
            enhanced   = _df_enhance(_df_model, _df_state, tensor_48k).squeeze().numpy()
            muestras_16k = sp_signal.resample(enhanced, len(muestras_16k)).astype(np.float32)
            print('  [AUDIO] Capa 5 OK: DeepFilterNet aplicado')
        except Exception as e:
            print(f'  [AUDIO] Capa 5 ERROR: {e} — continuando sin el')

    return muestras_16k.astype(np.float32)


# =============================================================================
#  Validacion: texto de Whisper → palabra del vocabulario
# =============================================================================
def buscar_en_vocabulario(texto: str) -> str:
    """
    Busca en el texto transcrito alguna palabra del vocabulario.
    Pasos:
      1. Coincidencia exacta (palabra del vocab contenida en el texto)
      2. Correcciones fonoticas comunes (variantes conocidas)
      3. Fuzzy matching para palabras cortas (<=6 chars): ayuda con AZUL, SI, NO, ROJO, STOP
    Retorna 'DESCONOCIDO' si no encuentra ninguna.
    """
    texto_up = texto.upper().strip()
    # Quitar puntuacion para no fallar por "AZUL." vs "AZUL"
    texto_limpio = ''.join(c if c.isalpha() or c == ' ' else ' ' for c in texto_up).strip()
    print(f'  [DEBUG] Texto Whisper: "{texto_up}"  →  limpio: "{texto_limpio}"')

    # Paso 1: coincidencia directa en el texto
    for palabra in VOCABULARIO:
        if palabra in texto_limpio or palabra in texto_up:
            return palabra

    # Paso 2: correcciones fonoticas
    for palabra, variantes in CORRECCIONES.items():
        for variante in variantes:
            v = variante.upper()
            if v in texto_up or v in texto_limpio:
                return palabra

    # Paso 3: fuzzy matching — util para palabras cortas que Whisper transcribe
    # con 1-2 caracteres distintos (AZUL → "ASUL", ROJO → "ROXO" etc.)
    # Solo aplicar cuando el texto es una palabra sola o casi (max 2 tokens)
    tokens = texto_limpio.split()
    if len(tokens) <= 2:
        mejor_palabra = None
        mejor_ratio = 0.0
        for token in tokens:
            for palabra in VOCABULARIO:
                # Para palabras cortas (<=6) el umbral es más bajo (0.70)
                # Para palabras largas se exige más similitud (0.82)
                umbral = 0.70 if len(palabra) <= 6 else 0.82
                ratio = SequenceMatcher(None, palabra, token).ratio()
                if ratio >= umbral and ratio > mejor_ratio:
                    mejor_ratio = ratio
                    mejor_palabra = palabra
        if mejor_palabra:
            print(f'  [DEBUG] Fuzzy match: "{texto_limpio}" → {mejor_palabra} (ratio={mejor_ratio:.2f})')
            return mejor_palabra

    return 'DESCONOCIDO'


# =============================================================================
#  Guardar WAV
# =============================================================================
def guardar_wav(datos_pcm: bytes, ruta: str):
    """Guarda bytes PCM raw int16 como WAV a SAMPLE_RATE (8kHz)."""
    with wave.open(ruta, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(datos_pcm)


def guardar_wav_float(muestras: np.ndarray, ruta: str, sample_rate: int):
    """Guarda array float32 [-1, 1] como WAV int16 al sample_rate indicado."""
    samples_int16 = np.clip(muestras * 32767, -32768, 32767).astype(np.int16)
    with wave.open(ruta, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples_int16.tobytes())


def abrir_archivo(ruta: str):
    """Abre un archivo con el programa predeterminado del sistema."""
    try:
        if sys.platform == 'win32':
            os.startfile(ruta)
        elif sys.platform == 'darwin':
            os.system(f'open "{ruta}"')
        else:
            os.system(f'xdg-open "{ruta}"')
    except Exception as e:
        print(f'  [WARN] No se pudo abrir automaticamente: {e}')


# =============================================================================
#  MAIN
# =============================================================================
def main():
    print('=' * 50)
    print('  TEST 6 — Reconocimiento de voz con Whisper')
    print('=' * 50)

    global _df_model, _df_state, _df_enhance

    # ── Cargar Whisper small (mejor que base, ~244MB, una sola vez) ──────────
    print('[INFO] Cargando modelo Whisper "small" (~244MB, solo la primera vez)...')
    print('       (Si es la primera vez puede tardar varios minutos en descargar)')
    t0 = time.time()
    modelo = whisper.load_model('small')
    print(f'[OK]   Whisper small listo en {time.time()-t0:.1f}s')

    # ── Cargar DeepFilterNet si esta activado ─────────────────────────────────
    if USE_DEEPFILTER:
        print('[INFO] Cargando DeepFilterNet (red neuronal de supresion de ruido)...')
        try:
            from df.enhance import enhance, init_df
            _df_enhance = enhance
            _df_model, _df_state, df_sr = init_df()
            print(f'[OK]   DeepFilterNet listo (sample_rate={df_sr}Hz)')
        except Exception as e:
            print(f'[WARN] DeepFilterNet no disponible: {e}')
            print('       Instala con: pip install deepfilternet')

    # Conectar al ESP32
    puerto = encontrar_puerto()
    print(f'[INFO] Conectando a {puerto} @ {BAUD_RATE} baud...')
    try:
        ser = serial.Serial(puerto, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f'[ERROR] No se pudo abrir {puerto}: {e}')
        print('        Cierra el Serial Monitor del Arduino IDE.')
        sys.exit(1)

    time.sleep(1.5)          # esperar reset del ESP32 al abrir puerto
    ser.reset_input_buffer()

    # Disparar Test 6 en el firmware
    print('[INFO] Enviando comando "6" al ESP32...')
    ser.write(b'6')
    time.sleep(0.3)

    # Enviar ENTER — señal de que Whisper ya cargo y Python esta listo
    time.sleep(0.5)
    print('[INFO] Enviando ENTER al ESP32 (Whisper listo)...')
    ser.write(b'\n')

    # Esperar a que el firmware este listo para grabar (buscar "READY_TO_RECORD")
    print('[INFO] Esperando que el firmware este listo...')
    t_espera = time.time()
    while True:
        if time.time() - t_espera > 15:
            print('[WARN] No llego READY_TO_RECORD, continuando de todas formas...')
            break
        try:
            linea = ser.readline().decode('latin-1', errors='replace').strip()
        except Exception:
            continue
        if linea:
            print(f'  ESP32: {linea}')
        if 'READY_TO_RECORD' in linea:
            break

    # PTT por teclado: ENTER para empezar a grabar
    print()
    print('=' * 50)
    input('  >>> Presiona ENTER para EMPEZAR a grabar... ')
    ser.write(b'R')   # Record start
    print('  >>> GRABANDO — habla ahora')
    print('=' * 50)

    # Esperar señal de que el firmware confirmo el inicio
    t_conf = time.time()
    while time.time() - t_conf < 3:
        try:
            linea = ser.readline().decode('latin-1', errors='replace').strip()
        except Exception:
            break
        if linea:
            print(f'  ESP32: {linea}')
        if 'RECORDING_START' in linea:
            break

    # PTT por teclado: ENTER para parar
    input('  >>> Presiona ENTER para PARAR la grabacion... ')
    ser.write(b'T')   # sTop
    print('[INFO] Grabacion detenida. Esperando audio...')

    # Esperar AUDIO_START:N (viene inmediatamente despues de 'T')
    total_bytes = None
    t_espera = time.time()

    while True:
        if time.time() - t_espera > TIMEOUT_DETECTA:
            print('[ERROR] Timeout esperando AUDIO_START.')
            ser.close(); sys.exit(1)
        try:
            linea = ser.readline().decode('latin-1', errors='replace').strip()
        except Exception:
            continue
        if linea:
            print(f'  ESP32: {linea}')
        if 'RECORDING_TOO_SHORT' in linea:
            print('[WARN] Grabacion demasiado corta. Vuelve a correr el script.')
            ser.close(); sys.exit(1)
        if linea.startswith('AUDIO_START:'):
            try:
                total_bytes = int(linea.split(':')[1])
                duracion = total_bytes / (SAMPLE_RATE * 2)
                print(f'[INFO] Recibiendo {total_bytes} bytes ({duracion:.1f}s, {SAMPLE_RATE}Hz)...')
                break
            except ValueError:
                pass

    # Recibir audio PCM
    datos = bytearray()
    leidos = 0
    t_audio = time.time()

    while leidos < total_bytes:
        faltante = total_bytes - leidos
        chunk = ser.read(min(faltante, 4096))
        if chunk:
            datos.extend(chunk)
            leidos += len(chunk)
            pct = leidos * 100 // total_bytes
            print(f'\r  Recibido: {leidos}/{total_bytes} bytes ({pct}%)   ', end='', flush=True)
        if time.time() - t_audio > TIMEOUT_AUDIO:
            print('\n[ERROR] Timeout leyendo datos de audio.')
            ser.close(); sys.exit(1)
    print()

    # Esperar AUDIO_END
    t_end = time.time()
    while time.time() - t_end < 5:
        linea = ser.readline().decode('latin-1', errors='replace').strip()
        if linea:
            print(f'  ESP32: {linea}')
        if 'AUDIO_END' in linea:
            break

    carpeta = os.path.dirname(os.path.abspath(__file__))

    # ── Guardar WAV crudo (lo que salio del ESP32, 8kHz) ─────────────────────
    ruta_crudo = os.path.join(carpeta, OUTPUT_FILE)
    guardar_wav(bytes(datos), ruta_crudo)
    duracion_real = len(datos) / (SAMPLE_RATE * 2)
    print(f'[INFO] WAV crudo guardado ({duracion_real:.1f}s, 8kHz): {ruta_crudo}')

    # ── Pipeline de limpieza de audio ────────────────────────────────────────
    print('[INFO] Aplicando pipeline de audio...')
    audio_16k = preprocesar_audio(bytes(datos))

    # ── Guardar WAV filtrado (lo que Whisper recibe, 16kHz) ──────────────────
    # Este es el archivo mas importante: es exactamente lo que Whisper escucha.
    ruta_filtrado = os.path.join(carpeta, 'grabacion_test6_whisper.wav')
    guardar_wav_float(audio_16k, ruta_filtrado, WHISPER_SR)
    print(f'[INFO] WAV filtrado guardado (16kHz, lo que Whisper escucha): {ruta_filtrado}')

    # ── Ejecutar Whisper small ────────────────────────────────────────────────
    print('[INFO] Ejecutando Whisper small en espanol...')
    print('       (en CPU tarda ~20-40s dependiendo de la duracion del audio)')
    t_w = time.time()
    # initial_prompt: guía al decoder de Whisper hacia nuestro vocabulario.
    # - Repetir cada palabra varias veces pesa más esos tokens internamente.
    # - Dar ejemplos fonéticos ayuda con palabras cortas (AZUL, SI, NO).
    # - "Una sola palabra" evita que invente frases completas.
    prompt_vocab = (
        "Juego Simon Dice. El jugador dice exactamente UNA palabra de este vocabulario en español: "
        "rojo, verde, azul, amarillo, start, stop, pausa, repite, reiniciar, "
        "arriba, abajo, izquierda, derecha, sí, no. "
        "Ejemplos de pronunciación: "
        "'a-sul' es azul. 'ro-jo' es rojo. 'ber-de' es verde. 'a-ma-ri-yo' es amarillo. "
        "'a-rri-ba' es arriba. 'a-ba-jo' es abajo. 'iz-kier-da' es izquierda. 're-i-ni-siar' es reiniciar. "
        "Transcribe solo esa palabra, sin puntuación, sin mayúsculas extra: "
        "rojo verde azul amarillo start stop pausa repite reiniciar arriba abajo izquierda derecha sí no."
    )

    resultado = modelo.transcribe(
        audio_16k,
        language='es',
        fp16=False,                       # CPU no soporta fp16
        condition_on_previous_text=False,
        temperature=0.0,                  # deterministico: sin aleatoriedad
        no_speech_threshold=0.5,          # sube el umbral: ignora silencios/ruido
        logprob_threshold=-0.8,           # descarta transcripciones de baja confianza
        initial_prompt=prompt_vocab,      # contexto del vocabulario → mucho mejor precision
        beam_size=5,                      # explora mas hipotesis antes de elegir
    )
    texto_raw = resultado['text'].strip()
    print(f'[OK]   Whisper ({time.time()-t_w:.1f}s): "{texto_raw}"')

    # ── Buscar en vocabulario ─────────────────────────────────────────────────
    detectado = buscar_en_vocabulario(texto_raw)
    print(f'[RESULT] Palabra detectada: {detectado}')
    print('=' * 50)

    # ── Enviar resultado al ESP32 ─────────────────────────────────────────────
    ser.write(f'DETECTED:{detectado}\n'.encode('utf-8'))
    print(f'[INFO] Enviado al ESP32: DETECTED:{detectado}')

    # ── Abrir el WAV filtrado para escuchar ───────────────────────────────────
    print(f'[INFO] Abriendo el audio que Whisper recibio: {ruta_filtrado}')
    abrir_archivo(ruta_filtrado)

    time.sleep(5)   # dar tiempo al firmware para mostrar el resultado en OLED
    ser.close()
    print('[INFO] Prueba completada. Para otra grabacion vuelve a correr el script.')


if __name__ == '__main__':
    main()
