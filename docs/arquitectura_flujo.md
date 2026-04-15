# Arquitectura y Flujo — Simon Dice por Voz

## Diagrama 1: Flujo de una ronda completa (camino feliz)

```mermaid
sequenceDiagram
    actor Usuario
    participant Panel as Web Panel<br/>(Next.js)
    participant Python as Servidor PC<br/>(Python)
    participant ESP32
    participant Whisper
    participant Juego as Motor Juego<br/>(juego_sim.py)
    participant TTS

    Note over Panel,TTS: === CONEXIÓN ===
    Usuario->>Panel: Clic "Conectar"
    Panel->>Python: WebSocket connect ws://localhost:8766
    Python->>Panel: WS: {tipo:"ready", whisperDisponible:true, tiempoTimeout:60000}
    Python->>Juego: juego.iniciar() → estado IDLE
    Python->>Panel: WS: {tipo:"state", estado:"IDLE"}
    Python->>TTS: decir("Simon Dice listo. Presiona ESPACIO...")

    Note over Panel,TTS: === INICIO DE RONDA ===
    Usuario->>Panel: Presiona ESPACIO
    Panel->>Python: WS: {tipo:"control", accion:"PTT_INICIO"}
    Python->>Juego: pausar_timeout()
    Python->>Python: _verificar_condiciones_ptt()

    alt TTS hablando
        Python->>Panel: WS: enviar_log("Espera al narrador...")
        Note over Python: timer sigue pausado — _hilo_tick no avanza<br/>mientras tts_hablando()=True
    else SHOWING_SEQUENCE activo
        Python->>Panel: WS: enviar_log("Mira la secuencia")
        Note over Python: timer no aplica — estado ≠ LISTENING
    else Condiciones OK
        Python->>Python: _ptt_spacebar_activo = True
        Python->>ESP32: Serial: 'R'
        ESP32->>ESP32: iniciar_grabacion()<br/>RGB=rojo, OLED="GRABANDO..."
        ESP32->>Python: Serial: "PTT_START"
        ESP32->>ESP32: Loop ADC 8kHz (MAX4466, HPF+LPF, oversample×2)
    end

    Usuario->>Panel: Suelta ESPACIO
    Panel->>Python: WS: {tipo:"control", accion:"PTT_FIN"}
    Python->>ESP32: Serial: 'T'
    ESP32->>Python: Serial: "PTT_STOP"
    ESP32->>Python: Serial: "AUDIO_START:N"
    ESP32->>Python: Serial: [N bytes PCM int16 LE 8kHz]
    ESP32->>Python: Serial: "AUDIO_END"

    Note over Python,Whisper: === PROCESAMIENTO WHISPER ===
    Python->>Python: _whisper_procesando = True<br/>_hilo_tick pausa el timer
    Python->>Panel: WS: (rawProcesando visible en UI)
    Python->>Whisper: transcribir(pcm_bytes)
    Whisper->>Whisper: HPF 80Hz → LPF 3400Hz → noisereduce<br/>→ normalize → resample 16kHz → Whisper small
    alt Whisper termina < 10s
        Whisper->>Python: ("azul.", "AZUL")
        Python->>Python: _whisper_procesando = False<br/>juego.reanudar_timeout()
        Python->>Panel: WS: {tipo:"voz", texto:"azul.", comando:"AZUL"}
    else Whisper tarda > 10s (timeout)
        Python->>Python: _whisper_hilo_activo = None (liberar)<br/>_whisper_procesando = False
        Python->>Panel: WS: {tipo:"voz", texto:"", comando:"DESCONOCIDO"}
        Python->>Panel: WS: enviar_log("Whisper tardó demasiado...")
        Note over Python: Usuario puede reintentar inmediatamente
    end

    Note over Python,Juego: === EVALUACIÓN ===
    Python->>Juego: procesar_comando("AZUL")
    Juego->>Juego: _evaluar("AZUL")

    alt Correcto
        Juego->>Python: on_resultado("CORRECT")
        Python->>Panel: WS: {tipo:"result", resultado:"CORRECT"}
        Python->>TTS: decir("Correcto.")
        alt Secuencia completa → LEVEL_UP
            Juego->>Python: on_estado(LEVEL_UP)
            Juego->>Python: on_nivel(n)
            Python->>Panel: WS: {tipo:"level", nivel:n}
            Juego->>Python: on_estado(SHOWING_SEQUENCE)
        else Más items en secuencia
            Juego->>Python: on_estado(LISTENING)
            Python->>Panel: WS: {tipo:"state", estado:"LISTENING"}
        end
    else Incorrecto / TIMEOUT
        Juego->>Python: on_resultado("WRONG" | "TIMEOUT")
        Python->>Panel: WS: {tipo:"result", resultado:"WRONG"}
        Python->>TTS: decir("Incorrecto. Di empieza...")
        Juego->>Python: on_estado(GAME_OVER)
        Python->>Panel: WS: {tipo:"gameover"}
        Python->>ESP32: Serial: "LED:OFF"
    end
```

---

## Diagrama 2: Máquina de estados del juego

