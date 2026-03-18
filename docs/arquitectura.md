# Arquitectura — Simon Dice por Voz

## Visión general

El sistema tiene dos modos de operación, ambos usan el mismo Web Panel en Next.js:

| Modo | Cuándo usarlo | Requiere |
|---|---|---|
| **Simulador PC** | Pruebas sin hardware | Python + Chrome/Edge |
| **Modo ESP32** | Con kit ESP32 real (producción) | Kit + cable USB + Chrome/Edge |

---

## Modo Simulador PC (pruebas sin hardware)

El simulador replica el comportamiento del ESP32 en la PC: corre el motor del juego,
simula los LEDs en la terminal y reproduce tonos y TTS por el speaker del sistema.

### Reconocimiento de voz — modo DUAL con auto-detección

El simulador anuncia en el mensaje `READY` si tiene Whisper local cargado:

**Preferido — Whisper local en Python:**
- Python captura el micrófono del sistema directamente con `sounddevice`
- El browser NO necesita permisos de micrófono
- Browser envía `PTT_INICIO` / `PTT_FIN` al presionar/soltar el botón o barra espaciadora
- Python graba, transcribe con `openai-whisper` (modelo `small`) y devuelve el texto+comando

**Fallback — Whisper WASM en browser:**
- Solo se activa si Python no tiene Whisper instalado
- El browser descarga el modelo (`onnx-community/whisper-small`, ~125 MB, se cachea)
- El browser captura el micrófono con Web Audio API (modo PTT)
- El texto transcrito se envía como `{"tipo":"comando","comando":"ROJO"}`

### Flujo con Whisper local (preferido)

```
Browser                          Python ws_server.py
  │  ─── PTT_INICIO ──────────►  pausar timer + abrir sounddevice mic
  │  (mantiene botón presionado)
  │  ─── PTT_FIN ─────────────►  cerrar mic → Whisper local → "rojo" → VERDE
  │  ◄── {"tipo":"voz",          reanudar timer + procesar comando
  │        "texto":"verde",
  │        "comando":"VERDE"} ─
```

### Narrador TTS (simulador)

El simulador narra los eventos del juego en español. Sistema en cascada:

| Prioridad | Motor | Voz | Calidad | Requiere |
|---|---|---|---|---|
| 1 (preferido) | `edge-tts` + `pygame` | `es-MX-DaliaNeural` | Neural, acento mexicano real | Internet |
| 2 (fallback) | PowerShell SAPI | Sabina / Helena u otra instalada | Síntesis clásica | Voces Windows instaladas |

Eventos narrados:
- Conexión: bienvenida + instrucciones completas (incluyendo "presiona el botón y di empieza")
- SHOWING_SEQUENCE: "Mira y escucha."
- Cada color al mostrarse: "rojo", "verde", etc.
- LISTENING: "Tu turno. Presiona el botón para hablar."
- CORRECT: "Correcto."
- Level up: "Nivel N."
- WRONG: "Incorrecto. Di empieza para intentar de nuevo."
- TIMEOUT: "Tiempo agotado. Di empieza para intentar de nuevo."
- GAME_OVER: "Fin del juego. Obtuviste N puntos. Di empieza para volver a jugar."

### Diagrama de componentes

```
tests/simulador_pc/main.py
  ├── audio_pc.py      sounddevice (tonos + mic PTT) + edge-tts/SAPI (narrador)
  ├── juego_sim.py     lógica del juego en Python (espejo de game_engine.cpp)
  ├── leds_sim.py      LEDs simulados en terminal con colores ANSI
  ├── ws_server.py     WebSocket :8765 — bidireccional, envía READY con info dispositivos
  ├── validador.py     texto → comando (misma lógica que validador.ts)
  └── config_test.py   WHISPER_MODEL, TIMEOUT_RESPUESTA, SAMPLE_RATE

Web Panel (Chrome/Edge)
  ├── useWebSocket.ts     modo dual: Python mic (preferido) o WASM (fallback)
  ├── useWhisperWASM.ts   lazy load — solo descarga si Python no tiene Whisper
  └── validador.ts        texto → comando → envía PTT o comando WASM
```

