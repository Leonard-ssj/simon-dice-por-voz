# Setup — Simon Dice por Voz

## Requisitos generales

| Herramienta | Versión mínima | Para qué |
|---|---|---|
| Node.js | 18 | Web Panel |
| npm | 9 | Web Panel |
| Chrome o Edge | cualquiera | Web Panel (Web Serial API + Whisper WASM) |
| Python | 3.10 | Solo para el simulador PC |

---

## Modo SIMULADOR — Sin hardware (disponible ahora)

El simulador corre el juego completo en tu PC: motor de juego, LEDs en terminal,
tonos y narración TTS por el speaker. El micrófono lo abre Python directamente.

### 1. Instalar dependencias Python

```bash
cd tests/simulador_pc
pip install -r requirements_test.txt
```

Instala:
- `sounddevice` — tonos del juego y captura del micrófono (PTT)
- `numpy` — procesamiento de audio
- `websockets` — servidor WebSocket hacia el browser
- `pyttsx3` — detecta voces instaladas en Windows (solo enumeración)
- `openai-whisper` — reconocimiento de voz local (modelo `small`, ~244 MB, se descarga automático)
- `edge-tts` — voz neural mexicana `es-MX-DaliaNeural` para el narrador (requiere internet)
- `pygame` — reproducción del audio de edge-tts

> **Nota:** `edge-tts` y `pygame` son opcionales. Si no están, el narrador usa
> las voces SAPI instaladas en Windows (PowerShell). Si no hay voz en español,
> el narrador suena en inglés.

### 2. Instalar y correr el Web Panel

```bash
cd web-panel
npm install
npm run dev
```

Panel disponible en `http://localhost:3000`

### 3. Correr el simulador

```bash
cd tests/simulador_pc
python main.py
```

Verás en la terminal:
```
=======================================================
  SIMON DICE POR VOZ — Simulador PC (modo TEST)
=======================================================
[TTS] Edge TTS activo — voz neural: es-MX-DaliaNeural
[WS] Cargando Whisper 'small'...
[WS] Whisper 'small' listo.
[WS] Servidor en ws://localhost:8765
  Simulador listo. Esperando conexion del panel web...
```

### 4. Conectar el panel y jugar

1. Abre **Chrome o Edge** en `http://localhost:3000`
2. Selecciona **"Simulador — WebSocket"** (ya está seleccionado por defecto)
3. Click **"Conectar"**
4. El panel mostrará en la barra inferior: micrófono, bocina y modelo Whisper activos
5. Di **"empieza"** presionando `ESPACIO` o el botón 🎤
6. Repite los colores: **"rojo"**, **"verde"**, **"azul"**, **"amarillo"**

> **PTT — Push to Talk:** mantén presionado `ESPACIO` o el botón 🎤 mientras hablas.
> Suéltalo cuando termines. Python graba el audio y Whisper lo transcribe.

### Detección automática de Whisper

Al conectar, el panel muestra qué Whisper está en uso:

| Badge en panel | Qué significa |
|---|---|
| 🔵 **Whisper local** | Python captura el mic y transcribe con Whisper local |
| 🟢 **Whisper listo** | WASM cargado en el browser (fallback) |
| 🟡 **Descargando modelo...** | WASM descargándose (~125 MB, primera vez) |

### Comandos de voz reconocidos

| Dices | Comando | Válido en |
|---|---|---|
| empieza / inicia / comienza | START | IDLE, GAMEOVER, PAUSA |
| rojo / roja / roxo | ROJO | LISTENING |
| verde / berde / verd | VERDE | LISTENING |
| azul / asul / azur | AZUL | LISTENING |
| amarillo / amarilla / amarijo | AMARILLO | LISTENING |
| repite / de nuevo / otra vez | REPITE | LISTENING |
| pausa / pausar / espera | PAUSA | LISTENING |
| para / stop / termina | STOP | cualquier momento |
| reinicia / reiniciar / reset | REINICIAR | GAMEOVER |

---

## Modo HARDWARE — Con ESP32

Requiere el kit OKYN-G5806 (ESP32-S3 + INMP441 + MAX98357A) conectado por USB.
**No se necesita instalar Python** — solo Chrome o Edge.

### 1. Flashear el firmware

```
Arduino IDE:
  Board:        ESP32S3 Dev Module
  Upload Speed: 921600
  Flash Size:   16MB
```

**Antes de compilar:** verificar pines en:
- `firmware/led_control.h` — `PIN_LED_ROJO`, `PIN_LED_VERDE`, `PIN_LED_AZUL`, `PIN_LED_AMARILLO`
- `firmware/audio_capture.h` — `I2S_SCK_PIN`, `I2S_WS_PIN`, `I2S_SD_PIN`
- `firmware/sound_control.h` — `PIN_SPEAKER_PWM`

Abrir `firmware/simon_dice.ino` en Arduino IDE y hacer Upload.

### 2. Abrir el Web Panel

Opción A — Local:
```bash
cd web-panel
npm install
npm run dev
# Abrir http://localhost:3000 en Chrome o Edge
```

Opción B — Producción (Vercel):
```bash
cd web-panel
npx vercel
# El panel queda en la nube, accesible desde cualquier Chrome/Edge
```

### 3. Conectar y jugar

1. Conecta el ESP32 al USB
2. Abre el panel en Chrome o Edge
3. Selecciona **"ESP32 — Web Serial"**
4. Click **"Conectar"** → selecciona el puerto serial del ESP32
5. Espera el badge **"Whisper listo"** (~125 MB primera descarga, luego desde caché)
6. Di **"empieza"** presionando `ESPACIO` o el botón 🎤 → juega

> **Requisito:** Web Serial API solo funciona en Chrome y Edge.
> Firefox, Safari y otros browsers no son compatibles.

---

## Deploy en Vercel

```bash
cd web-panel
npx vercel
```

El panel vive en la nube. La conexión al ESP32 y el reconocimiento de voz ocurren
completamente en el browser del usuario (client-side). No hay backend en Vercel.

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| "Web Serial no disponible" | Browser no es Chrome/Edge | Usar Chrome o Edge |
| El panel no se conecta al simulador | El simulador no está corriendo | Ejecutar `python main.py` primero |
| Whisper no reconoce lo que dices | Habla despacio y claro | Revisar volumen del micrófono en el SO |
| `RuntimeError: Event loop is closed` en terminal | Advertencia benigna de Windows/asyncio | Ya corregido — ignorar |
| Error 503 en edge-tts | Sin internet o servicio no disponible | Cae automáticamente a SAPI; sin impacto |
| Narrador TTS habla en inglés (SAPI) | No hay voz en español instalada | Configuración → Hora e idioma → Voz → Agregar voces (buscar Sabina o Helena) |
| "Cargando modelo..." no termina (WASM) | Conexión a internet lenta | Esperar (solo la primera vez, ~125 MB) |
| El ESP32 no aparece en la lista de puertos | Driver no instalado o cable solo carga | Usar cable de datos, instalar driver CP210x o CH340 |
| PTT no funciona (botón no responde) | Simulador no envió READY | Reconectar; verificar que el simulador Python esté corriendo |
