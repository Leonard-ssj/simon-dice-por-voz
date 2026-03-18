# Arquitectura — Simon Dice por Voz

## Visión general

El sistema tiene dos modos de operación, ambos usan el mismo Web Panel en Next.js:

| Modo | Cuándo usarlo | Requiere |
|---|---|---|
| **Simulador PC** | Pruebas sin hardware | Python + Chrome/Edge |
| **Modo ESP32** | Con kit ESP32 real (producción) | Kit + cable USB + Chrome/Edge |

---

## Diagrama general del sistema

```mermaid
graph TD
  subgraph SIMULADOR["Modo Simulador PC"]
    PY["Python main.py\n(motor del juego)"]
    WS["ws_server.py\nWebSocket :8765"]
    MIC["sounddevice\n(micrófono sistema)"]
    TTS["edge-tts / SAPI\n(narrador TTS)"]
    WHISPER_PY["openai-whisper\n(modelo small)"]
    PY --> WS
    PY --> TTS
    WS --> MIC --> WHISPER_PY
  end

  subgraph PANEL["Web Panel — Chrome/Edge"]
    PAGE["page.tsx\n(dashboard)"]
    WS_HOOK["useWebSocket.ts"]
    SERIAL_HOOK["useWebSerial.ts"]
    WASM["useWhisperWASM.ts\n+ whisper.worker.ts"]
    VAL["validador.ts"]
    PAGE --> WS_HOOK & SERIAL_HOOK
    WASM --> VAL
  end

  subgraph ESP32["Modo Hardware"]
    FW["Firmware C++\n(ESP32-S3)"]
    GAME["game_engine.cpp\n(máquina de estados)"]
    LEDS["led_control.cpp\n(4 LEDs físicos)"]
    SND["sound_control.cpp\n(speaker MAX98357A)"]
    FW --> GAME --> LEDS & SND
  end

  WS_HOOK <-->|"WebSocket JSON\nws://localhost:8765"| WS
  SERIAL_HOOK <-->|"Web Serial\n115200 baud\ntexto plano"| FW
  WASM -->|"texto transcrito"| SERIAL_HOOK
```

---

## Modo Simulador PC

El simulador replica el comportamiento del ESP32 en la PC: corre el motor del juego,
simula los LEDs en la terminal y reproduce tonos y TTS por el speaker del sistema.

### Reconocimiento de voz — modo DUAL

```mermaid
flowchart LR
  A[/"READY {whisperDisponible: true}"/] --> B{¿Python\ntiene Whisper?}
  B -- Sí --> C["Modo PTT local\nPython captura mic"]
  B -- No --> D["Modo WASM\nbrowser descarga modelo\n~125 MB"]
  C --> E["PTT_INICIO / PTT_FIN\npor WebSocket"]
  D --> F["Graba con Web Audio\nWhisper WASM en Worker"]
  E --> G["Whisper small\n244 MB en CPU"]
  F --> H["Whisper small INT8\n125 MB en browser"]
  G --> I[/"voz: {texto, comando}"/]
  H --> J[/"comando: {comando}"/]
```

**Preferido — Whisper local en Python:**
- Python captura el micrófono del sistema directamente con `sounddevice`
- El browser **NO** necesita permisos de micrófono
- Browser envía `PTT_INICIO` / `PTT_FIN` al presionar/soltar el botón o barra espaciadora
- Python graba, transcribe con `openai-whisper` (modelo `small`) y devuelve texto+comando

**Fallback — Whisper WASM en browser:**
- Solo se activa si Python no tiene Whisper instalado
- El browser descarga el modelo (`onnx-community/whisper-small`, ~125 MB, se cachea)
- El browser captura el micrófono con Web Audio API (modo PTT)

### Flujo PTT completo (Whisper local)

```mermaid
sequenceDiagram
  participant U as Usuario
  participant B as Browser
  participant P as Python ws_server
  participant J as juego_sim.py

  U->>B: Presiona ESPACIO / botón 🎤
  B->>P: {"tipo":"control","accion":"PTT_INICIO"}
  P->>J: pausar_timeout()
  P->>P: sounddevice.InputStream.start()

  U->>B: Suelta botón
  B->>P: {"tipo":"control","accion":"PTT_FIN"}
  P->>P: sounddevice stop → numpy array
  P->>P: whisper.transcribe(audio) → "rojo"
  P->>J: reanudar_timeout()
  P->>J: procesar_comando("ROJO")
  P->>B: {"tipo":"voz","texto":"rojo","comando":"ROJO"}
```

