# Simon Dice por Voz — Documentación Técnica

**Materia:** Sistemas Inteligentes
**Hardware:** ESP32-S3 (YD-ESP32-S3 en protoboard)
**Arquitectura:** Fase 1 — Prototipo con PC

---

## 1. Visión general

Simon Dice por Voz es un juego clásico de memoria controlado completamente por voz en español. El jugador escucha una secuencia de colores y debe repetirlos en orden usando solo su voz.

```
┌──────────────────────────────────────────────────────────────┐
│  ESP32-S3  (firmware/proyecto/proyecto.ino)                  │
│  • MAX4466: captura audio del jugador (ADC 8kHz)             │
│  • RGB WS2812B: muestra el color activo de la secuencia      │
│  • OLED SSD1306: muestra estado del juego                    │
│  • Botón GPIO0 (SW1): Push-To-Talk físico                    │
└──────────────────┬───────────────────────────────────────────┘
                   │ USB Serial 921600 baud
                   │ (audio PCM + comandos de texto)
┌──────────────────▼───────────────────────────────────────────┐
│  Python  (servidor_pc/servidor.py)                           │
│  • serial_bridge.py  → lee/escribe Serial del ESP32          │
│  • whisper_engine.py → pipeline audio + Whisper small        │
│  • juego_sim.py      → máquina de estados del juego          │
│  • ws_server.py      → WebSocket :8765 → panel web           │
│  • tts.py            → narrador TTS + tonos (laptop)         │
└──────────────────┬───────────────────────────────────────────┘
                   │ WebSocket ws://localhost:8765
┌──────────────────▼───────────────────────────────────────────┐
│  Next.js  (web-panel/)                                       │
│  • Muestra LEDs, secuencia, nivel, puntuación                │
│  • Log en tiempo real de todos los eventos                   │
│  • PTT por barra espaciadora → panel → WS → Python           │
└──────────────────────────────────────────────────────────────┘
```

**Principio de diseño clave:** El ESP32 es solo hardware. La lógica del juego vive en Python, lo que simplifica enormemente el firmware y permite iterar sin reflachar.

---

## 2. Hardware

### Pines (YD-ESP32-S3)

| Componente | Pin | Notas |
|---|---|---|
| MAX4466 OUT | GPIO4 (ADC1_CH3) | Micrófono analógico |
| OLED SDA | GPIO10 | I2C datos |
| OLED SCL | GPIO11 | I2C reloj |
| RGB WS2812B | GPIO48 | LED integrado en la placa |
| Botón PTT | GPIO0 (BOOT) | Activo LOW, pull-up interno |

### Configuración Arduino IDE

```
Board:            ESP32S3 Dev Module
PSRAM:            OPI PSRAM
Flash Size:       16MB (128Mb)
USB CDC on Boot:  Enabled
Upload Speed:     921600
```

### MAX4466 — Micrófono analógico

- Salida: señal AC centrada en VCC/2 (~1.65V)
- Ganancia: ajustable con potenciómetro (máximo recomendado)
- ADC del ESP32: 12-bit (0–4095), referencia 3.3V
- El bias de 1.65V se elimina en firmware restando 2048 a cada muestra

---

## 3. Firmware (ESP32)

### Lo que hace

El firmware maneja únicamente hardware:

1. Detecta PTT (botón físico GPIO0 o comando Serial 'R')
2. Captura audio del MAX4466 a 8kHz con filtros digitales biquad
3. Almacena en PSRAM (hasta 10s = 160KB)
4. Envía los bytes de audio al PC por Serial
5. Recibe comandos del PC y los ejecuta (LED, OLED)

### Por qué OVERSAMPLE=2 y no 4

Con `analogRead()` en ESP32-S3 cada lectura tarda ~40µs. A 8kHz el intervalo entre muestras es 125µs:

- `OVERSAMPLE=4`: 4 × 40µs = 160µs **>** 125µs → se supera el intervalo → tasa real ~6250Hz declarada como 8kHz → audio 1.28× acelerado = **efecto ardilla**
- `OVERSAMPLE=2`: 2 × 40µs = 80µs **<** 125µs → 45µs de margen → timing exacto, sin distorsión

