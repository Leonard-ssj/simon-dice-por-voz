# Setup — Simon Dice por Voz

Guia completa para ejecutar el juego desde cero.

---

## Requisitos previos

| Herramienta | Version minima | Para que |
|---|---|---|
| Python | 3.10 | Servidor PC (Whisper + Serial + WebSocket) |
| Node.js | 18 | Web Panel |
| npm | 9 | Web Panel |
| Chrome o Edge | cualquiera | Web Panel (Web Serial API) |
| Arduino IDE | 2.x | Flashear firmware al ESP32 |
| Hardware | Kit OKYN-G5806 | ESP32-S3-N16R8 + MAX98357A + INMP441 + OLED |

---

## Modo SERVIDOR PC (con ESP32 por USB)

Este es el modo principal del proyecto.
El ESP32 maneja todo el audio (voz + tonos) por su bocina MAX98357A.
Python corre Whisper localmente para reconocer voz.

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd sistemas-inteligentes
```

### 2. Crear el entorno virtual e instalar dependencias

**Opcion A — Script automatico (recomendado):**

```bat
cd servidor_pc
setup.bat
```

El script crea `.venv/` en `servidor_pc/`, instala todas las dependencias
y verifica que los modulos carguen correctamente.

**Opcion B — Manual:**

```bash
cd servidor_pc
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

> El entorno virtual aísla las dependencias del proyecto del Python global.
> `.venv/` está en `.gitignore` y no se sube al repositorio.

Dependencias instaladas:
- `openai-whisper` — reconocimiento de voz local (modelo `small`, ~244 MB, se descarga automatico)
- `pyserial` — comunicacion con el ESP32 por USB
- `websockets` — servidor WebSocket hacia el browser
- `numpy`, `scipy`, `noisereduce` — procesamiento de audio
- `sounddevice` — captura de audio del microfono (solo simulador)

### 3. Preparar los audios PCM (Piper TTS)

Los 59 archivos PCM del narrador se generan con Piper TTS y se suben al ESP32.

**3a. Instalar Piper** (solo la primera vez):

Descargar `piper` para Windows desde:
`https://github.com/rhasspy/piper/releases`

Descomprimir en `test_bocina/piper/` de modo que exista:
```
test_bocina/piper/piper.exe
```

**3b. Descargar el modelo de voz**:

Descargar `es_MX-claude-high.onnx` y su `.json` desde el repositorio de modelos de Piper.
Colocarlos en `test_bocina/`:
```
test_bocina/es_MX-claude-high.onnx
test_bocina/es_MX-claude-high.onnx.json
```

**3c. Generar los audios**:

```bash
cd test_bocina
python preparar_datos.py
```

Esto crea los 59 archivos `.pcm` en `test_bocina/speaker_test/data/`.

### 4. Subir los audios al ESP32

**Cerrar el Serial Monitor del Arduino IDE antes de continuar.**

```bash
cd test_bocina
pip install littlefs-python esptool
python subir_audio.py
```

El script detecta automaticamente el puerto COM del ESP32.
Si hay varios puertos, te pedira elegir.
La subida tarda ~30-60 segundos.

> Este paso solo es necesario la primera vez, o si se actualiza el vocabulario de voz.
> El servidor verifica automaticamente al arrancar: si los audios no estan,
> imprime una advertencia con las instrucciones en la terminal.

### 5. Flashear el firmware al ESP32

Abrir `firmware/proyecto/proyecto.ino` en Arduino IDE.

Configuracion en `Herramientas`:

| Opcion | Valor |
|---|---|
| Board | ESP32S3 Dev Module |
| PSRAM | OPI PSRAM |
| Flash Size | 16MB (128Mb) |
| Partition Scheme | Custom (usa `firmware/proyecto/partitions.csv`) |
| USB CDC on Boot | Enabled |
| Upload Speed | 921600 |

Hacer **Upload** (Ctrl+U).

> **Importante:** La particion "audio" de LittleFS **no se borra** al flashear el firmware.
> Los audios subidos en el paso 4 permanecen intactos.

### 6. Instalar y correr el Web Panel

```bash
cd web-panel
npm install
npm run dev
```