---

## Modo ESP32 — Producción

El modo definitivo para la entrega del proyecto.
Solo requiere: kit ESP32 + cable USB + Chrome o Edge. **No instalar Python ni nada.**

### Cómo funciona paso a paso

```
Kit ESP32-S3
    │ USB (Web Serial API, 115200 baud)
    ↓
Chrome / Edge — panel en Vercel o localhost:3000
  ├── useWebSerial.ts  lee/escribe Serial en texto plano
  ├── useWhisperWASM.ts graba mic → Whisper WASM → texto (PTT)
  └── validador.ts     texto → comando → escribe "ROJO\n" por Serial
```

### Flujo completo con ESP32

1. **Abrir el panel** en `http://localhost:3000` o `https://[tu-app].vercel.app` en Chrome o Edge
2. **Seleccionar "ESP32 — Web Serial"** en el toggle del panel
3. **Whisper se carga** automáticamente en el browser (modelo `small` cuantizado, ~125 MB)
   - Primera vez: se descarga desde HuggingFace y se guarda en IndexedDB del browser
   - Siguientes veces: carga instantánea desde caché local
4. **Conectar el ESP32** por USB y hacer click en "Conectar"
   - Chrome/Edge pide seleccionar el puerto serial — elegir el del ESP32 (ej: COM5)
   - El firmware responde con `READY` y `STATE:IDLE`
5. **Presionar ESPACIO o el botón 🎤**, decir "**empieza**"
   - Browser captura audio con Web Audio API (PTT mientras se mantiene presionado)
   - Whisper transcribe: "empieza" → validador → comando `START`
   - Browser escribe `START\n` por Serial al ESP32
   - ESP32 recibe `START`, cambia a `STATE:SHOWING`
6. **ESP32 muestra la secuencia** de colores (LEDs + tonos)
   - Envía `STATE:SHOWING`, `LED:ROJO`, `LED:OFF`, `LED:VERDE`, etc.
   - El panel refleja los LEDs en tiempo real
   - Al terminar: `STATE:LISTENING` + `EXPECTED:ROJO`
7. **Turno del jugador**: badge "Presiona para hablar" aparece en el panel
   - Usuario presiona ESPACIO/botón → browser graba → Whisper → "rojo"
   - validador.ts → `ROJO`
   - Browser escribe `ROJO\n` por Serial
   - ESP32 evalúa: envía `RESULT:CORRECT` o `RESULT:WRONG`
8. **Si correcto**: secuencia crece en 1, ESP32 envía `LEVEL:2`, `STATE:SHOWING` de nuevo
9. **Si incorrecto o timeout**: ESP32 envía `STATE:GAMEOVER` → decir "empieza" para reiniciar

### Diagrama de comunicación ESP32

```
Usuario presiona PTT          Browser                    ESP32
        │                        │                          │
        ├─ mantiene botón ──────►│ getUserMedia() → graba   │
        │                        │ ← suelta botón           │
        │                        │ Whisper: "rojo" → ROJO   │
        │                        ├──── "ROJO\n" ──────────►│
        │                        │                          │ evalúa
        │                        │◄─── "RESULT:CORRECT\n" ─┤
        │                        │◄─── "LEVEL:2\n" ────────┤
        │                        │◄─── "STATE:SHOWING\n" ──┤
        │                        │◄─── "LED:AZUL\n" ───────┤
        │                        │◄─── "LED:OFF\n" ────────┤
```

---

## Estructura de carpetas

