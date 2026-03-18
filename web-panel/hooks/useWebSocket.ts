"use client";

// ============================================================
// hooks/useWebSocket.ts — Modo Simulador PC
//
// Conecta al simulador Python via WebSocket.
// Reconocimiento de voz: Push-to-Talk (PTT).
//   Barra espaciadora (o botón en UI) → abre mic → usuario habla
//   → suelta → Whisper WASM transcribe → comando enviado al juego.
//
// Sin bucle continuo, sin ventanas de silencio. El usuario
// controla exactamente cuándo el micrófono está activo.
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
  const escuchandoRef   = useRef(false);   // evita inicios simultáneos de PTT
  const estadoRef       = useRef<EstadoJuego>("IDLE");
  // Ref a la versión más reciente de iniciarPTTVoz (evita stale closure en useEffect)
  const iniciarPTTRef   = useRef<() => void>(() => {});

  const whisper = useWhisperWASM();

  // ---- Helpers ----

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

  // ---- PTT: iniciar grabación ----
  const iniciarPTTVoz = useCallback(async () => {
    if (escuchandoRef.current || !whisper.modeloCargado) return;
    if (!ESTADOS_ESCUCHA.has(estadoRef.current)) return;

    escuchandoRef.current = true;

    // Callback que pausa el timer del juego mientras Whisper infiere
    const onProcesandoInicio = estadoRef.current === "LISTENING"
      ? () => enviarComando("WHISPER_PROCESANDO")
      : undefined;

    try {
      const textoRaw = await whisper.escuchar(onProcesandoInicio, "ptt");
      const comando  = textoAComando(textoRaw);

      if (textoRaw) {
        agregarLog(`"${textoRaw}" → ${comando}`, "voz");
      }

      setEstadoJuego((prev) => ({
        ...prev,
        ultimoTextoWhisper: textoRaw || prev.ultimoTextoWhisper,
        ultimaDeteccion:    comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
      }));

      if (comando !== "DESCONOCIDO") {
        enviarComando(comando);
      }
    } catch (err) {
      agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
    } finally {
      escuchandoRef.current = false;
    }
  }, [whisper, agregarLog, enviarComando]);

  // Mantener ref actualizada (para el useEffect de spacebar)
  useEffect(() => {
    iniciarPTTRef.current = iniciarPTTVoz;
  }, [iniciarPTTVoz]);

  // ---- Spacebar PTT — global ----
  useEffect(() => {
    if (!estadoJuego.conectado) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      // No interceptar espacio en inputs o botones
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
      whisper.finalizarGrabacion();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup",   handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup",   handleKeyUp);
    };
  }, [estadoJuego.conectado, whisper.finalizarGrabacion]); // eslint-disable-line

  // ---- Procesar mensajes del servidor ----
  const procesarMensaje = useCallback(
    (msg: MensajeWS) => {
      setEstadoJuego((prev) => {
        const siguiente = { ...prev };

        switch (msg.tipo) {
          case "ready":
            agregarLog("Simulador listo", "sistema");
            break;

          case "state":
            siguiente.estado = msg.estado as EstadoJuego;
            estadoRef.current = msg.estado as EstadoJuego;
            if (msg.estado === "IDLE" || msg.estado === "SHOWING") {
              siguiente.esperado = null;
            }
            if (msg.estado !== "SHOWING") {
              siguiente.ledActivo = null;
            }
            if (msg.estado === "SHOWING") {
              // Cancelar cualquier grabación activa mientras muestra LEDs
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
            siguiente.estado = "GAMEOVER";
            estadoRef.current = "GAMEOVER";
            siguiente.esperado = null;
            siguiente.ultimaDeteccion = null;
            siguiente.ultimoTextoWhisper = null;
            agregarLog(`Fin del juego — Puntuación: ${prev.puntuacion}`, "error");
            break;

          case "voz":
            siguiente.ultimoTextoWhisper = msg.texto;
            agregarLog(`"${msg.texto}" → ${msg.comando}`, "voz");
            break;

          case "log":
            agregarLog(msg.raw, "info");
            break;
        }

        return siguiente;
      });
    },
    [agregarLog, whisper]
  );

  // ---- Conectar ----
  const conectar = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN ||
        ws.current?.readyState === WebSocket.CONNECTING) return;

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
      setEstadoJuego((prev) => ({ ...prev, conectado: false }));
      agregarLog("Conexión cerrada", "sistema");
      ws.current = null;
    };

    ws.current = socket;
  }, [agregarLog, procesarMensaje, whisper]);

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

  // Mostrar estado de mic en todos los estados de escucha (no solo LISTENING)
  const puedoHablar = ESTADOS_ESCUCHA.has(estadoJuego.estado) && estadoJuego.conectado;

  const estadoConWhisper: EstadoCliente = {
    ...estadoJuego,
    whisperCargado:        whisper.modeloCargado,
    whisperTranscribiendo: whisper.transcribiendo,
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
    // Props de Whisper — visibles en todos los estados de escucha
    whisperProgresoDescarga: whisper.progresoDescarga,
    whisperNivelMic:         puedoHablar ? whisper.nivelMic : 0,
    whisperGrabando:         whisper.grabando,
    whisperMicAbierto:       whisper.micAbierto,
    whisperProcesando:       whisper.procesando,
    whisperTiempoRestante:   whisper.tiempoRestante,
    // PTT — funciones para el botón en UI
    iniciarPTT:              iniciarPTTVoz,
    finalizarPTT:            whisper.finalizarGrabacion,
    puedoHablar,
  };
}