Panel disponible en `http://localhost:3000`.

### 7. Correr el servidor

**Opcion A — Script de inicio (recomendado):**

```bat
cd servidor_pc
iniciar.bat
```

**Opcion B — Manual con venv activo:**

```bash
cd servidor_pc

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

python servidor.py
```

Veras en la terminal:
```
==========================================================
   SIMON DICE POR VOZ - Servidor PC
==========================================================
  1. El ESP32 debe estar conectado por USB.
  2. Abrir Chrome o Edge en:
     http://localhost:3000
  3. Seleccionar el tab  'Servidor PC'
  4. Hacer clic en 'Conectar'  <- el juego inicia aqui
  5. Presionar ESPACIO y hablar
==========================================================

[1/4] Cargando Whisper...
[2/4] Conectando al ESP32...
[Serial] ESP32 listo (READY recibido).
[LittleFS] 59 archivos PCM listos en el ESP32
[3/4] Iniciando servidor WebSocket...
[4/4] Registrando callbacks - esperando conexion del panel web...
```

La bocina del ESP32 dira **"Servidor listo"** al arrancar.

### 8. Conectar y jugar

1. Abre **Chrome o Edge** en `http://localhost:3000`
2. Selecciona el tab **"Servidor PC"**
3. Haz clic en **"Conectar"**
4. La bocina del ESP32 dira **"Simon Dice listo"**
5. Presiona `ESPACIO` y di **"empieza"**
6. Repite los colores: **"rojo"**, **"verde"**, **"azul"**, **"amarillo"**

> **PTT:** mantiene presionado `ESPACIO` mientras hablas, suelta al terminar.
> El servidor graba el audio y Whisper lo transcribe localmente.

---

## Modo SIMULADOR (sin ESP32, para desarrollo)

Corre el juego completo en la PC sin hardware. El audio sale por los speakers de la laptop.

### 1. Instalar dependencias

```bash
cd tests/simulador_pc
pip install -r requirements_test.txt
```

### 2. Correr el simulador

```bash
python main.py
```

### 3. Conectar el panel

1. Abre Chrome o Edge en `http://localhost:3000`
2. Selecciona **"Simulador - WebSocket"**
3. Haz clic en **"Conectar"**

---

## Deploy del Web Panel en Vercel

El panel puede desplegarse en la nube. La conexion al ESP32 y el reconocimiento de voz ocurren en el browser del usuario (client-side).

```bash
cd web-panel
npx vercel
```

---

## Solucion de problemas

| Problema | Causa probable | Solucion |
|---|---|---|
| `[LittleFS] ADVERTENCIA: particion vacia` | Audios no subidos | `cd test_bocina && python subir_audio.py` |
| `[Serial] No se encontro ningun puerto serial` | ESP32 no conectado o driver faltante | Conectar USB, instalar driver CP210x o CH340 |
| `[ERROR] No se pudo cargar Whisper` | openai-whisper no instalado | Ejecutar `setup.bat` de nuevo |
| El ESP32 no aparece en puertos | Cable solo de carga | Usar cable USB con datos |
| La bocina no suena | Audios no subidos o pines incorrectos | Verificar paso 4; pines: BCLK=15, LRC=16, DIN=17 |
| Serial Monitor bloquea la subida | Arduino IDE Serial Monitor abierto | Cerrar Serial Monitor antes de `subir_audio.py` |
| "Web Serial no disponible" | Firefox o Safari | Usar Chrome o Edge |
| Whisper no reconoce el color | Habla despacio y cerca del microfono | Reducir ruido ambiente, verificar microfono en el SO |
| El panel web muestra los LEDs desincronizados | Firmware viejo sin `VOZ_FIN` para colores | Reflashear el firmware actual |
| LittleFS ERROR en OLED | Partition Scheme incorrecto | Elegir "Custom" en Arduino IDE (usa `partitions.csv`) |
| `ModuleNotFoundError` al correr servidor | venv no activado | Usar `iniciar.bat` o activar `.venv` manualmente |
| El venv no existe | `setup.bat` no ejecutado | `cd servidor_pc && setup.bat` |