```
sistemas-inteligentes/
│
├── firmware/              C++ Arduino — corre en el ESP32-S3
│   ├── simon_dice.ino     entry point, setup() y loop()
│   ├── vocabulario.h      ÚNICA fuente del vocabulario de comandos
│   ├── game_engine.h/cpp  máquina de estados (TIMEOUT_RESPUESTA=30000ms)
│   ├── led_control.h/cpp  control de los 4 LEDs físicos
│   ├── sound_control.h/cpp tonos por speaker MAX98357A
│   ├── audio_capture.h/cpp captura I2S (reservado)
│   └── serial_comm.h/cpp  protocolo de texto por USB Serial
│
├── tests/
│   └── simulador_pc/      reemplaza el kit ESP32 para pruebas en PC
│       ├── main.py        entry point: arranca juego, WebSocket y hilos
│       ├── juego_sim.py   lógica del juego (espejo de game_engine.cpp)
│       ├── audio_pc.py    sounddevice (tonos + mic PTT) + edge-tts/SAPI (narrador)
│       ├── leds_sim.py    LEDs simulados en terminal con colores ANSI
│       ├── ws_server.py   WebSocket ↔ panel; envía READY con info de dispositivos
│       ├── validador.py   normaliza texto → comando
│       ├── config_test.py parámetros: WHISPER_MODEL, TIMEOUT_RESPUESTA, SAMPLE_RATE
│       └── requirements_test.txt
│
├── web-panel/             Next.js 14 + TypeScript — UI del juego
│   ├── app/
│   │   ├── page.tsx       dashboard principal, orquesta los modos
│   │   └── components/    GameStatus, LEDPanel, SequenceDisplay,
│   │                      LogConsole, ScoreBoard, ConnectionPanel, HowToPlay
│   ├── hooks/
│   │   ├── useWebSocket.ts    modo simulador (dual: Python mic o WASM fallback)
│   │   ├── useWebSerial.ts    modo ESP32 (Web Serial + Whisper WASM)
│   │   └── useWhisperWASM.ts  Whisper en browser: PTT + Web Worker (lazy load)
│   ├── workers/
│   │   └── whisper.worker.ts  Web Worker con @huggingface/transformers
│   ├── lib/
│   │   └── validador.ts       texto → comando (port de validador.py)
│   └── types/game.ts          tipos TypeScript del protocolo
│
└── docs/                  esta documentación
    ├── arquitectura.md
    ├── setup.md
    └── flujo_conversacion.md
```

---

## Protocolo WebSocket (simulador ↔ browser)

JSON, una línea por mensaje.

### simulador → panel

| tipo | Campos adicionales | Significado |
|---|---|---|
| `ready` | `whisperDisponible`, `whisperModelo`, `dispositivoMic`, `dispositivoSpeaker` | Simulador listo con info de dispositivos |
| `state` | `estado` | Cambio de estado del juego |
| `led` | `color` (null=apagado) | LED encendido/apagado |
| `sequence` | `secuencia[]` | Secuencia del nivel |
| `expected` | `esperado` | Color que se espera |
| `detected` | `palabra` | Palabra detectada |
| `result` | `resultado` | CORRECT/WRONG/TIMEOUT |
| `level` | `nivel` | Nivel actual |
| `score` | `puntuacion` | Puntuación actual |
| `gameover` | — | Fin del juego |
| `voz` | `texto`, `comando` | Resultado de Whisper local (Python transcribió) |
| `log` | `raw` | Mensaje de debug |

### panel → simulador

| tipo | Campos | Cuándo |
|---|---|---|
| `control` | `accion: "PTT_INICIO"` | Usuario presionó botón/espacio |
| `control` | `accion: "PTT_FIN"` | Usuario soltó botón/espacio |
| `comando` | `comando` | Fallback WASM: browser transcribió localmente |

---

## Protocolo Serial (ESP32 ↔ browser)

Texto plano, una línea por mensaje, `\n` al final, 115200 baud.

### ESP32 → browser

