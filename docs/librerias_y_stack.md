# Librerías y Stack Tecnológico — Simon Dice por Voz

Documentación completa de cada librería, framework y herramienta del proyecto,
con explicación de por qué se usa y en qué parte del código aparece.

---

## 1. Firmware ESP32 (`firmware/proyecto/proyecto.ino`)

El firmware está escrito en **C++ con el framework Arduino sobre ESP-IDF**.
No contiene lógica de juego — solo maneja hardware: captura audio, controla el OLED, el RGB y envía datos por Serial.

### Librerías de Arduino

| Librería | Versión | Instalar desde |
|----------|---------|----------------|
| Adafruit SSD1306 | ≥ 2.5 | Arduino Library Manager |
| Adafruit GFX Library | ≥ 1.11 | Arduino Library Manager |
| Adafruit NeoPixel | ≥ 1.12 | Arduino Library Manager |

---

#### `Wire.h` — I2C (incluida en el core ESP32)
- **Qué es**: protocolo de comunicación en bus de 2 hilos (SDA + SCL).
- **Por qué**: el OLED SSD1306 se comunica por I2C.
- **Dónde**: `Wire.begin(OLED_SDA, OLED_SCL)` en `setup()`.
- **Pines**: SDA=GPIO10, SCL=GPIO11.

---

#### `Adafruit_GFX.h` — Motor gráfico 2D
- **Qué es**: librería base de Adafruit que provee primitivas gráficas: texto, líneas, rectángulos, bitmaps.
- **Por qué**: es la dependencia requerida por `Adafruit_SSD1306`. No se usa directamente en el código.
- **Dónde**: include implícito — `Adafruit_SSD1306` la hereda.

---

#### `Adafruit_SSD1306.h` — Driver OLED
- **Qué es**: driver para la pantalla OLED SSD1306 (128×32 px o 128×64 px).
- **Por qué**: el kit tiene un OLED integrado de 128×32 que muestra estado del juego (nivel, puntos, mensajes).
- **Dónde**: `oled_mostrar(l1, l2, l3)` — imprime 3 líneas de texto.
- **Ejemplo de uso**:
  ```cpp
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("TU TURNO");
  display.display();
  ```

---

#### `Adafruit_NeoPixel.h` — LED RGB WS2812B
- **Qué es**: librería para LEDs NeoPixel (WS2812B) — control de color RGB individual por un solo pin de datos.
- **Por qué**: el ESP32-S3 del kit tiene un WS2812B integrado en GPIO48. Lo usamos para indicar colores del juego (rojo, verde, azul, amarillo) y estado (grabando = rojo pulsante).
- **Dónde**: `set_color(r, g, b)` → `pixel.setPixelColor(0, ...)` → `pixel.show()`.
- **Ejemplo de uso**:
  ```cpp
  pixel.setPixelColor(0, pixel.Color(255, 0, 0)); // rojo
  pixel.show();
  ```

---

#### `driver/i2s.h` — I2S para speaker MAX98357A (ESP-IDF)
- **Qué es**: driver de hardware del ESP-IDF para el protocolo I2S (Inter-IC Sound) — transmisión digital de audio.
- **Por qué**: el amplificador MAX98357A recibe audio digital por I2S desde el ESP32. Usado para reproducir tonos de juego directamente en el speaker.
- **Dónde**: `iniciar_i2s_speaker()` en `setup()`, `reproducir_tono_i2s(freq, ms)` para tonos.
- **Pines**: BCLK=GPIO6, WS/LRC=GPIO5, DIN=GPIO7.
- **Nota**: es la API de bajo nivel de Espressif (no una librería de Arduino). Viene incluida con el SDK de ESP32.

---

#### `math.h` — Matemáticas (C estándar)
- **Qué es**: librería estándar de C para funciones matemáticas.
- **Por qué**: necesaria para `sinf()` al generar ondas sinusoidales para los tonos I2S.
- **Dónde**: `reproducir_tono_i2s()` — genera muestras PCM de una onda seno.

---

### Técnicas de firmware propias (sin librería externa)

