"use client";

// ============================================================
// hooks/useWebSocket.ts — Modo Simulador PC
//
// Conecta al simulador Python via WebSocket.
//
// Reconocimiento de voz — modo DUAL con auto-detección:
//
//   PREFERIDO (Whisper local en Python):
//     El servidor anuncia whisperDisponible:true en el mensaje READY.
//     PTT → browser captura audio PCM Float32 16kHz con AudioContext
//     → envía frame binario WebSocket → Python transcribe con Whisper
//     → servidor devuelve {"tipo":"voz", "texto":"...", "comando":"..."}
//     → browser actualiza UI.
//
//   FALLBACK (Whisper WASM en browser):
//     Si el servidor no tiene Whisper (whisperDisponible:false),
//     el browser usa useWhisperWASM igual que antes.
//     Sigue siendo PTT (barra espaciadora / botón).
//
// Sin bucle continuo. El usuario controla el micrófono con PTT.
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoCliente, EstadoJuego, MensajeWS, ColorJuego, ResultadoTurno } from "../types/game";
import { useWhisperWASM } from "./useWhisperWASM";
import { textoAComando } from "../lib/validador";

// Estados en los que el usuario puede hablar
const ESTADOS_ESCUCHA = new Set<string>(["IDLE", "LISTENING", "PAUSA", "GAMEOVER"]);

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8765";

const NOMBRES_ESTADO: Record<string, string> = {
  IDLE:       "Esperando",
  SHOWING:    "Mostrando secuencia",
  LISTENING:  "Tu turno — habla",
  EVALUATING: "Procesando...",
  CORRECT:    "¡Correcto!",
  LEVEL_UP:   "¡Nivel superado!",
  WRONG:      "Incorrecto",
  GAMEOVER:   "Fin del juego",
  PAUSA:      "Pausa",
};

const ESTADO_INICIAL: EstadoCliente = {
  conectado:             false,
  estado:                "IDLE",
  nivel:                 1,
  puntuacion:            0,
  secuencia:             [],
  esperado:              null,
  ledActivo:             null,
  ultimaDeteccion:       null,
  ultimoTextoWhisper:    null,
  ultimoResultado:       null,
  whisperCargado:        false,
  whisperTranscribiendo: false,
  log:                   [],
};

let contadorLog = 0;