### Filtros biquad en firmware

Butterworth 2do orden, Direct Form I, Fs=8kHz:

```
HPF @ 80Hz — elimina DC bias y vibraciones bajas
  B0= 0.9566  B1=-1.9131  B2= 0.9566
  A1=-1.9112  A2= 0.9150

LPF @ 3400Hz — banda de voz telefónica
  B0= 0.7158  B1= 1.4316  B2= 0.7158
  A1= 1.3490  A2= 0.5141
```

### Protocolo Serial (ESP32 ↔ PC)

**ESP32 → PC:**

| Mensaje | Significado |
|---|---|
| `READY` | Firmware inicializado |
| `PTT_START` | Grabación iniciada |
| `PTT_STOP` | Grabación detenida |
| `AUDIO_CORTO` | Grabación < 0.25s, descartada |
| `AUDIO_START:N` | Vienen N bytes PCM int16 LE 8kHz |
| `AUDIO_END` | Fin del paquete |

**PC → ESP32:**

| Mensaje | Significado |
|---|---|
| `R` | Iniciar grabación remota (spacebar) |
| `T` | Detener grabación remota |
| `LED:ROJO` / `LED:OFF` | Color del LED activo |
| `OLED:l1\|l2\|l3` | Texto en OLED (3 líneas) |

---

## 4. Pipeline de limpieza de audio (Python)

El audio del ESP32 tiene ruido residual del ADC. El servidor aplica 5 capas antes de entregar a Whisper:

```
[bytes PCM int16 LE @ 8kHz del ESP32]
  │
  ▼ int16 → float32 normalizado [-1.0, 1.0]
  │
  ▼ HPF 80Hz — scipy filtfilt (fase cero, sin distorsión)
  │   Elimina DC residual
  │
  ▼ LPF 3400Hz — scipy filtfilt (fase cero)
  │   Refuerza corte de alta frecuencia
  │
  ▼ noisereduce estatcionario
  │   prop_decrease=0.55 (reducir 55% del ruido)
  │   ⚠ NO usar >0.70: borra consonantes Z,K,R,S,CH
  │     → Whisper alucina ("¡Draje!", "¡Ni una ni una!")
  │
  ▼ Normalización al 90% del pico
  │   Maximiza SNR sin saturar
  │
  ▼ Resample 8kHz → 16kHz (scipy.signal.resample)
  │   Whisper requiere exactamente 16kHz

[np.ndarray float32 @ 16kHz] → Whisper
```

### Por qué prop_decrease=0.55 y no 0.80

Con 0.80 el filtro borraba las componentes espectrales de las consonantes fricativas:

- **Z** ("AZUL"): energía en ~3-5kHz → desaparecía → Whisper confundía con otra cosa
- **K** ("IZQUIERDA"): igual
- **S/CH** ("REINICIAR", "DERECHA"): igual

Con 0.55 se preserva suficiente espectro consonántico. El ruido residual no afecta tanto a Whisper como la falta de información.

---

## 5. Reconocimiento de voz — Whisper

### Qué es Whisper

Modelo de reconocimiento de voz de OpenAI entrenado con 680,000 horas de audio. Se ejecuta **localmente** (sin internet, sin API key, completamente gratis).

- **Modelo:** `small` (~244MB) — mejor balance calidad/velocidad en CPU
- **Tiempo:** 3-8s en CPU i5/i7
- **Idioma:** forzado a español (`language="es"`)

### Parámetros clave de transcripción

| Parámetro | Valor | Por qué |
|---|---|---|
| `temperature` | `0.0` | Determinístico — sin aleatoriedad en la elección |
| `no_speech_threshold` | `0.5` | Ignora segmentos de silencio/ruido |
| `logprob_threshold` | `-0.8` | Descarta transcripciones de baja confianza |
| `initial_prompt` | vocabulario | Guía al decoder hacia nuestras palabras |
| `beam_size` | `5` | Explora 5 hipótesis simultáneas antes de elegir |

### initial_prompt — cómo funciona

Whisper usa el prompt como "contexto previo de la conversación". Al listar el vocabulario, el decoder asigna mayor probabilidad a esas tokens durante beam search:

