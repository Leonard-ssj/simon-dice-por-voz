# Simon Dice por Voz — Sistemas Inteligentes

## Contexto del proyecto
Proyecto universitario de la materia **Sistemas Inteligentes**.
Juego físico Simon Dice controlado completamente por voz en **español**.
Hardware principal: Kit **MRD085A** (ESP32-S3 con micrófono INMP441, speaker MAX98357A integrados).
IDE: **Antigravity**
Tiempo disponible: **1 mes** (Fase 1 en 2 semanas, Fase 2 + Web Panel las 2 restantes)

---

## Arquitectura — Híbrida 2 Fases

### Fase 1 — Prototipo funcional (con PC)
```
ESP32-S3 → USB Serial → Python Server (Whisper base) → comando → ESP32
                                  ↓
                          WebSocket (localhost)
                                  ↓
                          Next.js Web Panel
```

### Fase 2 — Sistema autónomo (sin PC)
```
ESP32-S3 + Modelo Edge Impulse (TFLite Micro)
      ↓ detecta comando localmente
Motor del juego
      ↓
LEDs + Speaker
      ↓ USB Serial (eventos)
Next.js Web Panel (Web Serial API directo desde el browser)
```

> Fase 1 completa = entrega mínima viable
> Fase 2 + Web Panel = entrega completa y autónoma

---

## Stack tecnológico

| Sistema | Tecnología | Lenguaje |
|---|---|---|
| Firmware ESP32 | Arduino framework sobre ESP-IDF | C++ |
| Reconocimiento voz Fase 1 | Whisper `base` (local, gratis, sin internet) | Python |
| Comunicación Fase 1 | pyserial + websockets | Python |
| Modelo voz Fase 2 | Edge Impulse → TFLite Micro | — generado |
| Web Panel | Next.js 14 + TypeScript | TypeScript |
| Deploy web | Vercel | — |
| Control versiones | Git | — |

---

## Vocabulario — expandible

El vocabulario vive únicamente en `firmware/vocabulario.h`.
Nunca hardcodear palabras en otro archivo.

Agregar palabras en Fase 1: editar el array, recompilar.
Agregar palabras en Fase 2: grabar ~50 muestras nuevas + reentrenar Edge Impulse (~30 min).

```cpp
// Vocabulario actual
Colores:     ROJO, VERDE, AZUL, AMARILLO
Acciones:    START, STOP, PAUSA, REPITE, REINICIAR
Direcciones: ARRIBA, ABAJO, IZQUIERDA, DERECHA
Respuestas:  SI, NO
Especiales:  DESCONOCIDO (cuando no se reconoce nada)
```

---

## Lógica del juego — Simon Dice

### Reglas
1. El sistema genera una secuencia aleatoria de colores/palabras
2. Muestra la secuencia (LEDs + sonido) al jugador
3. El jugador debe repetir la secuencia en orden, hablando
4. Si acierta → la secuencia crece en 1 y sube de nivel
5. Si falla o hay timeout → Game Over
6. El jugador puede decir REPITE para escuchar la secuencia de nuevo (penalización opcional)
7. PAUSA detiene el juego temporalmente

### Máquina de estados
```
IDLE
  ↓ (START)
SHOWING_SEQUENCE     ← muestra LEDs + sonido uno por uno
  ↓
LISTENING            ← espera comando de voz (timeout: 5 segundos)
  ↓
EVALUATING           ← compara con secuencia esperada
  ↓              ↓
CORRECT           WRONG / TIMEOUT
  ↓                  ↓
¿Fin secuencia?    GAME_OVER
  ↓ sí                ↓
LEVEL_UP           IDLE (reinicia)
  ↓
SHOWING_SEQUENCE (secuencia +1)
```

### Configuración del juego
```cpp
TIMEOUT_RESPUESTA  = 5000ms    // tiempo máximo para responder
DURACION_LED       = 800ms     // tiempo que enciende cada LED
PAUSA_ENTRE_LEDS   = 300ms     // pausa entre LEDs de la secuencia
NIVEL_INICIAL      = 1         // longitud inicial de la secuencia
MAX_NIVEL          = 20        // nivel máximo
```

---

## Protocolo Serial ESP32

Formato: texto plano, una línea por mensaje, terminado en `\n`.