export function useWebSocket() {
  const [estadoJuego, setEstadoJuego] = useState<EstadoCliente>(ESTADO_INICIAL);
  const ws              = useRef<WebSocket | null>(null);
  const escuchandoRef   = useRef(false);
  const estadoRef       = useRef<EstadoJuego>("IDLE");
  const iniciarPTTRef   = useRef<() => void>(() => {});

  // ---- Modo Whisper local (Python) ----
  const whisperDisponibleRef = useRef(false);
  const [whisperLocalActivo, setWhisperLocalActivo] = useState(false);

  // Estado de grabación raw para UI
  const [rawGrabando,   setRawGrabando]   = useState(false);
  const [rawProcesando, setRawProcesando] = useState(false);
  const rawGrabandoRef   = useRef(false);
  const rawProcesandoRef = useRef(false);

  // Refs de AudioContext para grabar PCM sin Whisper WASM
  const audioCtxRef     = useRef<AudioContext | null>(null);
  const micRawRef       = useRef<MediaStream | null>(null);
  const audioSamplesRef = useRef<Float32Array[]>([]);
  const grabandoRawRef  = useRef(false);
  const [rawNivelMic,   setRawNivelMic]   = useState(0);

  // ---- Whisper WASM (fallback) ----
  const whisper = useWhisperWASM();

  // ---- Helpers ----

  const setRawGrabandoAll = useCallback((v: boolean) => {
    rawGrabandoRef.current = v;
    setRawGrabando(v);
  }, []);

  const setRawProcesandoAll = useCallback((v: boolean) => {
    rawProcesandoRef.current = v;
    setRawProcesando(v);
  }, []);

  const agregarLog = useCallback(
    (mensaje: string, tipo: "info" | "correcto" | "error" | "voz" | "sistema" = "info") => {
      setEstadoJuego((prev) => ({
        ...prev,
        log: [
          { id: contadorLog++, ts: Date.now(), mensaje, tipo },
          ...prev.log.slice(0, 99),
        ],
      }));
    },
    []
  );

  const enviarComando = useCallback((comando: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ tipo: "comando", comando }));
    }
  }, []);

  // Señal de control — llega antes del audio binario en la misma conexión TCP,
  // por lo que Python puede pausar el timer SIN race condition con el tick.
  const enviarControl = useCallback((accion: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ tipo: "control", accion }));
    }
  }, []);

  // ---- Grabación PCM raw (para Whisper local en Python) ----

  const iniciarGrabacionRaw = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate:       16000,
        channelCount:     1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    micRawRef.current      = stream;
    audioSamplesRef.current = [];
    grabandoRawRef.current  = true;

    // AudioContext a 16kHz — mismo formato que espera Whisper
    const ctx = new AudioContext({ sampleRate: 16000 });
    audioCtxRef.current = ctx;

    const source    = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      if (!grabandoRawRef.current) return;
      const data = e.inputBuffer.getChannelData(0);
      audioSamplesRef.current.push(new Float32Array(data));

      // Nivel de micrófono para la barra de UI
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      setRawNivelMic(Math.min(Math.sqrt(sum / data.length) * 5, 1));
    };

    source.connect(processor);
    processor.connect(ctx.destination);

    // Guardar referencias para cleanup
    (ctx as AudioContext & { _src: AudioNode; _proc: AudioNode })._src  = source;
    (ctx as AudioContext & { _src: AudioNode; _proc: AudioNode })._proc = processor;
  }, []);

  const finalizarGrabacionRaw = useCallback(async (): Promise<ArrayBuffer | null> => {
    grabandoRawRef.current = false;
    setRawNivelMic(0);

    const ctx = audioCtxRef.current;
    if (ctx) {
      const c = ctx as AudioContext & { _src: AudioNode; _proc: AudioNode };
      c._src?.disconnect();
      c._proc?.disconnect();
      await ctx.close().catch(() => {});
      audioCtxRef.current = null;
    }
    micRawRef.current?.getTracks().forEach((t) => t.stop());
    micRawRef.current = null;

    const muestras = audioSamplesRef.current;
    if (muestras.length === 0) return null;

    const totalLen = muestras.reduce((a, b) => a + b.length, 0);
    if (totalLen < 1600) return null; // < 0.1s — ignorar

    const combined = new Float32Array(totalLen);
    let offset = 0;
    for (const buf of muestras) {
      combined.set(buf, offset);
      offset += buf.length;
    }
    return combined.buffer;
  }, []);

  // ---- PTT: iniciar grabación ----

  const iniciarPTTVoz = useCallback(async () => {
    if (escuchandoRef.current) return;
    if (!ESTADOS_ESCUCHA.has(estadoRef.current)) return;

    escuchandoRef.current = true;

    if (whisperDisponibleRef.current) {
      // ── Modo Whisper local: grabar audio raw → enviar binario a Python ──
      // Pausar el timer del juego ANTES de empezar a grabar.
      // PTT_INICIO llega a Python por el mismo socket TCP, antes del audio binario,
      // lo que elimina la race condition entre pausar_timeout() y tick().
      if (estadoRef.current === "LISTENING") {
        enviarControl("PTT_INICIO");
      }
      try {
        setRawGrabandoAll(true);
        await iniciarGrabacionRaw();
        // escuchandoRef se libera cuando llega el mensaje "voz" de Python
      } catch (err) {
        agregarLog(`Error al abrir micrófono: ${err}`, "error");
        setRawGrabandoAll(false);
        escuchandoRef.current = false;
      }
    } else {
      // ── Modo WASM fallback ──
      if (!whisper.modeloCargado) {
        escuchandoRef.current = false;
        return;
      }
      const onProcesandoInicio = estadoRef.current === "LISTENING"
        ? () => enviarComando("WHISPER_PROCESANDO")
        : undefined;

      try {
        const textoRaw = await whisper.escuchar(onProcesandoInicio, "ptt");
        const comando  = textoAComando(textoRaw);

        if (textoRaw) agregarLog(`"${textoRaw}" → ${comando}`, "voz");

        setEstadoJuego((prev) => ({
          ...prev,
          ultimoTextoWhisper: textoRaw || prev.ultimoTextoWhisper,
          ultimaDeteccion:    comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
        }));

        if (comando !== "DESCONOCIDO") enviarComando(comando);
      } catch (err) {
        agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
      } finally {
        escuchandoRef.current = false;
      }
    }
  }, [whisper, agregarLog, enviarComando, enviarControl, iniciarGrabacionRaw, setRawGrabandoAll]);

  useEffect(() => {
    iniciarPTTRef.current = iniciarPTTVoz;
  }, [iniciarPTTVoz]);

  // ---- PTT: finalizar grabación ----

  const finalizarPTTExterior = useCallback(async () => {
    if (whisperDisponibleRef.current) {
      // Modo local: detener grabación y enviar audio a Python
      if (!rawGrabandoRef.current) return;
      setRawGrabandoAll(false);
      setRawProcesandoAll(true);

      const buffer = await finalizarGrabacionRaw();
      if (buffer && ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(buffer);
        // escuchandoRef y rawProcesando se limpian al recibir mensaje "voz"
      } else {
        setRawProcesandoAll(false);
        escuchandoRef.current = false;
      }
    } else {
      // Modo WASM: señalar a useWhisperWASM que pare la grabación
      whisper.finalizarGrabacion();
    }
  }, [whisper, finalizarGrabacionRaw, setRawGrabandoAll, setRawProcesandoAll]);

  // ---- Spacebar PTT — global ----

  useEffect(() => {
    if (!estadoJuego.conectado) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
      e.preventDefault();
      if (ESTADOS_ESCUCHA.has(estadoRef.current) && !escuchandoRef.current) {
        iniciarPTTRef.current();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      e.preventDefault();
      finalizarPTTExterior();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup",   handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup",   handleKeyUp);
    };
  }, [estadoJuego.conectado, finalizarPTTExterior]); // eslint-disable-line

  // ---- Procesar mensajes del servidor ----

  const procesarMensaje = useCallback(
    (msg: MensajeWS) => {
      setEstadoJuego((prev) => {
        const siguiente = { ...prev };

        switch (msg.tipo) {
          case "ready": {
            const disponible = (msg as MensajeWS & { whisperDisponible?: boolean }).whisperDisponible === true;
            whisperDisponibleRef.current = disponible;
            setWhisperLocalActivo(disponible);
            agregarLog(
              disponible
                ? "Simulador listo — Whisper local activo"
                : "Simulador listo — usando Whisper del navegador",
              "sistema"
            );
            break;
          }

          case "state":
            siguiente.estado  = msg.estado as EstadoJuego;
            estadoRef.current = msg.estado as EstadoJuego;
            if (msg.estado === "IDLE" || msg.estado === "SHOWING") {
              siguiente.esperado = null;
            }
            if (msg.estado !== "SHOWING") {
              siguiente.ledActivo = null;
            }
            if (msg.estado === "SHOWING") {
              whisper.cancelarEscucha();
              siguiente.ultimaDeteccion    = null;
              siguiente.ultimoTextoWhisper = null;
              siguiente.ultimoResultado    = null;
            }
            agregarLog(`Estado: ${NOMBRES_ESTADO[msg.estado] ?? msg.estado}`, "info");
            break;

          case "led":
            siguiente.ledActivo = msg.color;
            break;

          case "detected":
            siguiente.ultimaDeteccion = msg.palabra;
            agregarLog(`Detectado: ${msg.palabra}`, "voz");
            break;

          case "result":
            siguiente.ultimoResultado = msg.resultado as ResultadoTurno;
            if (msg.resultado === "CORRECT") {
              agregarLog("Correcto ✓", "correcto");
            } else if (msg.resultado === "WRONG") {
              agregarLog("Incorrecto ✗", "error");
            } else {
              agregarLog("Tiempo agotado ⏱", "error");
            }
            break;

          case "sequence":
            siguiente.secuencia = msg.secuencia as ColorJuego[];
            break;

          case "expected":
            siguiente.esperado = msg.esperado as ColorJuego;
            break;

          case "level":
            siguiente.nivel = msg.nivel;
            agregarLog(`Nivel ${msg.nivel}`, "sistema");
            break;

          case "score":
            siguiente.puntuacion = msg.puntuacion;
            break;

          case "gameover":
            siguiente.estado  = "GAMEOVER";
            estadoRef.current = "GAMEOVER";
            siguiente.esperado           = null;
            siguiente.ultimaDeteccion    = null;
            siguiente.ultimoTextoWhisper = null;
            agregarLog(`Fin del juego — Puntuación: ${prev.puntuacion}`, "error");
            break;

          case "voz":
            // Resultado de Whisper local — Python transcribió y procesó
            siguiente.ultimoTextoWhisper = msg.texto;
            siguiente.ultimaDeteccion    = msg.comando !== "DESCONOCIDO"
              ? (msg.comando as ColorJuego)
              : prev.ultimaDeteccion;
            agregarLog(`"${msg.texto}" → ${msg.comando}`, "voz");
            // Liberar estado de grabación local
            setRawProcesandoAll(false);
            setRawGrabandoAll(false);
            escuchandoRef.current = false;
            break;

          case "log":
            agregarLog(msg.raw, "info");
            break;
        }

        return siguiente;
      });
    },
    [agregarLog, whisper, setRawProcesandoAll, setRawGrabandoAll]
  );

  // ---- Conectar ----

  const conectar = useCallback(() => {
    if (
      ws.current?.readyState === WebSocket.OPEN ||
      ws.current?.readyState === WebSocket.CONNECTING
    ) return;

    agregarLog(`Conectando a ${WS_URL}...`, "sistema");
    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      setEstadoJuego((prev) => ({ ...prev, conectado: true }));
      agregarLog("Conectado. Presiona ESPACIO o el botón para hablar.", "sistema");
    };

    socket.onmessage = (event) => {
      try {
        const msg: MensajeWS = JSON.parse(event.data);
        procesarMensaje(msg);
      } catch {
        agregarLog(`Mensaje no reconocido: ${event.data}`, "info");
      }
    };

    socket.onerror = () => {
      agregarLog("Error de conexión WebSocket", "error");
    };

    socket.onclose = () => {
      whisper.cancelarEscucha();
      setRawGrabandoAll(false);
      setRawProcesandoAll(false);
      escuchandoRef.current        = false;
      whisperDisponibleRef.current = false;
      setWhisperLocalActivo(false);
      setEstadoJuego((prev) => ({ ...prev, conectado: false }));
      agregarLog("Conexión cerrada", "sistema");
      ws.current = null;
    };

    ws.current = socket;
  }, [agregarLog, procesarMensaje, whisper, setRawGrabandoAll, setRawProcesandoAll]);

  // ---- Desconectar ----

  const desconectar = useCallback(() => {
    whisper.cancelarEscucha();
    ws.current?.close();
  }, [whisper]);

  const limpiarLog = useCallback(() => {
    setEstadoJuego((prev) => ({ ...prev, log: [] }));
  }, []);

  useEffect(() => {
    return () => { ws.current?.close(); };
  }, []);

  // ---- Props compuestos para UI ----

  const puedoHablar = ESTADOS_ESCUCHA.has(estadoJuego.estado) && estadoJuego.conectado;

  // Combinar estados de ambos modos para mostrar en UI de forma uniforme
  const grabando      = rawGrabando   || whisper.grabando;
  const procesando    = rawProcesando || whisper.procesando;
  const micAbierto    = rawGrabando   || whisper.micAbierto;
  const transcribiendo = grabando || procesando;
  const nivelMic      = rawGrabando   ? rawNivelMic : (puedoHablar ? whisper.nivelMic : 0);
  const modeloCargado = whisperLocalActivo || whisper.modeloCargado;

  const estadoConWhisper: EstadoCliente = {
    ...estadoJuego,
    whisperCargado:        modeloCargado,
    whisperTranscribiendo: transcribiendo,
  };

  return {
    estadoJuego:             estadoConWhisper,
    conectar,
    desconectar,
    limpiarLog,
    reiniciar: () => {
      enviarComando("REINICIAR");
      setEstadoJuego((prev) => ({ ...prev, log: [] }));
    },
    // Props de voz — unificados independientemente del modo
    whisperLocalActivo,
    whisperProgresoDescarga: whisperLocalActivo ? null : whisper.progresoDescarga,
    whisperNivelMic:         nivelMic,
    whisperGrabando:         grabando,
    whisperMicAbierto:       micAbierto,
    whisperProcesando:       procesando,
    whisperTiempoRestante:   whisperLocalActivo ? null : whisper.tiempoRestante,
    // PTT
    iniciarPTT:  iniciarPTTVoz,
    finalizarPTT: finalizarPTTExterior,
    puedoHablar,
  };
}
