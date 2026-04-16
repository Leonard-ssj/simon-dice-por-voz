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
    Python->>TTS: decir("Simon Dice listo...")
    TTS-->>Panel: WS: {tipo:"tts", activo:true}
    TTS-->>Panel: WS: {tipo:"tts", activo:false}

    Note over Panel,TTS: === INICIO DE RONDA ===
    Usuario->>Panel: Presiona ESPACIO
    Panel->>Python: WS: {tipo:"control", accion:"PTT_INICIO"}
    Python->>Juego: pausar_timeout()
    Python->>Python: _verificar_condiciones_ptt()

    alt TTS hablando (narrando=true en panel)
        Python->>Panel: WS: {tipo:"voz", texto:"", comando:"DESCONOCIDO"}
        Note over Panel: rawGrabando/rawProcesando se limpian inmediatamente
    else SHOWING_SEQUENCE activo
        Python->>Panel: WS: {tipo:"voz", texto:"", comando:"DESCONOCIDO"}
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

    alt Audio muy corto (< 0.25s)
        ESP32->>Python: Serial: "AUDIO_CORTO"
        Python->>Panel: WS: {tipo:"voz", texto:"", comando:"DESCONOCIDO"}
        Note over Panel: sale de "Grabando..." inmediatamente
    else Audio válido
        Note over Python,Whisper: === PROCESAMIENTO WHISPER ===
        Python->>Python: _whisper_procesando = True<br/>_hilo_tick pausa el timer
        Python->>Whisper: transcribir(pcm_bytes)
        Whisper->>Whisper: HPF 80Hz → LPF 3400Hz → noisereduce<br/>→ normalize → resample 16kHz → Whisper small
        alt Whisper termina < 10s
            Whisper->>Python: ("azul.", "AZUL")
            Python->>Python: _whisper_procesando = False<br/>juego.reanudar_timeout()
            Python->>Panel: WS: {tipo:"voz", texto:"azul.", comando:"AZUL"}
        else Whisper tarda > 10s (timeout)
            Python->>Python: _whisper_hilo_activo = None (liberar)<br/>_whisper_procesando = False
            Python->>Panel: WS: {tipo:"voz", texto:"", comando:"DESCONOCIDO"}
            Note over Python: Usuario puede reintentar inmediatamente
        end
    end

    Note over Python,Juego: === EVALUACIÓN ===
    Python->>Juego: procesar_comando("AZUL")
    Juego->>Juego: _evaluar("AZUL")

    alt Correcto — quedan más colores en secuencia
        Juego->>Python: on_resultado("CORRECT")
        Python->>Panel: WS: {tipo:"result", resultado:"CORRECT"}
        Juego->>Python: on_estado(EVALUATING → LISTENING)
        Python->>TTS: decir("Correcto. Tu turno.")
        Python->>Panel: WS: {tipo:"tts", activo:true}
        Note over Panel: countdown pausado, spacebar bloqueado
        Python->>Panel: WS: {tipo:"tts", activo:false}
        Note over Panel: countdown reanuda desde donde quedó
    else Correcto — secuencia completa → LEVEL_UP
        Juego->>Python: on_resultado("CORRECT")
        Python->>Panel: WS: {tipo:"result", resultado:"CORRECT"}
        Juego->>Python: on_estado(CORRECT)
        Python->>TTS: decir("Correcto.")
        Juego->>Python: on_nivel(n)
        Juego->>Python: on_estado(SHOWING_SEQUENCE)
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

    EVALUATING --> CORRECT : color == esperado && secuencia completa
    EVALUATING --> LISTENING : color == esperado && quedan colores
    EVALUATING --> WRONG : color != esperado

    CORRECT --> LEVEL_UP : _hilo_nivel_up (0.6s delay)

    LEVEL_UP --> SHOWING_SEQUENCE : _iniciar_secuencia()\n(nivel++)

    WRONG --> GAME_OVER : hilo_gameover (0.8s delay)
    GAME_OVER --> IDLE : procesar_comando("REINICIAR")
    GAME_OVER --> [*]