### Narrador TTS

```mermaid
flowchart TD
  E[Evento del juego] --> T{¿edge-tts\n+ pygame\ndisponibles?}
  T -- Sí --> ET["edge-tts\nes-MX-DaliaNeural\n(voz neural mexicana)"]
  T -- No --> S{¿hay voz\nespañol SAPI?}
  S -- Sí --> SAPI["PowerShell SAPI\n(Sabina / Helena)"]
  S -- No --> EN["PowerShell SAPI\n(voz en inglés)"]
  ET -->|falla/sin internet| SAPI
```

**Eventos narrados:**
- Conexión: bienvenida + instrucciones ("presiona el botón y di empieza")
- SHOWING: "Mira y escucha." + nombre de cada color al mostrarlo
- LISTENING: "Tu turno. Presiona el botón para hablar."
- CORRECT: "Correcto."
- LEVEL_UP: "Nivel N."
- WRONG: "Incorrecto. Di empieza para intentar de nuevo."
- TIMEOUT: "Tiempo agotado. Di empieza para intentar de nuevo."
- GAME_OVER: "Fin del juego. Obtuviste N puntos. Di empieza para volver a jugar."

---

## Modo ESP32 — Producción

El modo definitivo. Solo requiere: kit ESP32 + cable USB + Chrome o Edge.
**No se necesita instalar Python.**

### Cómo funciona — paso a paso

```mermaid
sequenceDiagram
  participant U as Usuario
  participant B as Browser (Chrome/Edge)
  participant W as Whisper WASM<br/>(Web Worker)
  participant E as ESP32-S3

  Note over B,W: Al abrir el panel por primera vez
  B->>W: Inicializar worker
  W->>W: Descargar whisper-small<br/>~125 MB (solo 1 vez, se cachea)
  W-->>B: {tipo:"ready"}

  Note over U,E: Conectar hardware
  U->>B: Click "Conectar al ESP32"
  B->>E: Web Serial API — abre puerto COM
  E-->>B: "READY\n"
  E-->>B: "STATE:IDLE\n"
  B-->>U: Badge "Whisper listo" 🟢

  Note over U,E: Iniciar juego
  U->>B: Presiona ESPACIO + dice "empieza"
  B->>W: {audio: Float32Array}
  W-->>B: {texto:"empieza"} → validador → "START"
  B->>E: "START\n"
  E-->>B: "STATE:SHOWING\n"
  E-->>B: "LED:ROJO\n" → "LED:OFF\n"
  E-->>B: "LED:VERDE\n" → "LED:OFF\n"
  E-->>B: "STATE:LISTENING\n"
  E-->>B: "EXPECTED:ROJO\n"

  Note over U,E: Turno del jugador
  U->>B: Presiona ESPACIO + dice "rojo"
  B->>W: {audio: Float32Array}
  W-->>B: {texto:"rojo"} → validador → "ROJO"
  B->>E: "ROJO\n"
  E-->>B: "RESULT:CORRECT\n"
  E-->>B: "LEVEL:2\n"
  E-->>B: "STATE:SHOWING\n"
```

### Diagrama de comunicación Serial

```mermaid
flowchart LR
  subgraph BROWSER["Chrome / Edge"]
    WS2["useWebSerial.ts"]
    WASM2["Whisper WASM\nWeb Worker"]
    VAL2["validador.ts"]
    WS2 -->|"Lee líneas\ntexto plano"| PARSE["Parsear mensajes\nESP32→browser"]
    WASM2 -->|"texto transcrito"| VAL2 -->|"ROJO / VERDE..."| WS2
  end
  subgraph KIT["Kit OKYN-G5806"]
    FW2["simon_dice.ino"]
    GM["game_engine.cpp"]
    LC["led_control.cpp"]
    SC["sound_control.cpp"]
    FW2 --> GM --> LC & SC
  end
  WS2 <-->|"USB Serial\n115200 baud\n'ROJO\n' / 'LED:ROJO\n'"| FW2
```

