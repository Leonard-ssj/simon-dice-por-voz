# Arquitectura — Simon Dice por Voz

## Visión general

El sistema tiene dos modos de operación, ambos usan el mismo Web Panel en Next.js:

| Modo | Cuándo usarlo | Requiere |
|---|---|---|
| **Simulador PC** | Pruebas sin hardware | Python + Chrome/Edge |
| **Modo ESP32** | Con kit ESP32 real (producción) | Kit + cable USB + Chrome/Edge |

En ambos modos el reconocimiento de voz ocurre **en el browser** usando Whisper WASM
(`@huggingface/transformers` con modelo `onnx-community/whisper-small`, ~125MB cuantizado,
se cachea en IndexedDB). No se necesita Python en producción.

---

## Modo Simulador PC (pruebas sin hardware)

El simulador replica el comportamiento del ESP32 en la PC: corre el motor del juego,
simula los LEDs en la terminal y reproduce tonos y TTS por el speaker del sistema.
Los comandos de voz llegan desde el browser via WebSocket.

```
tests/simulador_pc/main.py
  ├── audio_pc.py      sounddevice (tonos) + pyttsx3 (TTS narrador)
  ├── juego_sim.py     lógica del juego en Python (espejo del firmware C++)
  ├── leds_sim.py      LEDs simulados en terminal con colores ANSI
  ├── ws_server.py     WebSocket :8765 ↔ Web Panel (bidireccional)
  └── validador.py     texto → comando (misma lógica que validador.ts)

Web Panel (Chrome/Edge)
  ├── useWebSocket.ts  se conecta a ws://localhost:8765
  ├── useWhisperWASM.ts graba mic → Whisper WASM → texto
  └── validador.ts     texto → comando → envía via WebSocket
```

Flujo cuando el panel está conectado:
1. Browser escucha para todos los estados: IDLE, LISTENING, PAUSA, GAMEOVER
2. Browser reconoce el comando con Whisper WASM y lo manda via WebSocket:
   `{"tipo": "comando", "comando": "ROJO"}`
3. `ws_server.py` recibe el mensaje → llama `juego.procesar_comando(cmd)`
4. El juego actualiza estado → callbacks → LEDs ANSI, tonos, TTS, WebSocket al panel

---

## Modo ESP32 — Producción

El modo definitivo para la entrega del proyecto.
Solo requiere: kit ESP32 + cable USB + Chrome o Edge. No instalar Python ni nada.

```
Kit ESP32-S3
    │ USB (Web Serial API, 115200 baud)
    ↓
Chrome / Edge — panel en Vercel o localhost:3000
  ├── useWebSerial.ts  lee/escribe Serial en texto plano
  ├── useWhisperWASM.ts graba mic → Whisper WASM → texto
  └── validador.ts     texto → comando → escribe "ROJO\n" por Serial
```

Flujo completo:
1. Panel descarga Whisper Small (~125MB, se cachea en IndexedDB después)
2. Usuario conecta ESP32 por USB → click "Conectar al ESP32"
3. ESP32 envía `READY`, `STATE:IDLE`
4. Usuario dice "empieza" → browser → Whisper → "START" → Serial → ESP32
5. ESP32 muestra secuencia (LEDs + tonos), envía `STATE:SHOWING`, `LED:ROJO`, etc.
6. ESP32 envía `STATE:LISTENING` → browser ya está escuchando (bucle continuo)
7. Browser detecta el color → Serial → ESP32 → evalúa → `RESULT:CORRECT/WRONG`

El ESP32 maneja: `game_engine.cpp`, `led_control.cpp`, `sound_control.cpp`, `serial_comm.cpp`.
El browser maneja: reconocimiento de voz + panel visual.

---

## Estructura de carpetas

```
sistemas-inteligentes/
│
├── firmware/              C++ Arduino — corre en el ESP32-S3
│   ├── simon_dice.ino     entry point, setup() y loop()
│   ├── vocabulario.h      ÚNICA fuente del vocabulario de comandos
│   ├── game_engine.h/cpp  máquina de estados (TIMEOUT_RESPUESTA=15000ms)
│   ├── led_control.h/cpp  control de los 4 LEDs físicos
│   ├── sound_control.h/cpp tonos por speaker MAX98357A
│   ├── audio_capture.h/cpp captura I2S (reservado para Edge Impulse futuro)
│   └── serial_comm.h/cpp  protocolo de texto por USB Serial
│
├── tests/
│   └── simulador_pc/      reemplaza el kit ESP32 para pruebas en PC
│       ├── main.py        entry point: arranca juego, WebSocket y hilos
│       ├── juego_sim.py   lógica del juego (espejo de game_engine.cpp)
│       ├── audio_pc.py    tonos por sounddevice + TTS narrador (pyttsx3)
│       ├── leds_sim.py    LEDs simulados en terminal con colores ANSI
│       ├── ws_server.py   servidor WebSocket ↔ panel (bidireccional)
│       ├── validador.py   normaliza texto → comando (equivalente a validador.ts)
│       └── config_test.py parámetros de audio y juego
│
├── web-panel/             Next.js 14 + TypeScript — UI del juego
│   ├── app/
│   │   ├── page.tsx       dashboard principal, orquesta los modos
│   │   └── components/    GameStatus, LEDPanel, SequenceDisplay,
│   │                      LogConsole, ScoreBoard, ConnectionPanel, HowToPlay
│   ├── hooks/
│   │   ├── useWebSocket.ts    modo simulador (WebSocket + Whisper WASM)
│   │   ├── useWebSerial.ts    modo ESP32 (Web Serial + Whisper WASM)
│   │   └── useWhisperWASM.ts  Whisper en browser: VAD + Web Worker
│   ├── workers/
│   │   └── whisper.worker.ts  Web Worker con @huggingface/transformers
│   ├── lib/
│   │   └── validador.ts       texto → comando (port de validador.py)
│   └── types/game.ts          tipos TypeScript del protocolo
│
├── modelo_voz/            Edge Impulse (opcional, alternativa futura)
│   └── datos/             muestras de audio por clase
│
└── docs/                  esta documentación
    ├── arquitectura.md
    ├── setup.md
    ├── flujo_conversacion.md
    ├── diagrama_simulador_pc.md
    └── diagrama_opcion_c.md
```

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
| `DETECTED:ROJO` | Palabra detectada |
| `RESULT:CORRECT` | Respuesta correcta |
| `RESULT:WRONG` | Respuesta incorrecta |
| `RESULT:TIMEOUT` | No habló a tiempo |
| `SEQUENCE:ROJO,AZUL,...` | Secuencia completa del nivel |
| `EXPECTED:VERDE` | Color que se espera en este turno |
| `LEVEL:3` | Nivel actual |
| `SCORE:30` | Puntuación actual |
| `GAMEOVER` | Fin del juego |

