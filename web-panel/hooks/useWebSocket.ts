"use client";

// ============================================================
// hooks/useWebSocket.ts — Modo Simulador PC (Fase 1)
//
// Conecta al simulador Python via WebSocket.
//
// Reconocimiento de voz — modo DUAL con auto-detección:
//
//   PREFERIDO (Whisper local en Python):
//     El servidor anuncia whisperDisponible:true en el mensaje READY.
//     El browser envía señales de control PTT — Python abre el micrófono
//     del sistema directamente (sounddevice), graba, transcribe con Whisper
//     y devuelve {"tipo":"voz","texto":"...","comando":"..."}.
//     El browser NO necesita permisos de micrófono en este modo.
//
//   FALLBACK (Whisper WASM en browser):
//     Si el servidor no tiene Whisper (whisperDisponible:false), el browser
//     descarga Whisper WASM (lazy, solo cuando se confirma que hace falta),
//     captura el micrófono localmente y envía el texto del comando.
//
// Sin bucle continuo. PTT: barra espaciadora o botón visible.
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
  const ws             = useRef<WebSocket | null>(null);
  const escuchandoRef  = useRef(false);
  const estadoRef      = useRef<EstadoJuego>("IDLE");
  const iniciarPTTRef  = useRef<() => void>(() => {});

  // ---- Modo Whisper local (Python mic) ----
  const whisperDisponibleRef = useRef(false);
  const [whisperLocalActivo, setWhisperLocalActivo] = useState(false);

  // UI para el modo Python mic (browser no graba, solo muestra estados)
  const [rawGrabando,   setRawGrabando]   = useState(false);
  const [rawProcesando, setRawProcesando] = useState(false);
  const rawGrabandoRef   = useRef(false);
  const rawProcesandoRef = useRef(false);

  // ---- Whisper WASM (fallback — lazy, solo si Python no tiene Whisper) ----
  // autoCargar = false: no descarga nada hasta saber si hace falta
  const whisper = useWhisperWASM(false);

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

  // Señal de control (PTT_INICIO, PTT_FIN) — llegan antes del audio en TCP
  const enviarControl = useCallback((accion: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ tipo: "control", accion }));
    }
  }, []);

  // ---- PTT: iniciar ----

  const iniciarPTTVoz = useCallback(async () => {
    if (escuchandoRef.current) return;
    if (!ESTADOS_ESCUCHA.has(estadoRef.current)) return;

    escuchandoRef.current = true;

    if (whisperDisponibleRef.current) {
      // ── Modo Whisper local: Python abre el mic del sistema ──
      // PTT_INICIO pausa el timer en Python (inline en asyncio, sin race condition)
      // y abre sounddevice InputStream en el PC.
      enviarControl("PTT_INICIO");
      setRawGrabandoAll(true);
      // escuchandoRef se libera cuando llega el mensaje "voz" de Python
    } else {
      // ── Modo WASM fallback: browser captura el mic ──
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
  }, [whisper, agregarLog, enviarComando, enviarControl, setRawGrabandoAll]);

  useEffect(() => {
    iniciarPTTRef.current = iniciarPTTVoz;
  }, [iniciarPTTVoz]);

  // ---- PTT: finalizar ----

  const finalizarPTTExterior = useCallback(() => {
    if (whisperDisponibleRef.current) {
      // Modo local: indicar a Python que el usuario soltó el botón
      if (!rawGrabandoRef.current) return;
      enviarControl("PTT_FIN");
      setRawGrabandoAll(false);
      setRawProcesandoAll(true);
      // rawProcesando y escuchandoRef se limpian cuando llega el mensaje "voz"
    } else {
      // Modo WASM: señalar al hook que corte la grabación
      whisper.finalizarGrabacion();
    }
  }, [whisper, enviarControl, setRawGrabandoAll, setRawProcesandoAll]);

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

  // ---- Cargar WASM solo cuando se confirma que Python no tiene Whisper ----

  useEffect(() => {
    if (estadoJuego.conectado && !whisperLocalActivo) {
      whisper.cargar();
    }
  }, [estadoJuego.conectado, whisperLocalActivo]); // eslint-disable-line

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
                ? "Simulador listo — Whisper local activo (mic del sistema)"
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
            // Resultado de Whisper local — Python transcribió y procesó el comando
            siguiente.ultimoTextoWhisper = msg.texto;
            siguiente.ultimaDeteccion    = msg.comando !== "DESCONOCIDO"
              ? (msg.comando as ColorJuego)
              : prev.ultimaDeteccion;
            agregarLog(`"${msg.texto}" → ${msg.comando}`, "voz");
            // Liberar estado de grabación Python
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

  const puedoHablar    = ESTADOS_ESCUCHA.has(estadoJuego.estado) && estadoJuego.conectado;
  const grabando       = rawGrabando   || whisper.grabando;
  const procesando     = rawProcesando || whisper.procesando;
  const micAbierto     = rawGrabando   || whisper.micAbierto;
  const transcribiendo = grabando || procesando;
  const modeloCargado  = whisperLocalActivo || whisper.modeloCargado;

  // Nivel de mic solo disponible en modo WASM (Python mic no envía RMS al browser)
  const nivelMic = (!whisperLocalActivo && puedoHablar) ? whisper.nivelMic : 0;

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
    whisperLocalActivo,
    whisperProgresoDescarga: whisperLocalActivo ? null : whisper.progresoDescarga,
    whisperNivelMic:         nivelMic,
    whisperGrabando:         grabando,
    whisperMicAbierto:       micAbierto,
    whisperProcesando:       procesando,
    whisperTiempoRestante:   whisperLocalActivo ? null : whisper.tiempoRestante,
    iniciarPTT:              iniciarPTTVoz,
    finalizarPTT:            finalizarPTTExterior,
    puedoHablar,
  };
}