```mermaid
stateDiagram-v2
    direction LR
    [*] --> IDLE : juego.iniciar()

    IDLE --> SHOWING_SEQUENCE : procesar_comando("REINICIAR")

    SHOWING_SEQUENCE --> LISTENING : hilo_secuencia termina<br/>(LEDs + TTS completados)

    LISTENING --> EVALUATING : procesar_comando(color)
    LISTENING --> GAME_OVER : tick() — timeout expiró\n(timer pausado durante TTS + Whisper)

    EVALUATING --> CORRECT : color == esperado
    EVALUATING --> WRONG : color != esperado

    CORRECT --> LISTENING : quedan items en secuencia\n(pos_actual < longitud)
    CORRECT --> LEVEL_UP : secuencia completa

    LEVEL_UP --> SHOWING_SEQUENCE : _iniciar_secuencia()\n(nivel++)

    WRONG --> GAME_OVER : hilo_gameover (0.8s delay)
    GAME_OVER --> IDLE : procesar_comando("REINICIAR")
    GAME_OVER --> [*]
```

---

## Diagrama 3: Sincronización TTS ↔ Timer ↔ PTT

```mermaid
flowchart TD
    A([Spacebar presionado]) --> B[ws_server: on_pausar_timeout\njuego.pausar_timeout]
    B --> C{_verificar_condiciones_ptt}

    C -->|tts_hablando=True| D[Rechazar PTT\nNO reanudar_timeout\nlog: Espera al narrador]
    D --> E[_hilo_tick: tts_hablando=True\nNO llama juego.tick\nTimer congelado]
    E --> F[TTS termina → _tts_activo.clear]
    F --> G[_hilo_tick: tts_hablando=False\nTimer reanuda automáticamente]
    G --> H([Usuario puede presionar spacebar])

    C -->|SHOWING_SEQUENCE| I[Rechazar PTT\nreanudar_timeout\nlog: Mira la secuencia]
    I --> J[Timer no aplica\nestado ≠ LISTENING]

    C -->|Condiciones OK| K[_ptt_spacebar_activo = True\nSerial R → ESP32 graba]
    K --> L[Serial audio → Python]
    L --> M[_whisper_procesando = True\n_hilo_tick pausa timer]
    M --> N{join timeout=10s}

    N -->|< 10s OK| O[enviar_voz al panel\njuego.procesar_comando\n_whisper_procesando=False\nTimer reanuda]
    N -->|> 10s TIMEOUT| P[_whisper_hilo_activo = None\n_whisper_procesando = False\nenviar_voz vacío → panel resetea\nTimer reanuda\nUsuario puede reintentar]
```

---

## Diagrama 4: Protocolo de mensajes WebSocket (Servidor → Panel)

```mermaid
flowchart LR
    subgraph servidor["Servidor PC (Python)"]
        E1["ready\n{whisperDisponible, tiempoTimeout}"]
        E2["state\n{estado: IDLE|SHOWING|LISTENING...}"]
        E3["led\n{color: ROJO|VERDE|AZUL|AMARILLO|null}"]
        E4["sequence\n{secuencia: ['ROJO','AZUL',...]}"]
        E5["expected\n{esperado: 'ROJO'}"]
        E6["voz\n{texto: 'azul.', comando: 'AZUL'}"]
        E7["result\n{resultado: CORRECT|WRONG|TIMEOUT}"]
        E8["level\n{nivel: 2}"]
        E9["score\n{puntuacion: 10}"]
        E10["gameover"]
        E11["log\n{mensaje: '...'}"]
    end

    subgraph panel["Web Panel (Next.js)"]
        P1["Muestra estado del juego"]
        P2["Enciende LED visual"]
        P3["Muestra secuencia"]
        P4["Muestra palabra esperada"]
        P5["Muestra detección Whisper\nreset rawProcesando/rawGrabando"]
        P6["Muestra resultado turno"]
        P7["Actualiza nivel"]
        P8["Actualiza puntuación"]
        P9["Pantalla Game Over"]
        P10["Log en tiempo real"]
    end

    E1 --> P1
    E2 --> P1
    E3 --> P2
    E4 --> P3
    E5 --> P4
    E6 --> P5
    E7 --> P6
    E8 --> P7
    E9 --> P8
    E10 --> P9
    E11 --> P10
```

---

## Resumen de hilos concurrentes

| Hilo | Nombre | Responsabilidad |
|------|--------|-----------------|
| Principal | `main` | Arranque, bucle `while True` |
| WS server | `ws-server` | asyncio loop — recibe/envía WebSocket |
| Serial reader | `serial-reader` | Lee stream Serial del ESP32 |
| Audio proc | `audio-proc` (spawneado) | Recibe PCM, llama Whisper |
| Whisper | `whisper-transcribe` | Transcripción (con timeout 10s) |
| TTS worker | `tts-worker` | Reproduce cola TTS |
| Tick | `tick` | Verifica timeout del turno cada 200ms |
| Secuencia | `seq` | Muestra LEDs de la secuencia (bloqueante) |
| Nivel up | `nivel-up` | Delay 0.6s → nuevo nivel |
| Game over | `gameover` | Delay 0.8s → GAME_OVER |
| Bienvenida | `bienvenida` | TTS de bienvenida al conectar |