### Mensajes del protocolo Serial

**ESP32 → browser:**
```
READY               sistema inicializado
STATE:IDLE          esperando inicio
STATE:SHOWING       mostrando secuencia de LEDs
STATE:LISTENING     esperando respuesta del jugador
STATE:EVALUATING    procesando respuesta
STATE:GAMEOVER      fin del juego
STATE:PAUSA         juego pausado
LED:ROJO            LED rojo encendido
LED:OFF             LEDs apagados
RESULT:CORRECT      respuesta correcta
RESULT:WRONG        respuesta incorrecta
RESULT:TIMEOUT      no habló a tiempo
SEQUENCE:ROJO,AZUL  secuencia completa del nivel
EXPECTED:VERDE      color esperado en este turno
LEVEL:3             nivel actual
SCORE:30            puntuación actual
```

**browser → ESP32:**
```
ROJO\n              comando reconocido por Whisper
DESCONOCIDO\n       no se entendió
```

---

## Máquina de estados del juego

```mermaid
stateDiagram-v2
  [*] --> IDLE

  IDLE --> SHOWING_SEQUENCE : START

  SHOWING_SEQUENCE --> LISTENING : secuencia mostrada

  LISTENING --> EVALUATING : PTT_FIN (audio capturado)
  LISTENING --> LISTENING : REPITE
  LISTENING --> PAUSA : PAUSA
  LISTENING --> GAME_OVER : TIMEOUT

  PAUSA --> LISTENING : START / REPITE

  EVALUATING --> CORRECT : respuesta correcta
  EVALUATING --> WRONG : respuesta incorrecta

  CORRECT --> LEVEL_UP : fin de secuencia
  CORRECT --> LISTENING : siguiente color

  LEVEL_UP --> SHOWING_SEQUENCE : secuencia + 1

  WRONG --> GAME_OVER
  GAME_OVER --> IDLE : START / REINICIAR
```

---

## IA — Whisper

| | Whisper local (Python) | Whisper WASM (browser) |
|---|---|---|
| Librería | `openai-whisper` | `@huggingface/transformers` v3 |
| Modelo | `small` (244 MB) | `small` cuantizado INT8 (125 MB) |
| Micrófono | Python `sounddevice` | Web Audio API |
| Permisos mic browser | No necesita | Sí |
| Latencia (CPU) | 2–8 s | 1–3 s |
| Caché | carpeta `~/.cache/whisper` | IndexedDB del browser |
| Disponible en | Solo simulador PC | Simulador (fallback) + ESP32 |

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
│   └── simulador_pc/
│       ├── main.py        entry point: juego + WebSocket + hilos
│       ├── juego_sim.py   lógica del juego (espejo de game_engine.cpp)
│       ├── audio_pc.py    sounddevice (tonos + mic PTT) + edge-tts/SAPI
│       ├── leds_sim.py    LEDs simulados en terminal (ANSI)
│       ├── ws_server.py   WebSocket ↔ panel; READY con info dispositivos
│       ├── validador.py   normaliza texto → comando
│       ├── config_test.py WHISPER_MODEL, TIMEOUT_RESPUESTA, SAMPLE_RATE
│       └── requirements_test.txt
│
├── web-panel/             Next.js 14 + TypeScript
│   ├── app/
│   │   ├── page.tsx       dashboard principal
│   │   └── components/    GameStatus, LEDPanel, SequenceDisplay,
│   │                      LogConsole, ScoreBoard, ConnectionPanel, HowToPlay
│   ├── hooks/
│   │   ├── useWebSocket.ts    modo simulador
│   │   ├── useWebSerial.ts    modo ESP32
│   │   └── useWhisperWASM.ts  Whisper WASM (lazy load)
│   ├── workers/
│   │   └── whisper.worker.ts  Web Worker con @huggingface/transformers
│   ├── lib/
│   │   └── validador.ts       texto → comando
│   └── types/game.ts
│
└── docs/
    ├── arquitectura.md    (este archivo)
    └── setup.md
```

---

## Modos del panel

| Modo | Toggle | Cuándo usar |
|---|---|---|
| **Simulador — WebSocket** | "WebSocket" | `python main.py` corriendo en PC |
| **ESP32 — Web Serial** | "Serial" | Kit ESP32 conectado por USB |