| Técnica | Descripción |
|---------|-------------|
| ADC oversample ×4 | Lee GPIO4 (MAX4466) 4 veces y promedia → reduce ruido ADC de 12 bits |
| HPF biquad digital | Filtro pasa-altas 80Hz en software (coeficientes precalculados) — elimina DC offset |
| LPF biquad digital | Filtro pasa-bajas 4000Hz en software — elimina aliasing |
| Protocolo Serial texto | `OLED:l1\|l2\|l3`, `LED:COLOR`, `R`/`T` para PTT — texto plano una línea por mensaje |

---

## 2. Servidor Python (`servidor_pc/`)

El servidor Python es el cerebro del sistema en Fase 1. Conecta el ESP32 (Serial) con el panel web (WebSocket), procesa el audio con Whisper y controla la lógica del juego.

---

### `openai-whisper`
- **Qué es**: implementación oficial de OpenAI de Whisper — modelo de reconocimiento de voz (ASR) de código abierto. Corre localmente, sin internet.
- **Por qué**: reconocimiento de voz en español de alta calidad. Soporta múltiples modelos (`tiny`, `base`, `small`, `medium`) con balance velocidad/calidad. El proyecto usa `small` (~244MB).
- **Dónde**: `whisper_engine.py` → `whisper.load_model("small")` → `modelo.transcribe(audio_16k)`.
- **Parámetros clave usados**:
  ```python
  modelo.transcribe(
      audio,
      language="es",         # forzar español
      temperature=0.0,       # determinista (sin aleatoriedad)
      fp16=False,            # CPU (fp16 es solo GPU)
      beam_size=5,           # búsqueda de haz — mayor calidad
      no_speech_threshold=0.50,  # umbral para detectar silencio
  )
  ```
- **Velocidad real**: modelo `small` en CPU → ~3-8 segundos por transcripción.

---

### `numpy`
- **Qué es**: librería fundamental de Python para computación numérica — arrays multidimensionales y operaciones matemáticas vectorizadas.
- **Por qué**: el audio PCM del ESP32 llega como bytes crudos `int16`. Numpy convierte esos bytes a arrays float32 para aplicar filtros y calcular métricas.
- **Dónde**: `whisper_engine.py` en cada etapa del pipeline:
  ```python
  muestras = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
  rms = float(np.sqrt(np.mean(muestras ** 2)))  # detección de silencio
  ```

---

### `scipy`
- **Qué es**: librería científica de Python. Usamos específicamente `scipy.signal` para DSP (procesamiento de señal digital).
- **Por qué**: implementa filtros IIR (Butterworth) y resampling de alta calidad que no están en numpy base.
- **Dónde**: `whisper_engine.py` — pipeline de preprocesamiento de audio:
  ```python
  # Filtro pasa-altas 80Hz (elimina ruido de baja frecuencia)
  b, a = sp_signal.butter(2, 80.0 / (8000/2), btype="high")
  muestras = sp_signal.filtfilt(b, a, muestras)   # fase cero (filtfilt)

  # Filtro pasa-bajas 3400Hz (banda de voz)
  b, a = sp_signal.butter(2, 3400.0 / (8000/2), btype="low")
  muestras = sp_signal.filtfilt(b, a, muestras)

  # Resample 8kHz → 16kHz (Whisper requiere 16kHz)
  muestras_16k = sp_signal.resample(muestras, n_destino)
  ```
- **Por qué `filtfilt` y no `lfilter`**: `filtfilt` aplica el filtro dos veces (ida y vuelta) → fase cero, sin distorsión temporal de la señal de voz.

---

### `noisereduce`
- **Qué es**: librería de sustracción espectral de ruido estacionario — reduce ruido de fondo constante (ventiladores, ADC noise floor).
- **Por qué**: el MAX4466 (micrófono analógico) introduce más ruido que un micrófono I2S digital. `noisereduce` estima el perfil de ruido estacionario y lo sustrae del espectro.
- **Dónde**: `whisper_engine.py` capa 3 del pipeline:
  ```python
  muestras = nr.reduce_noise(
      y=muestras, sr=8000,
      stationary=True,       # ruido constante (ADC floor)
      prop_decrease=0.55,    # reducción del 55% del ruido
  )
  ```

---

### `pyserial`
- **Qué es**: librería para comunicación por puerto Serial (UART/USB-CDC) en Python.
- **Por qué**: el ESP32 se conecta al PC por USB y expone un puerto COM (CH340/CP210x). Toda la comunicación ESP32↔Python pasa por aquí — comandos de texto y bloques de audio PCM.
- **Dónde**: `serial_bridge.py`:
  ```python
  self._serial = serial.Serial(port, 921600, timeout=0.1)
  self._serial.write(b"R")          # iniciar grabación
  datos = self._serial.read(1024)   # leer audio PCM
  ```
