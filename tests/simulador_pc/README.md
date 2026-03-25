# Simulador PC — Simon Dice por Voz

Reemplaza el kit ESP32 durante el desarrollo. Corre el juego completo en tu PC:
LEDs simulados en terminal, speaker del sistema, Whisper local para reconocimiento de voz.

---

## Arranque rápido

```bash
# Desde la raíz del proyecto:
cd tests/simulador_pc
pip install -r requirements_test.txt
python main.py

# En otra terminal:
cd web-panel
npm run dev
```

Abre **Chrome o Edge** en `http://localhost:3000`, selecciona **Simulador — WebSocket** y conecta.

---

## Archivos

| Archivo | Rol |
|---|---|
| `main.py` | Entry point. Conecta callbacks entre juego, audio, LEDs y WebSocket |
| `juego_sim.py` | Máquina de estados completa del juego |
| `ws_server.py` | Servidor WebSocket `:8765` + transcripción con Whisper local |
| `audio_pc.py` | Captura de micrófono (sounddevice), TTS (edge-tts / SAPI), tonos |
| `leds_sim.py` | LEDs simulados en terminal con colores ANSI |
| `validador.py` | Normaliza texto de Whisper → comando canónico del juego |
| `config_test.py` | Configuración: timeouts, modelo Whisper, volumen, niveles |

---

## Reglas del juego

1. El sistema genera una secuencia aleatoria de colores
2. Muestra la secuencia al jugador (LEDs + sonido + TTS)
3. El jugador repite la secuencia **en orden**, hablando cada color
4. Si acierta todos los colores → sube de nivel (secuencia crece en 1)
5. Si falla un color o no responde a tiempo → **Game Over**
6. Di **REPITE** para escuchar la secuencia de nuevo
7. Di **PAUSA** para pausar y **EMPIEZA** para reanudar
8. Di **PARA** o **STOP** en cualquier momento para terminar

### Puntuación

```
Acierto de secuencia completa = nivel_actual × 10 puntos
Ejemplo: completar nivel 3 suma 30 puntos
```

---

## Máquina de estados

```
IDLE
  │  START (di "empieza")
  ▼
SHOWING_SEQUENCE   ← muestra LEDs + sonidos uno por uno
  │  secuencia terminada
  ▼
LISTENING          ← espera voz del jugador (timeout: 30s)
  │  PTT_FIN → Whisper transcribe
  ▼
EVALUATING         ← compara respuesta con secuencia esperada
  │
  ├─ correcto + fin de secuencia ──► CORRECT ──► LEVEL_UP ──► SHOWING_SEQUENCE
  │
  ├─ correcto + secuencia incompleta ──► CORRECT ──► LISTENING (siguiente color)
  │
  ├─ incorrecto ──► WRONG ──► GAME_OVER
  │
  └─ timeout ──► GAME_OVER
       │
GAME_OVER ──► IDLE  (di "empieza" para volver)

LISTENING ──► PAUSA  (di "pausa")
PAUSA     ──► LISTENING  (di "empieza" o "pausa")

LISTENING ──► LISTENING  (di "repite" → muestra secuencia de nuevo)
```

---

## Cronología de una partida

```
00:00  python main.py arranca
       → Carga Whisper 'small' (~3-8s en CPU)
       → Servidor WebSocket listo en :8765
       → TTS dice "Simulador listo. Abre el panel web..."

00:10  Panel web conecta
       → TTS dice bienvenida + instrucciones
       → Panel muestra "Conectado"

00:20  Jugador presiona ESPACIO + dice "empieza"
       → Whisper transcribe "empieza" → START
       → Juego: IDLE → SHOWING_SEQUENCE

00:21  Nivel 1 — secuencia: [ROJO]
       → LED ROJO enciende 800ms, se apaga, pausa 300ms
       → TTS dice "Rojo"
       → Juego: SHOWING_SEQUENCE → LISTENING
       → TTS dice "Tu turno. Presiona el botón para hablar."
       → Timer 30s empieza

00:25  Jugador presiona ESPACIO + dice "rojo"
       → Whisper transcribe → ROJO
       → Timer se pausa mientras Whisper procesa
       → Juego: LISTENING → EVALUATING → CORRECT → LEVEL_UP
       → TTS dice "Correcto." luego "Nivel 2."
       → Puntuación +10

00:28  Nivel 2 — secuencia: [ROJO, VERDE]
       → Muestra ROJO, luego VERDE
       → Jugador debe decir ROJO, luego VERDE
       (si falla → WRONG → GAME_OVER)

...    (continúa hasta MAX_NIVEL = 20 o fallo)
```

---

## Comandos de voz

### Colores (respuesta principal del juego)

| Comando | Variantes que acepta Whisper |
|---|---|
| `ROJO` | roja, roxo, ronjo, roco, roso |
| `VERDE` | berde, berdi, verd, erde, birde |
| `AZUL` | asul, azur, asor, asur |
| `AMARILLO` | amarilla, amarijo, marillo, amarilo, marrillo |

### Acciones

| Comando | Variantes | Cuándo usarlo |
|---|---|---|
| `START` | empieza, inicia, comienza, jugar, arranca, empezar, iniciar, comenzar, empieze | IDLE o GAME_OVER — inicia partida |
| `STOP` | para, parar, termina, fin, salir, terminar, detente, alto | Cualquier estado — termina partida |
| `PAUSA` | pausar, espera, esperar | LISTENING — pausa el juego |
| `REPITE` | repetir, repita, repitelo, otra vez, de nuevo | LISTENING — repite la secuencia |
| `REINICIAR` | reinicia, reset, volver, reiniciate | Cualquier estado — reinicia desde nivel 1 |