```

---

## Diagrama 3: Sincronización TTS ↔ Timer ↔ PTT ↔ Panel

```mermaid
flowchart TD
    A([Spacebar presionado]) --> B[ws_server: on_pausar_timeout\njuego.pausar_timeout]
    B --> C{_verificar_condiciones_ptt}

    C -->|tts_hablando=True| D[Rechazar PTT\nenviar_voz vacío → panel limpia flags\nlog: Espera al narrador]
    D --> E[_hilo_tick: tts_hablando=True\nNO llama juego.tick\nTimer congelado]
    E --> F[TTS termina → _tts_activo.clear\nenviar_tts false → panel reanuda countdown]
    F --> G([Usuario puede presionar spacebar])

    C -->|SHOWING_SEQUENCE| H[Rechazar PTT\nenviar_voz vacío → panel limpia flags\nlog: Mira la secuencia]

    C -->|Condiciones OK| I[_ptt_spacebar_activo = True\nSerial R → ESP32 graba]
    I --> J[Serial audio → Python]
    J -->|AUDIO_CORTO| K[enviar_voz vacío → panel\njuego.reanudar_timeout]
    J -->|Audio OK| L[_whisper_procesando = True\n_hilo_tick pausa timer]
    L --> M{join timeout=10s}

    M -->|< 10s OK| N[enviar_voz al panel\njuego.procesar_comando\n_whisper_procesando=False\nTimer reanuda]
    M -->|> 10s TIMEOUT| O[_whisper_hilo_activo = None\n_whisper_procesando = False\nenviar_voz vacío → panel resetea\nTimer reanuda\nUsuario puede reintentar]

    subgraph panel["Panel Web"]
        P1[Recibe tts=true → pausar countdown\nbloquear spacebar\nnarrando=true]
        P2[Recibe tts=false → reanudar countdown\nhabilitar spacebar\nnarrando=false]
        P3[Recibe voz → limpiar rawGrabando\nrawProcesando\nescuchandoRef=false]
    end

    E -.->|enviar_tts true| P1
    F -.->|enviar_tts false| P2
    N -.-> P3
    O -.-> P3
    K -.-> P3
    D -.-> P3
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
        E12["tts\n{activo: true|false}"]
    end

    subgraph panel["Web Panel (Next.js)"]
        P1["Muestra estado del juego"]
        P2["Enciende LED visual"]
        P3["Muestra secuencia"]
        P4["Muestra palabra esperada"]
        P5["Muestra detección Whisper\nreset rawProcesando/rawGrabando"]
        P6["Muestra resultado turno\nreset flags PTT"]
        P7["Actualiza nivel"]
        P8["Actualiza puntuación"]
        P9["Pantalla Game Over"]
        P10["Log en tiempo real"]
        P11["Pausa/reanuda countdown\nBloquea/habilita spacebar\nnarrando=true/false"]
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
    E12 --> P11
```

---

## Diagrama 5: Modo Multi-Color (varios colores en un solo audio)

```mermaid
flowchart TD
    A([Audio recibido\nWhisper transcribe]) --> B["texto_a_colores(texto)"]
    B --> C{colores\ndetectados}

    C -->|0 colores| D["texto_a_comando(texto)\ncamino normal"]
    C -->|1 color| D
    C -->|≥ 2 colores| E["juego.procesar_colores_multiples(colores)"]

    E --> F{Para cada color\nen orden}

    F -->|Color == esperado| G[pos_escuchar++\naceptados++]
    G --> H{¿Secuencia\ncompleta?}
    H -->|No| F
    H -->|Sí| I[CORRECT → LEVEL_UP\nTTS: Correcto.]

    F -->|Color != esperado| J[WRONG → GAME_OVER\nTTS: Incorrecto.]
    F -->|Lista agotada\nsin error| K{aceptados > 0?}

    K -->|Sí| L["on_resultado(CORRECT)\n→ LISTENING\nTTS: N colores correctos. Tu turno."]
    K -->|No| M[_empezar_escucha\nsin resultado]
```

### Reglas de corte en `texto_a_colores()`

| Texto de Whisper | Resultado | Razón |
|-----------------|-----------|-------|
| `"azul rojo rojo amarillo"` | `[AZUL, ROJO, ROJO, AMARILLO]` | Todo reconocido |
| `"adul dojo amadillo"` | `[AZUL, ROJO, AMARILLO]` | Fuzzy matching |
| `"azul rojo sdadsa verde"` | `[AZUL, ROJO]` | Para en sdadsa |
| `"sdadsa rojo rojo"` | `[]` | Primera palabra falla → camino normal |
| `"reiniciar"` | `[]` | No es color → `texto_a_comando` → REINICIAR |
| `"azul"` (solo 1) | `[AZUL]` → usa camino normal | < 2 colores |

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
| Tick | `tick` | Verifica timeout del turno cada 200ms; detecta transiciones TTS → notifica panel |
| Secuencia | `seq` | Muestra LEDs de la secuencia (bloqueante) |
| Nivel up | `nivel-up` | Delay 0.6s → nuevo nivel |
| Game over | `gameover` | Delay 0.8s → GAME_OVER |
| Bienvenida | `bienvenida` | TTS de bienvenida al conectar |

---

## OLED del ESP32 — Mensajes por estado

| Estado | Línea 1 | Línea 2 | Línea 3 |
|--------|---------|---------|---------|
| IDLE | Simon Dice | Di EMPIEZA | para comenzar |
| SHOWING_SEQUENCE | MOSTRANDO | secuencia | — |
| LISTENING | TU TURNO | Nv2 Pts:10 1/2 | Presiona ESPACIO |
| EVALUATING | Procesando... | Whisper | — |
| CORRECT | CORRECTO! | — | — |
| LEVEL_UP | NIVEL 3! | Puntos: 20 | Bien hecho! |
| WRONG | INCORRECTO | — | — |
| GAME_OVER | GAME OVER | — | Di EMPIEZA |
| PAUSA | PAUSA | Di EMPIEZA | para continuar |

*LISTENING es dinámico: nivel y puntuación actuales, posición en secuencia.*