- **Detección automática de puerto**: `SerialBridge` detecta el primer dispositivo ESP32/CH340/CP210x conectado sin necesidad de especificar el COM manualmente.

---

### `websockets` (≥ 14)
- **Qué es**: implementación Python del protocolo WebSocket (RFC 6455) — comunicación bidireccional en tiempo real sobre TCP.
- **Por qué**: el panel web (Next.js) necesita recibir eventos del juego en tiempo real (estado, LEDs, resultados) y enviar señales PTT. WebSocket es la opción estándar para esto.
- **Dónde**: `ws_server.py` — servidor asyncio:
  ```python
  async with websockets.asyncio.server.serve(handler, "localhost", 8766):
      await asyncio.Future()  # corre indefinidamente
  ```
- **Por qué versión ≥ 14**: la API `websockets.asyncio.server` (más moderna y estable) solo existe desde v14.

---

### `sounddevice`
- **Qué es**: binding de Python para PortAudio — reproducción y captura de audio usando el dispositivo de audio del sistema.
- **Por qué**: reproduce los tonos del juego (Do, Mi, Sol, Si para los 4 colores) directamente por el altavoz de la laptop como feedback de audio durante SHOWING_SEQUENCE.
- **Dónde**: `tts.py` → `reproducir_sonido(tipo, extra)` genera una onda sinusoidal numpy y la reproduce:
  ```python
  muestras = np.sin(2 * np.pi * freq * t) * VOLUMEN_TONOS
  sd.play(muestras, samplerate=44100)
  sd.wait()
  ```

---

### `edge-tts`
- **Qué es**: cliente Python no oficial de Microsoft Edge Text-to-Speech — usa las voces neurales de Azure TTS con calidad muy alta.
- **Por qué**: la voz `es-MX-DaliaNeural` suena natural en español mexicano. Requiere internet solo para generar el audio, que luego se reproduce localmente con pygame.
- **Dónde**: `tts.py` → `_hablar_edge(texto)`:
  ```python
  communicate = edge_tts.Communicate(texto, voice="es-MX-DaliaNeural")
  await communicate.save("/tmp/tts.mp3")
  pygame.mixer.music.load("/tmp/tts.mp3")
  pygame.mixer.music.play()
  ```
- **Fallback**: si `edge-tts` no está disponible o no hay internet → usa `pyttsx3` con SAPI de Windows.

---

### `pyttsx3`
- **Qué es**: motor TTS (Text-to-Speech) multiplataforma que usa las voces del sistema operativo (SAPI en Windows, espeak en Linux).
- **Por qué**: fallback offline para cuando `edge-tts` no está disponible. Sin dependencia de internet.
- **Dónde**: `tts.py` → `_hablar_powershell(texto)` (en realidad usa un subprocess de PowerShell con SAPI directamente para evitar bloqueos de threading de pyttsx3).

---

### `pygame`
- **Qué es**: librería multimedia de Python — originalmente para videojuegos, usamos solo el módulo `pygame.mixer` para reproducción de audio MP3.
- **Por qué**: `edge-tts` genera archivos MP3 temporales que necesitan ser reproducidos. `pygame.mixer` es la forma más sencilla de reproducir MP3 en Python sin dependencias pesadas.
- **Dónde**: `tts.py` → reproducción del audio generado por `edge-tts`.

---

### Librerías estándar de Python (sin instalación)

| Librería | Uso |
|----------|-----|
| `threading` | Hilos concurrentes — tick, TTS worker, secuencia, Whisper |
| `asyncio` | Event loop del servidor WebSocket |
| `time` | Timeouts, sleeps, medición de tiempos |
| `json` | Serialización de mensajes WebSocket |
| `queue` | Cola thread-safe para TTS y WebSocket broadcast |
| `unicodedata` | Normalización de texto (quitar acentos) en validador.py |
| `re` | Expresiones regulares para limpiar texto en validador.py |
| `difflib.SequenceMatcher` | Fuzzy matching fonético en validador.py |
| `collections.Counter` | Detección de alucinaciones repetitivas de Whisper |
| `random` | Generación de secuencias aleatorias de colores |
| `enum` | Definición de estados del juego (`Estado.LISTENING`, etc.) |
| `sys`, `os` | Manipulación de rutas y paths para imports entre módulos |

