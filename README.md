# Simon Dice por Voz 🎮🎤

Juego Simon Dice controlado completamente por voz en español.
Proyecto universitario de la materia **Sistemas Inteligentes**.

El reconocimiento de voz corre **en el browser** usando Whisper WASM
(sin servidores externos, sin Python, sin internet después de la primera carga).

---

## Cómo funciona

```
Micrófono → Whisper WASM (browser)
                ↓
         comando de voz
                ↓
  ┌─────────────────────────────┐
  │  Simulador PC (pruebas)     │  via WebSocket
  │  Python: juego + TTS + tonos│ ← "ROJO\n" {"tipo":"comando"}
  └─────────────────────────────┘
           — ó —
  ┌─────────────────────────────┐
  │  ESP32-S3 (producción)      │  via Web Serial
  │  Firmware C++: LEDs + buzzer│ ← "ROJO\n"
  └─────────────────────────────┘
```

El panel web vive en Vercel. La conexión al ESP32 o al simulador ocurre
en el browser del usuario — no hay backend.

---

## Estructura del proyecto

```
sistemas-inteligentes/
├── firmware/          ← C++ Arduino para el ESP32-S3
├── tests/
│   └── simulador_pc/  ← Python: corre el juego en la PC (pruebas)
├── web-panel/         ← Next.js 14 + TypeScript (Vercel)
├── modelo_voz/        ← datos y modelo Edge Impulse (Fase 2)
└── docs/              ← documentación técnica
```

---

## Inicio rápido

### 1. Modo Simulador (sin ESP32)

```bash
# Terminal 1 — Simulador Python
cd tests/simulador_pc
pip install -r requirements_test.txt
python main.py

# Terminal 2 — Panel web
cd web-panel
npm install
npm run dev
```

Abre **Chrome o Edge** en `http://localhost:3000`.
Haz clic en **"Conectar al Simulador"**.
Espera a que el modelo Whisper descargue (~125 MB, solo la primera vez).
Di **"empieza"** para comenzar.

### 2. Modo ESP32 (producción)

```bash
cd web-panel
npm run dev
```

Abre `http://localhost:3000` en Chrome o Edge.
Haz clic en **"Conectar al ESP32"** y selecciona el puerto USB.

---

## Hardware

- **Kit OKYN-G5806**: ESP32-S3 + micrófono INMP441 + speaker MAX98357A
- 4 LEDs (rojo, verde, azul, amarillo) + resistencias 220Ω

El ESP32 **no graba audio**. Solo recibe comandos de texto por Serial
(`ROJO\n`, `START\n`, etc.) y controla los LEDs y el buzzer.

---

## Vocabulario

| Categoría | Palabras |
|-----------|----------|
| Colores   | ROJO, VERDE, AZUL, AMARILLO |
| Acciones  | START (empieza), STOP (para), PAUSA, REPITE, REINICIAR |
| Respuestas| SI, NO |

Whisper entiende variantes fonéticas: "inicia", "comienza", "empieze" → START.

---

## Modelo de IA

**Whisper Small** (`onnx-community/whisper-small`, ~125 MB quantizado)
corriendo en el browser via WebAssembly (ONNX Runtime Web).

- Sin internet después de la primera descarga (caché IndexedDB)
- ~1-3 segundos por transcripción en CPU moderna
- Idioma: español

---

## Tecnologías

| Componente | Tecnología |
|---|---|
| Firmware ESP32 | Arduino (C++) |
| Simulador PC | Python 3.11 |
| Reconocimiento de voz | Whisper WASM (`@huggingface/transformers` v3) |
| Panel web | Next.js 14 + TypeScript |
| Deploy | Vercel |
| Narrador (simulador) | pyttsx3 |

---

## Notas

- Web Serial API requiere **Chrome o Edge** (no funciona en Firefox/Safari)
- El simulador Python reemplaza el ESP32 en pruebas — misma interfaz de comandos
- El vocabulario vive en `firmware/vocabulario.h` (única fuente de verdad)