```
"Juego Simon Dice. El jugador dice exactamente UNA palabra:
rojo, verde, azul, amarillo, start, stop, pausa, repite...
Ejemplos: 'a-sul' es azul. 'ro-jo' es rojo..."
```

### ¿Se puede entrenar Whisper para este proyecto?

**Fine-tuning de Whisper:**
- Técnicamente posible, pero requiere GPU NVIDIA para entrenar (días en CPU)
- Necesita ~100-500 ejemplos por palabra
- El `initial_prompt` + tabla VARIANTES logra ~90% del beneficio sin entrenar

**Para Fase 2 (Edge Impulse):** se graban ~50 muestras por palabra y se entrena un modelo MFCC/red neuronal mucho más pequeño (~150KB) que corre en el ESP32 sin PC. Ese sí es el entrenamiento con datos propios.

### Validador — 4 pasos

```
Texto Whisper: "asul"
  │
  ▼ Paso 1: coincidencia exacta en vocabulario canónico
  │         "ASUL" no está → siguiente
  │
  ▼ Paso 2: frases de dos palabras ("otra vez" → REPITE)
  │         No aplica → siguiente
  │
  ▼ Paso 3: tabla VARIANTES (variantes fonéticas/naturales)
  │         "ASUL" está en VARIANTES["AZUL"] → ✓ AZUL
  │
  ▼ Paso 4: fuzzy matching (SequenceMatcher, umbral 0.70-0.82)
            Para variantes no previstas en la tabla

→ Resultado: "AZUL"
```

---

## 6. Lógica del juego

```
IDLE
  │  START (di "empieza")
  ▼
SHOWING_SEQUENCE  ← LEDs + TTS uno a uno
  │
  ▼
LISTENING         ← timer 30s, espera PTT del jugador
  │
  ▼
EVALUATING        ← timer pausado durante Whisper (~5s)
  │
  ├─ CORRECTO + fin secuencia  → CORRECT → LEVEL_UP → SHOWING_SEQUENCE
  ├─ CORRECTO + incompleta    → CORRECT → LISTENING (siguiente color)
  ├─ INCORRECTO               → WRONG → GAME_OVER
  └─ TIMEOUT                  → GAME_OVER

LISTENING → PAUSA (di "pausa")
PAUSA → LISTENING (di "empieza")
LISTENING → LISTENING (di "repite")
```

**Puntuación:** acierto de secuencia completa = `nivel_actual × 10 puntos`

### Por qué el timer se pausa durante Whisper

Sin la pausa, Whisper tarda 3-8s y ese tiempo se descuenta del timeout del jugador. Con la pausa, el timer solo cuenta el tiempo real que el jugador tarda en responder — no el tiempo de la máquina.

---

## 7. Protocolo WebSocket

**Servidor → Panel:**
```json
{"tipo": "ready"}
{"tipo": "state",    "estado": "LISTENING"}
{"tipo": "led",      "color": "ROJO"}
{"tipo": "sequence", "secuencia": ["ROJO","VERDE"]}
{"tipo": "expected", "esperado": "VERDE"}
{"tipo": "level",    "nivel": 3}
{"tipo": "score",    "puntuacion": 30}
{"tipo": "result",   "resultado": "CORRECT"}
{"tipo": "voz",      "texto": "rojo", "comando": "ROJO"}
{"tipo": "gameover"}
{"tipo": "log",      "mensaje": "..."}
```

**Panel → Servidor:**
```json
{"tipo": "control", "accion": "PTT_INICIO"}
{"tipo": "control", "accion": "PTT_FIN"}
{"tipo": "comando", "comando": "ROJO"}
```

---

## 8. Cómo instalar y correr

### Instalación

```bash
# Dependencias Python
cd servidor_pc
pip install -r requirements.txt

# Panel web
cd ../web-panel
npm install
```

### Flashear firmware

1. Abrir `firmware/proyecto/proyecto.ino` en Arduino IDE
2. Board: `ESP32S3 Dev Module` | PSRAM: `OPI PSRAM` | Flash: `16MB`
3. USB CDC on Boot: `Enabled`
4. Subir (→)

### Correr el juego

```bash
# Terminal 1
cd servidor_pc
python servidor.py

# Terminal 2
cd web-panel
npm run dev
```