---

## 3. Panel Web (`web-panel/`)

El panel web está construido con **Next.js 14** (React) y **TypeScript**. Corre completamente en el browser del usuario — no hay backend propio, toda la lógica es client-side.

---

### `next` (14.2.3)
- **Qué es**: framework React para producción — App Router, SSR/SSG, optimizaciones automáticas.
- **Por qué**: estructura moderna de React con soporte nativo para TypeScript, rutas basadas en archivos y builds optimizados para Vercel.
- **Dónde**: toda la aplicación vive en `app/` — `page.tsx` es el dashboard principal.
- **Características usadas**: App Router (`"use client"`), `layout.tsx` para el shell, imports automáticos de CSS.

---

### `react` + `react-dom` (18)
- **Qué es**: librería de UI declarativa basada en componentes y estado reactivo.
- **Por qué**: base de Next.js. Los componentes del panel (`GameStatus`, `LEDPanel`, `LogConsole`, etc.) son componentes React con hooks.
- **Hooks usados**: `useState`, `useEffect`, `useRef`, `useCallback` — todos en `useWebSocket.ts` y `useWhisperWASM.ts`.

---

### `@huggingface/transformers` (3.5.0)
- **Qué es**: librería de Hugging Face para ejecutar modelos de Machine Learning directamente en el browser usando ONNX Runtime Web (WebAssembly + WebGPU).
- **Por qué**: modo fallback WASM — si el servidor Python no tiene Whisper, el browser puede transcribir audio localmente usando Whisper WASM cuantizado (~125MB descargado una vez a IndexedDB).
- **Dónde**: `hooks/useWhisperWASM.ts`:
  ```typescript
  const pipe = await pipeline("automatic-speech-recognition", 
      "onnx-community/whisper-small", { dtype: "q4" });
  const result = await pipe(audioBuffer, { language: "spanish" });
  ```
- **Nota**: solo se carga si el servidor Python reporta `whisperDisponible: false` en el mensaje `ready`.

---

### `framer-motion` (12.x)
- **Qué es**: librería de animaciones para React — animaciones declarativas, gestos, transiciones entre estados.
- **Por qué**: las transiciones visuales del juego (LED activo, cambio de estado, resultado correcto/incorrecto) se animan suavemente sin escribir CSS de animación manual.
- **Dónde**: componentes del dashboard — el LED panel anima el encendido/apagado de colores, el estado del juego hace fade in/out.

---

### `lucide-react` (0.577)
- **Qué es**: librería de iconos SVG para React — ~1500 iconos listos como componentes.
- **Por qué**: íconos del panel: micrófono, conectar/desconectar, nivel, puntuación, log, etc. SVG puro = escalable sin perder calidad.
- **Dónde**: componentes UI del dashboard — `<Mic />`, `<Wifi />`, `<Trophy />`, etc.

---

### `tailwindcss` (3.3)
- **Qué es**: framework CSS utility-first — clases atómicas directamente en el HTML/JSX en lugar de escribir CSS separado.
- **Por qué**: desarrollo rápido de UI sin cambiar entre archivos `.css`. El output final solo incluye las clases usadas (tree-shaking automático).
- **Dónde**: todo el panel usa clases Tailwind directamente en JSX:
  ```tsx
  <div className="flex items-center gap-2 rounded-xl bg-zinc-900 p-4 text-white">
  ```

---

### `@radix-ui/react-scroll-area` + `@radix-ui/react-slot`
- **Qué es**: componentes UI accesibles sin estilo (headless) de Radix UI — construidos sobre ARIA y accesibilidad por defecto.
- **Por qué**:
  - `react-scroll-area`: el log en tiempo real necesita scroll suave con scrollbar personalizado (los scrollbars nativos no son estilizables cross-browser).
  - `react-slot`: permite que componentes wrapper pasen sus props al hijo directo (patrón de composición de shadcn/ui).
- **Dónde**: `LogConsole` usa `ScrollArea` para el log de eventos, componentes de botones usan `Slot`.

---