### browser → ESP32

| Mensaje | Significado |
|---|---|
| `ROJO\n` | Comando reconocido por Whisper WASM |
| `DESCONOCIDO\n` | No se entendió |

---

## Protocolo WebSocket (simulador ↔ browser)

JSON, una línea por mensaje. El panel también **envía** comandos al simulador.

### simulador → panel (mensajes JSON)

| tipo | Campos adicionales | Significado |
|---|---|---|
| `ready` | — | Simulador listo |
| `state` | `estado` | Cambio de estado del juego |
| `led` | `color` (null=apagado) | LED encendido/apagado |
| `sequence` | `secuencia[]` | Secuencia del nivel |
| `expected` | `esperado` | Color que se espera |
| `detected` | `palabra` | Palabra detectada |
| `result` | `resultado` | CORRECT/WRONG/TIMEOUT |
| `level` | `nivel` | Nivel actual |
| `score` | `puntuacion` | Puntuación actual |
| `gameover` | — | Fin del juego |
| `voz` | `texto`, `comando` | Texto crudo + comando validado |
| `log` | `raw` | Mensaje de debug |

### panel → simulador

| tipo | Campos | Significado |
|---|---|---|
| `comando` | `comando` | Comando reconocido por Whisper WASM en el browser |

---

## Máquina de estados del juego

```
IDLE ──(START)──► SHOWING_SEQUENCE
                         │
                  muestra cada LED + tono uno por uno
                         │
                         ▼
                     LISTENING ◄──(REPITE)──┐
                         │                   │
                  browser escucha voz        │
                  Whisper WASM transcribe    │
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

## IA — Whisper en el browser

Whisper es un modelo de reconocimiento de voz de OpenAI entrenado en 680,000 horas de audio
multilingüe. En este proyecto corre **completamente en el browser** via WebAssembly.

- Librería: `@huggingface/transformers` v3 (ONNX Runtime Web)
- Modelo: `onnx-community/whisper-small` (~244MB original → ~125MB con cuantización INT8)
- Corre en un Web Worker separado para no bloquear la UI
- Se descarga una sola vez y se cachea en IndexedDB del browser
- Sin internet después de la descarga inicial
- Idioma forzado: español (`language: "es"`)
- `initial_prompt` con vocabulario del juego para reducir alucinaciones
- Latencia típica en CPU moderna: 1–3 segundos por frase

**Filtro de alucinaciones** (`validador.ts`):
Whisper a veces "inventa" texto cuando no hay voz real. `esAlucinacion()` descarta:
- Frases sin ninguna palabra del vocabulario del juego (ej: "Bienvenidos.", "[Música]")
- Loops de repetición (ej: "no no no no no...")
- Frases largas (> 3 palabras) sin coincidencia clara

### Por qué Whisper no corre en el ESP32-S3

| | Whisper small | ESP32-S3 |
|---|---|---|
| Tamaño del modelo | ~244 MB | 16 MB flash total |
| RAM en inferencia | ~500 MB | 512 KB SRAM + 8 MB PSRAM |

Por eso el reconocimiento de voz vive en el browser, no en el chip.

---

## IA — Edge Impulse (alternativa futura)

Si en el futuro se quisiera que el ESP32 haga el reconocimiento sin browser:

1. Grabar ~50–100 muestras por palabra (1 segundo, 16kHz)
2. Subir a Edge Impulse → crear impulso MFCC → red neuronal
3. Entrenar (< 10 minutos en la nube)
4. Exportar librería Arduino → importar en `firmware/voice_model.cpp`

| | Whisper WASM (browser) | Edge Impulse (ESP32) |
|---|---|---|
| Corre en | Browser (WASM) | ESP32-S3 (C++) |
| Vocabulario | Cualquier palabra | Solo palabras entrenadas |
| Latencia | 1–3 s | ~40 ms |
| RAM necesaria | MB en JS heap | ~9 MB en chip |
| Requiere panel | Sí | No |