### ESP32 → PC / Web Panel
```
READY                          sistema inicializado
STATE:LISTENING                escuchando al jugador
STATE:SHOWING                  mostrando secuencia
STATE:EVALUATING               procesando respuesta
AUDIO:START                    inicio de chunk de audio (Fase 1)
AUDIO:END                      fin de chunk de audio (Fase 1)
DETECTED:<palabra>             palabra detectada (ej: DETECTED:ROJO)
RESULT:CORRECT                 respuesta correcta
RESULT:WRONG                   respuesta incorrecta
RESULT:TIMEOUT                 no habló a tiempo
SEQUENCE:<col1>,<col2>,...     secuencia actual completa
EXPECTED:<palabra>             palabra que se espera en este turno
LEVEL:<n>                      nivel actual
SCORE:<n>                      puntuación actual
GAMEOVER                       fin del juego
```

### PC → ESP32 (solo Fase 1)
```
<PALABRA>\n     ej: ROJO\n, VERDE\n, DESCONOCIDO\n
```

---

## Hardware

### Kit MRD085A
- ESP32-S3 (512KB SRAM + 8MB PSRAM, 240MHz, aceleración vectorial para IA)
- Micrófono: INMP441 I2S digital (SNR 61dB, 16kHz, 16-bit, mono)
- Speaker: amplificador MAX98357A + altavoz pasivo
- WiFi integrado (no usado en este proyecto)

### LEDs del juego
- **No hay LEDs físicos** — los colores se muestran en el Web Panel (componente LEDPanel)
- El firmware envía mensajes `LED:ROJO`, `LED:OFF` por Serial para actualizar el panel

### Pines integrados en el kit MRD085A (⚠️ verificar con esquemático)
```
INMP441 SCK  → ⚠️ verificar (estimado GPIO12)
INMP441 WS   → ⚠️ verificar (estimado GPIO13)
INMP441 SD   → ⚠️ verificar (estimado GPIO11)
MAX98357A BCLK → ⚠️ verificar (estimado GPIO5)
MAX98357A WS   → ⚠️ verificar (estimado GPIO4)
MAX98357A DIN  → ⚠️ verificar (estimado GPIO6)
MAX98357A SD   → ⚠️ verificar (estimado GPIO7)
OLED SDA     → ⚠️ verificar (estimado GPIO21)
OLED SCL     → ⚠️ verificar (estimado GPIO22)
SW1 Volumen+ → ⚠️ verificar (estimado GPIO0)
SW2 Volumen- → ⚠️ verificar (estimado GPIO35)
USB Serial   → cable de flasheo — 921600 baud
```

> IMPORTANTE: Todos los pines GPIO son estimaciones. Verificar con el esquemático del kit MRD085A antes de compilar.

---

## Web Panel — Next.js

### Qué muestra
- Estado actual del juego (ESCUCHANDO, MOSTRANDO SECUENCIA, etc.)
- Palabra detectada en tiempo real
- Resultado de cada turno (correcto / incorrecto / timeout)
- Secuencia actual visual (colores como bloques)
- Nivel y puntuación
- Log en tiempo real de todos los eventos

### Modos de conexión
- **Fase 1:** WebSocket a `ws://localhost:8765` (servidor Python local)
- **Fase 2:** Web Serial API directo al ESP32 desde el browser

### Restricción importante
Web Serial API funciona **solo en Chrome y Edge**. No funciona en Firefox ni Safari.
Documentar esto claramente en la UI del panel.

### Deploy
Vercel. El panel vive en la nube pero la conexión al ESP32 ocurre en el browser del usuario (client-side). No hay backend en Vercel.

---

## Edge Impulse — Plan de entrenamiento

### Datos necesarios
- ~50-100 muestras por palabra (1 segundo cada una)
- Grabar con diferentes personas, tonos y con algo de ruido de fondo
- Incluir clase `noise` (ruido de fondo sin hablar)
- Total estimado: ~600-700 muestras para vocabulario completo

### Proceso
1. Crear cuenta gratis en edgeimpulse.com
2. Nuevo proyecto → tipo Audio (Keyword Spotting)
3. Subir/grabar muestras por clase
4. Crear impulso: MFCC → Red Neuronal
5. Entrenar (< 10 minutos)
6. Validar accuracy (objetivo: > 85%)
7. Exportar como librería Arduino (.zip)
8. Importar en firmware

### Especificaciones del modelo resultante
- Tamaño esperado: ~100-200KB en flash
- Inferencia en ESP32-S3: ~160ms (con aceleración ESP-NN: ~40ms)
- RAM requerida: ~48KB SRAM + ~1.1MB PSRAM

---

## Estructura del proyecto