### `clsx` + `tailwind-merge`
- **Qué es**:
  - `clsx`: combina strings de clases CSS condicionalmente (`clsx("base", condition && "extra")`).
  - `tailwind-merge`: cuando se combinan clases Tailwind conflictivas (`p-2 p-4`), resuelve automáticamente cuál gana en lugar de duplicar.
- **Por qué**: en componentes con props de className variable es fácil tener conflictos de clases Tailwind. Estos dos juntos forman el patrón estándar de shadcn/ui.
- **Dónde**: función `cn()` usada en casi todos los componentes:
  ```typescript
  export function cn(...inputs: ClassValue[]) {
      return twMerge(clsx(inputs));
  }
  ```

---

### `class-variance-authority` (CVA)
- **Qué es**: librería para definir variantes de componentes con type-safety — similar a como Tailwind define variantes de color/tamaño.
- **Por qué**: los botones, badges y chips del panel tienen múltiples variantes (tamaño, color, estado). CVA define esas variantes con tipos TypeScript correctos.
- **Dónde**: componentes base como `Button`, `Badge` — define variantes `default`, `destructive`, `outline`, etc.

---

### TypeScript (5.x)
- **Qué es**: superset tipado de JavaScript — añade tipos estáticos que se comprueban en tiempo de compilación.
- **Por qué**: el protocolo WebSocket tiene ~12 tipos de mensaje distintos. Sin tipos, cualquier typo en `msg.tipo` o acceso a campo incorrecto pasa desapercibido. Con TypeScript se detectan en el editor.
- **Dónde**: `types/game.ts` define el tipo `MensajeWS` como unión discriminada:
  ```typescript
  type MensajeWS =
    | { tipo: "state"; estado: EstadoJuego }
    | { tipo: "voz"; texto: string; comando: string }
    | { tipo: "tts"; activo: boolean }
    // ... 9 tipos más
  ```

---

### `postcss` + `autoprefixer`
- **Qué es**: herramientas de transformación de CSS.
  - `postcss`: procesador de CSS que aplica plugins.
  - `autoprefixer`: añade prefijos CSS (`-webkit-`, `-moz-`) automáticamente para compatibilidad cross-browser.
- **Por qué**: requerido por Tailwind CSS para funcionar con Next.js.
- **Dónde**: configuración en `postcss.config.js` — transparente al desarrollador.

---

### DevDependencies de TypeScript

| Paquete | Para qué |
|---------|----------|
| `@types/node` | Tipos para APIs de Node.js (usado por Next.js en build) |
| `@types/react` | Tipos para React — props, eventos, hooks |
| `@types/react-dom` | Tipos para ReactDOM — render, portals |

---

## 4. Stack de comunicación entre capas

```
ESP32 (C++)
    │
    │  USB Serial 921600 baud
    │  Protocolo: texto plano + binario PCM
    │
Python Servidor (pyserial)
    │
    │  WebSocket ws://localhost:8766
    │  Protocolo: JSON (mensajes tipados)
    │
Next.js Panel (websockets hook)
    │
    │  (solo si Whisper local no disponible)
    │  ONNX Runtime Web (@huggingface/transformers)
    │
Whisper WASM (fallback, en browser)
```

---

## 5. Pipeline de audio — capas de procesamiento

| Capa | Librería | Transformación |
|------|----------|---------------|
| 0. Captura ADC | Firmware ESP32 (nativa) | GPIO4 → int16, 8kHz, oversample ×4 |
| 1. HPF 80Hz | `scipy.signal.butter` + `filtfilt` | Elimina DC offset y ruido sub-80Hz |
| 2. LPF 3400Hz | `scipy.signal.butter` + `filtfilt` | Limita a banda de voz telefónica |
| 3. Noise reduce | `noisereduce` | Sustracción espectral ruido estacionario |
| 4. Normalización | `numpy` | Pico normalizado al 90% |
| 5. Resample | `scipy.signal.resample` | 8000Hz → 16000Hz (Whisper requiere 16kHz) |
| 6. ASR | `openai-whisper` | float32 PCM 16kHz → texto en español |
| 7. Normalización texto | `unicodedata`, `re` (stdlib) | Quitar acentos, puntuación, mayúsculas |
| 8. Mapeo a comando | `validador.py` + `difflib` | Texto → comando canónico (AZUL, ROJO…) |
| 9. Multi-color | `validador.texto_a_colores` | Texto → lista de colores en orden |