### Direcciones (para Fase 2 — sin uso en Fase 1)

`ARRIBA`, `ABAJO`, `IZQUIERDA`, `DERECHA`

---

## Cómo funciona el reconocimiento de voz (PTT)

```
1. Jugador presiona ESPACIO (o botón en el panel)
   → Browser envía {"tipo":"ptt_inicio"} por WebSocket
   → Python: pausa el timer del juego
   → Python: abre sounddevice.InputStream (16kHz, mono, float32)

2. Jugador habla el color

3. Jugador suelta ESPACIO
   → Browser envía {"tipo":"ptt_fin"} por WebSocket
   → Python: cierra el micrófono, guarda audio como numpy array

4. Python: transcribe con Whisper local
   → openai-whisper modelo "small"
   → idioma forzado: español
   → initial_prompt: vocabulario del juego (mejora precisión)

5. Resultado: texto crudo → validador.py → comando canónico
   → "empieza" → START
   → "rojo" → ROJO
   → "alucinación larga..." → DESCONOCIDO

6. Python: reanuda el timer del juego
   → Envía voz al panel: {"tipo":"voz", "texto":"rojo", "comando":"ROJO"}
   → Pasa el comando al motor del juego (juego_sim.py)
```

**Fallback WASM:** si Whisper local no cargó, el browser transcribe con
Whisper WASM y envía `{"tipo":"comando", "comando":"ROJO"}` directamente.

---

## Narrador TTS — Cascada de prioridades

El simulador habla con voz neural mexicana cuando es posible:

```
1. edge-tts (internet) → es-MX-DaliaNeural  ← voz neural, mejor calidad
2. SAPI español        → Microsoft Sabina    ← instalada en Windows (MX)
3. SAPI inglés default → cualquier voz       ← último recurso
```

### Frases que dice el simulador

| Momento | Frase |
|---|---|
| Al arrancar | "Simulador listo. Abre el panel web y conecta al simulador." |
| Al conectar panel | "Bienvenido a Simon Dice por Voz. El sistema mostrará una secuencia de colores. Cuando sea tu turno, di el color en voz alta. Para comenzar, presiona el botón del micrófono o la barra espaciadora y di empieza." |
| Mostrando secuencia | "Mira y escucha." |
| Turno del jugador | "Tu turno. Presiona el botón para hablar." |
| Cada color en secuencia | "Rojo." / "Verde." / "Azul." / "Amarillo." |
| Respuesta correcta | "Correcto." |
| Subida de nivel | "Nivel 2." / "Nivel 3." … |
| Respuesta incorrecta | "Incorrecto. Di empieza para intentar de nuevo." |
| Timeout | "Tiempo agotado. Di empieza para intentar de nuevo." |
| Juego pausado | "Juego pausado." |
| Game over | "Fin del juego. Obtuviste N puntos. Di empieza para volver a jugar." |

---

## LEDs simulados en terminal

```
  [ ROJO ]   [      ]   [      ]   [      ]   ← LED ROJO encendido
  [      ]   [ VERDE ]  [      ]   [      ]   ← LED VERDE encendido
```

Los LEDs usan colores ANSI: rojo, verde, azul, amarillo.
En el panel web se reflejan visualmente en tiempo real.

---

## Configuración (`config_test.py`)

| Parámetro | Valor | Descripción |
|---|---|---|
| `WHISPER_MODEL` | `"small"` | Modelo Whisper. `"base"` si la CPU es lenta |
| `TIMEOUT_RESPUESTA` | `30000` ms | Tiempo para responder por turno |
| `DURACION_LED_SIM` | `800` ms | Tiempo que cada LED permanece encendido |
| `PAUSA_ENTRE_LEDS` | `300` ms | Pausa entre LEDs al mostrar secuencia |
| `NIVEL_INICIAL` | `1` | Longitud inicial de la secuencia |
| `MAX_NIVEL` | `20` | Nivel máximo alcanzable |
| `WS_PORT` | `8765` | Puerto WebSocket (panel debe coincidir) |

---

## Protocolo WebSocket (`:8765`)

### Servidor → Panel

```json
{"tipo": "ready",    "whisperDisponible": true, "whisperModelo": "small",
                     "dispositivoMic": "...", "dispositivoSpeaker": "..."}
{"tipo": "state",    "estado": "LISTENING"}
{"tipo": "led",      "color": "ROJO"}
{"tipo": "led",      "color": null}
{"tipo": "sequence", "secuencia": ["ROJO", "VERDE"]}
{"tipo": "expected", "esperado": "VERDE"}
{"tipo": "level",    "nivel": 3}
{"tipo": "score",    "puntuacion": 30}
{"tipo": "result",   "resultado": "CORRECT"}
{"tipo": "voz",      "texto": "rojo", "comando": "ROJO"}
{"tipo": "gameover"}
{"tipo": "log",      "mensaje": "..."}
```

### Panel → Servidor

```json
{"tipo": "ptt_inicio"}
{"tipo": "ptt_fin",   "audio": [0.01, -0.02, ...]}   ← Float32 PCM 16kHz (WASM)
{"tipo": "comando",   "comando": "ROJO"}               ← fallback WASM
```

---

## Dependencias (`requirements_test.txt`)

```
sounddevice     # captura de micrófono del sistema
numpy           # procesamiento de audio PCM
websockets      # servidor WebSocket
pyttsx3         # TTS SAPI fallback (sin internet)
openai-whisper  # reconocimiento de voz local
edge-tts        # TTS neural mexicana (requiere internet)
pygame          # reproducir audio MP3 de edge-tts
```