```
sistemas-inteligentes/
├── firmware/                    ← C++ Arduino
│   ├── simon_dice.ino               ← entry point, setup() y loop()
│   ├── vocabulario.h                ← ÚNICA fuente del vocabulario
│   ├── audio_capture.h/cpp          ← captura I2S, detección VAD
│   ├── serial_comm.h/cpp            ← protocolo Serial (Fase 1)
│   ├── game_engine.h/cpp            ← máquina de estados, lógica
│   ├── led_control.h/cpp            ← control de 4 LEDs
│   ├── sound_control.h/cpp          ← tonos y feedback por speaker
│   └── voice_model.h/cpp            ← inferencia Edge Impulse (Fase 2)
│
├── servidor_pc/                 ← Python, solo Fase 1
│   ├── servidor.py                  ← Serial + Whisper + WebSocket
│   ├── validador.py                 ← normaliza texto → comando válido
│   ├── config.py                    ← puerto COM, configuraciones
│   └── requirements.txt
│
├── web-panel/                   ← Next.js 14 + TypeScript
│   ├── app/
│   │   ├── page.tsx                 ← dashboard principal
│   │   ├── layout.tsx
│   │   └── components/
│   │       ├── GameStatus.tsx       ← estado actual del juego
│   │       ├── SequenceDisplay.tsx  ← visualización de secuencia
│   │       ├── LogConsole.tsx       ← log en tiempo real
│   │       ├── ConnectionPanel.tsx  ← botón conectar WebSocket/Serial
│   │       └── ScoreBoard.tsx       ← nivel y puntuación
│   ├── hooks/
│   │   ├── useWebSocket.ts          ← conexión Fase 1
│   │   └── useWebSerial.ts          ← conexión Fase 2
│   ├── types/
│   │   └── game.ts                  ← tipos TypeScript del protocolo
│   └── package.json
│
├── modelo_voz/                  ← Edge Impulse, Fase 2
│   ├── datos/
│   │   ├── rojo/                    ← archivos .wav
│   │   ├── verde/
│   │   ├── azul/
│   │   ├── amarillo/
│   │   ├── start/
│   │   ├── stop/
│   │   ├── pausa/
│   │   ├── repite/
│   │   ├── reiniciar/
│   │   ├── arriba/
│   │   ├── abajo/
│   │   ├── izquierda/
│   │   ├── derecha/
│   │   ├── si/
│   │   ├── no/
│   │   └── noise/
│   └── exportado/                   ← librería generada por Edge Impulse
│
└── docs/
    ├── arquitectura.md
    ├── setup.md                     ← cómo instalar y correr el proyecto
    └── hardware.md                  ← pinout y conexiones físicas
```

---

## Setup del entorno de desarrollo

### Firmware (ESP32)
```bash
# Instalar Arduino IDE o PlatformIO en Antigravity
# Instalar soporte ESP32 en Arduino: https://espressif.github.io/arduino-esp32/package_esp32_index.json
# Board: ESP32S3 Dev Module
# Upload Speed: 921600
# Flash Size: 16MB (verificar con el kit)
```

### Servidor Python (Fase 1)
```bash
cd servidor_pc
pip install openai-whisper pyserial websockets
# El modelo Whisper base se descarga automáticamente (~74MB) en el primer uso
```

### Web Panel
```bash
cd web-panel
npm install
npm run dev      # desarrollo local en localhost:3000
```

---

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Kit sin documentación clara de pines | Semana 1 dedicada a verificar hardware |
| Whisper lento en PC con CPU débil | Usar modelo `tiny` como fallback |
| Edge Impulse < 85% accuracy | Grabar más muestras, más personas |
| Web Serial API no funciona en Firefox | Documentar en la UI, solo Chrome/Edge |
| Tiempo insuficiente para Fase 2 | Fase 1 ya es proyecto completo y válido |

---

## Reglas de desarrollo

- Todo el firmware en C++, comentado en español
- Vocabulario definido SOLO en `vocabulario.h`
- No hardcodear pines GPIO — usar constantes con nombre descriptivo
- Python server es temporal — no invertir tiempo en hacerlo perfecto
- Web Panel es prioridad media — no bloquea el núcleo del juego
- Commits descriptivos en español
- Probar cada módulo de forma aislada antes de integrarlo

---

## Prioridades de desarrollo

```
ALTA (núcleo del juego)
  1. Verificar hardware: micrófono, LEDs, speaker funcionando
  2. Captura de audio por I2S
  3. Comunicación Serial ESP32 ↔ PC
  4. Servidor Python: Whisper + validador de comandos
  5. Motor del juego: máquina de estados completa
  → FASE 1 LISTA

  6. Recolectar muestras de voz (todo el equipo)
  7. Entrenar modelo en Edge Impulse
  8. Integrar modelo al firmware
  → FASE 2 LISTA

MEDIA (panel web)
  9. Estructura Next.js + tipos TypeScript
  10. Hook useWebSocket (Fase 1)
  11. Dashboard UI completo
  12. Hook useWebSerial (Fase 2)
  13. Deploy en Vercel
  → WEB PANEL LISTO
```