Abrir **Chrome o Edge** en `http://localhost:3000`:

1. Seleccionar **"Simulador — WebSocket"**
2. Clic en **Conectar**
3. Presionar **ESPACIO** (o botón SW1) y decir **"empieza"**

### Cambiar puerto Serial si auto-detect falla

```python
# servidor_pc/config.py
SERIAL_PORT = "COM4"          # Windows
# SERIAL_PORT = "/dev/ttyUSB0"  # Linux/macOS
```

---

## 9. Estructura de archivos

```
sistemas-inteligentes/
├── firmware/
│   ├── test_hardware/           ← Tests de desarrollo (ya no se usan)
│   └── proyecto/
│       └── proyecto.ino         ← FIRMWARE PRINCIPAL
│
├── servidor_pc/                 ← SERVIDOR PYTHON
│   ├── servidor.py              ← Entry point: conecta todo
│   ├── serial_bridge.py         ← ESP32 Serial ↔ juego
│   ├── whisper_engine.py        ← Pipeline audio + Whisper
│   ├── validador.py             ← Texto → comando
│   ├── ws_server.py             ← WebSocket :8765
│   ├── tts.py                   ← Narrador + tonos
│   ├── config.py                ← Configuración
│   └── requirements.txt
│
├── tests/
│   └── simulador_pc/            ← Simulador sin ESP32
│       └── juego_sim.py         ← Reutilizado por servidor.py
│
├── web-panel/                   ← Panel Next.js
│
└── docs/
    └── arquitectura.md          ← Este archivo
```

---

## 10. Flujo completo de una jugada

```
00:00  python servidor.py
       → Carga Whisper 'small' (~5s cacheado)
       → Conecta ESP32 por Serial → recibe READY
       → WebSocket listo en :8765
       → TTS: "Servidor listo..."

00:10  Panel web conecta (Chrome localhost:3000)
       → TTS: "Bienvenido a Simon Dice..."

00:20  Jugador presiona ESPACIO
       → Panel → WS: PTT_INICIO
       → Python: pausar_timeout() + Serial 'R' al ESP32
       → ESP32: graba, RGB rojo, OLED "GRABANDO..."
       → Serial → Python: "PTT_START"

00:22  Jugador dice "empieza" y suelta ESPACIO
       → Panel → WS: PTT_FIN
       → Python: Serial 'T' al ESP32
       → ESP32: para, RGB azul, OLED "Procesando..."
       → Serial → Python: "PTT_STOP" + "AUDIO_START:15200" + bytes + "AUDIO_END"

00:22  Whisper: "empieza" → validador → START
       → juego.reanudar_timeout()
       → juego.procesar_comando("START")

00:23  Estado: SHOWING_SEQUENCE
       → TTS: "Mira y escucha."
       → Serial: "LED:ROJO" → ESP32 RGB rojo
       → TTS: "Rojo."
       → Serial: "LED:OFF"
       → Estado: LISTENING

00:26  Jugador presiona ESPACIO + dice "rojo"
       → [mismo flujo PTT]
       → Whisper: "rojo" → ROJO
       → Evaluación: CORRECTO, secuencia completa
       → Puntuación +10, nivel 2
       → TTS: "Correcto. Nivel 2."
       → Muestra secuencia [ROJO, VERDE]...
```

---

## 11. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| ESP32 no detectado | Driver faltante | Instalar CH340 o CP210x |
| ESP32 no detectado | Serial Monitor abierto | Cerrar Arduino IDE |
| Voz de ardilla | OVERSAMPLE=4 en firmware | Cambiar a OVERSAMPLE=2 |
| Alucinaciones Whisper | prop_decrease muy alto | Mantener en 0.55 |
| AZUL no reconocido | Palabra corta | Ya en tabla VARIANTES + fuzzy |
| TTS no habla | Sin voz española | Instalar voz "Paulina/Jorge" en Windows |
| Panel no conecta | Puerto 8765 libre | Verificar que servidor.py esté corriendo |
| Panel no conecta | Firefox/Safari | Usar Chrome o Edge |
| Sin buffer de audio | PSRAM no habilitada | Board settings: OPI PSRAM |
