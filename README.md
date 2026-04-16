# Simon Dice por Voz

Proyecto universitario — Sistemas Inteligentes.
Juego Simon Dice controlado completamente por voz en español.

## Hardware

- **ESP32-S3** (kit OKYSTAR PCB 56483A_Y85_250412 — N16R8: 16MB Flash, 8MB PSRAM)
- Micrófono MAX4466 (ADC analógico, 8kHz, filtros HPF+LPF en firmware)
- OLED SSD1306 0.91" (128×32px)
- LED WS2812B RGB (NeoPixel)
- Comunicación: USB Serial 921600 baud

## Arquitectura (Fase 1 — con PC)

```
ESP32-S3 → USB Serial → Python Server → WebSocket → Next.js Panel
              (audio PCM)   (Whisper ASR)
```

## Setup rápido

### 1. Servidor Python

```bash
cd servidor_pc
pip install openai-whisper pyserial websockets pygame edge-tts scipy noisereduce numpy
python servidor.py
```

El modelo Whisper `small` (~244MB) se descarga automáticamente la primera vez.

### 2. Panel Web

```bash
cd web-panel
npm install
npm run dev
```

Abrir **Chrome o Edge** en `http://localhost:3000` (Firefox no soporta Web Serial API).

### 3. Firmware ESP32

- IDE: Arduino IDE o PlatformIO
- Board: ESP32S3 Dev Module
- Flash: 16MB, PSRAM: OPI, Upload Speed: 921600
- Abrir `firmware/proyecto/proyecto.ino` y flashear

## Cómo jugar

1. Conectar ESP32 por USB
2. Iniciar el servidor Python (`python servidor_pc/servidor.py`)
3. Abrir el panel web → clic en **Conectar** (tab "Servidor PC")
4. Decir **"empieza"** para iniciar
5. El sistema muestra una secuencia de colores (RGB + panel)
6. Presionar **ESPACIO** y decir el/los colores en orden

### Modo mono-color
Di un color por turno: `"azul"`, `"rojo"`, etc.

### Modo multi-color
Di varios colores seguidos en un solo audio: `"azul rojo amarillo"`.
El sistema los procesa en orden. Para en el primer color incorrecto.

| Ejemplo | Resultado |
|---------|-----------|
| `"azul rojo amarillo"` | Acepta los 3 |
| `"adul dojo amadillo"` | Acepta AZUL, ROJO, AMARILLO (fuzzy) |
| `"azul rojo sdadsa verde"` | Acepta AZUL y ROJO, para en sdadsa |
| `"sdadsa rojo"` | No acepta nada (primer color no reconocido) |
| `"verde azul"` (seq: AZUL…) | WRONG — primer color incorrecto |

## Vocabulario de voz

| Categoría | Palabras |
|-----------|----------|
| Colores | rojo, verde, azul, amarillo |
| Control | empieza, para, pausa, repite, reiniciar |
| Direcciones | arriba, abajo, izquierda, derecha |
| Respuestas | sí, no |

Whisper tolera variantes fonéticas: "adul" → AZUL, "berde" → VERDE, "dojo" → ROJO, etc.

## Estructura del proyecto

```
sistemas-inteligentes/
├── firmware/proyecto/       ← Arduino C++ (ESP32)
├── servidor_pc/             ← Python: Serial + Whisper + WebSocket
│   ├── servidor.py          ← Orquestador principal
│   ├── validador.py         ← texto_a_comando(), texto_a_colores()
│   ├── whisper_engine.py    ← Pipeline de audio + Whisper
│   ├── serial_bridge.py     ← Comunicación Serial con ESP32
│   ├── ws_server.py         ← Servidor WebSocket
│   ├── tts.py               ← Narrador de voz (Edge TTS + SAPI)
│   └── config.py            ← Configuración central
├── tests/simulador_pc/      ← juego_sim.py (motor del juego)
├── web-panel/               ← Next.js 14 + TypeScript
└── docs/                    ← Diagramas de arquitectura
```

## Diagramas

Ver `docs/arquitectura_flujo.md` para diagramas detallados de:
- Flujo de una ronda completa
- Máquina de estados
- Sincronización TTS ↔ Timer ↔ PTT ↔ Panel
- Protocolo WebSocket
- Modo multi-color