| Mensaje | Significado |
|---|---|
| `READY` | Sistema inicializado |
| `STATE:IDLE` | Esperando inicio |
| `STATE:SHOWING` | Mostrando secuencia de LEDs |
| `STATE:LISTENING` | Esperando respuesta del jugador |
| `STATE:EVALUATING` | Procesando respuesta |
| `STATE:GAMEOVER` | Fin del juego |
| `STATE:PAUSA` | Juego pausado |
| `LED:ROJO` / `LED:OFF` | LED encendido o apagado |
| `RESULT:CORRECT` | Respuesta correcta |
| `RESULT:WRONG` | Respuesta incorrecta |
| `RESULT:TIMEOUT` | No habló a tiempo |
| `SEQUENCE:ROJO,AZUL,...` | Secuencia completa del nivel |
| `EXPECTED:VERDE` | Color que se espera en este turno |
| `LEVEL:3` | Nivel actual |
| `SCORE:30` | Puntuación actual |

### browser → ESP32

| Mensaje | Significado |
|---|---|
| `ROJO\n` | Comando reconocido por Whisper |
| `DESCONOCIDO\n` | No se entendió |

---

## Máquina de estados del juego

```
IDLE ──(START)──► SHOWING_SEQUENCE
                         │
                  muestra cada LED + tono uno por uno
                  narrador dice el color
                         │
                         ▼
                     LISTENING ◄──(REPITE)──┐
                         │                   │
                  badge "Presiona para        │
                  hablar" en el panel         │
                  narrador: "Tu turno.        │
                  Presiona el botón."         │
                         │                   │
                  usuario presiona PTT        │
                  Python/browser graba        │
                  Whisper transcribe          │
                         │                   │
                         ▼                   │
                     EVALUATING             │
                    /          \            │
                correcto     incorrecto    │
                /                \         │
           CORRECT            WRONG/TIMEOUT│
              │                    │       │
       ¿fin secuencia?         GAME_OVER  │
         sí    no                  │       │
         │      │            ──(START)──►IDLE
      LEVEL_UP  │
         │    (siguiente color)
         ▼
  SHOWING_SEQUENCE (nivel+1)
```

---

## IA — Whisper

Whisper es un modelo de reconocimiento de voz de OpenAI entrenado en 680,000 horas de audio
multilingüe. En este proyecto puede correr de dos formas:

### Whisper local (Python) — preferido en el simulador

- Librería: `openai-whisper`
- Modelo: `small` (244 MB, se descarga y cachea automáticamente)
- Corre en la CPU del PC al recibir PTT_FIN
- `initial_prompt` con vocabulario del juego para reducir alucinaciones
- Latencia típica en CPU: 2–8 segundos (depende del hardware)
- **El browser NO necesita permisos de micrófono en este modo**

### Whisper WASM (browser) — fallback / modo ESP32

- Librería: `@huggingface/transformers` v3 (ONNX Runtime Web)
- Modelo: `onnx-community/whisper-small` (~125 MB cuantizado INT8)
- Corre en un Web Worker separado para no bloquear la UI
- Se descarga una sola vez y se cachea en IndexedDB del browser
- Solo se descarga si el simulador no tiene Whisper local
- Idioma: español (`language: "es"`)
- `initial_prompt` con vocabulario del juego
- Latencia típica en CPU moderna: 1–3 segundos

| | Whisper local (Python) | Whisper WASM (browser) |
|---|---|---|
| Modelo | `small` (244 MB) | `small` cuantizado (125 MB) |
| Micrófono | Python `sounddevice` | Web Audio API del browser |
| Permisos mic browser | No necesita | Sí |
| Latencia | 2–8 s | 1–3 s |
| Disponible en | Solo simulador PC | Simulador (fallback) + ESP32 |

---

## Modos del panel (resumen)

| Modo | Toggle | Cuándo usar |
|---|---|---|
| **Simulador — WebSocket** | "WebSocket" | `python main.py` corriendo en PC |
| **ESP32 — Web Serial** | "Serial" | Kit ESP32 conectado por USB, producción |
