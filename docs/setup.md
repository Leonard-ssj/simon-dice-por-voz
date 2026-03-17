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

Usa el speaker de tu PC para sonidos y TTS. El browser hace el reconocimiento de voz.
No requiere el kit ESP32.

### 1. Instalar dependencias Python

```bash
cd tests/simulador_pc
pip install -r requirements_test.txt
```

Instala: `sounddevice`, `numpy`, `websockets`, `pyttsx3`

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
  Abre el panel en Chrome/Edge para jugar:
  → http://localhost:3000
=======================================================
```

### 4. Conectar el panel y jugar

1. Abre **Chrome o Edge** en `http://localhost:3000`
2. El panel mostrará "Cargando modelo..." mientras descarga Whisper (~125 MB, solo la primera vez)
3. Cuando aparezca **"Whisper listo"**, click **Conectar al Simulador**
4. Di **"empieza"** o **"inicia"** → el juego comienza
5. Repite los colores: **"rojo"**, **"verde"**, **"azul"**, **"amarillo"**

> **El browser hace todo el reconocimiento de voz.** El simulador Python solo corre
> el motor del juego, simula los LEDs en la terminal y reproduce tonos y narración.

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
| para / stop / termina / fin | STOP | cualquier momento |
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
3. Espera el badge **"Whisper listo"** (~125 MB primera descarga, luego desde caché)
4. Click en el toggle **"ESP32 — Web Serial"**
5. Click **"Conectar"** → selecciona el puerto serial del ESP32
6. Di **"empieza"** → juega

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
| "Cargando modelo..." no termina | Conexión a internet lenta | Esperar (solo la primera vez, ~125 MB) |
| El ESP32 no aparece en la lista de puertos | Driver no instalado o cable solo carga | Usar cable de datos, instalar driver CP210x o CH340 |
| Narrador TTS habla en inglés | No hay voz en español instalada | Configuración → Hora e idioma → Voz → Agregar voces |
