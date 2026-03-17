"use client";

// ============================================================
// hooks/useWebSocket.ts — Modo Simulador PC
//
// Se conecta al simulador Python (tests/simulador_pc) via WebSocket.
// El browser graba el micrófono, transcribe con Whisper WASM y manda
// el comando reconocido al simulador via WebSocket:
//   {"tipo": "comando", "comando": "ROJO"}
//
// El simulador Python recibe los comandos y corre el juego
// (LEDs ANSI, tonos, TTS narrador), igual que lo haría el ESP32.
//
// Bucle continuo de voz (bucleVoz): escucha en todos los estados
// que aceptan comandos: IDLE, LISTENING, PAUSA, GAMEOVER.
// Permite decir "empieza" desde IDLE sin acción manual.
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoCliente, EstadoJuego, MensajeWS, ColorJuego, ResultadoTurno } from "../types/game";
import { useWhisperWASM } from "./useWhisperWASM";
import { textoAComando } from "../lib/validador";

// Estados del juego en los que el browser debe escuchar comandos de voz
const ESTADOS_ESCUCHA = new Set<string>(["IDLE", "LISTENING", "PAUSA", "GAMEOVER"]);

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8765";

const NOMBRES_ESTADO: Record<string, string> = {
  IDLE:       "Esperando",
  SHOWING:    "Mostrando secuencia",
  LISTENING:  "Escuchando — habla ahora",
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
  const ws = useRef<WebSocket | null>(null);
  const escuchandoVozRef  = useRef(false);
  const bucleVozActivoRef = useRef(false);
  const estadoRef         = useRef<EstadoJuego>("IDLE");
  // Ref que siempre apunta a la versión más reciente de iniciarEscuchaVoz
  const iniciarEscuchaRef = useRef<() => Promise<void>>(async () => {});
  // Ventana de silencio — mientras Date.now() < silencioHastaRef, el mic NO abre.
  // Evita que el mic capture el TTS del simulador Python como comandos de voz.
  const silencioHastaRef = useRef<number>(0);

  const whisper = useWhisperWASM();

  const agregarLog = useCallback(
    (mensaje: string, tipo: "info" | "correcto" | "error" | "voz" | "sistema" = "info") => {
      setEstadoJuego((prev) => ({
        ...prev,
        log: [
          { id: contadorLog++, ts: Date.now(), mensaje, tipo },
          ...prev.log.slice(0, 99), // máximo 100 entradas
        ],
      }));
    },
    []
  );

  // ---- Enviar comando al servidor Python via WebSocket ----
  const enviarComando = useCallback((comando: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ tipo: "comando", comando }));
    }
  }, []);

  // ---- Escucha de voz con Whisper WASM (igual que en modo Serial) ----
  const iniciarEscuchaVoz = useCallback(async () => {
    if (escuchandoVozRef.current || !whisper.modeloCargado) return;
    // No abrir el mic durante la ventana de silencio (TTS hablando)
    if (Date.now() < silencioHastaRef.current) {
      escuchandoVozRef.current = false;
      return;
    }
    escuchandoVozRef.current = true;

    // Solo loguear "Escuchando..." cuando el juego realmente pide voz
    if (estadoRef.current === "LISTENING") {
      agregarLog("Escuchando... habla ahora", "sistema");
    }

    try {
      const textoRaw = await whisper.escuchar();
      const comando  = textoAComando(textoRaw);

      // Solo loguear en LISTENING — en IDLE/GAMEOVER escuchamos en segundo plano sin spam
      if (textoRaw && estadoRef.current === "LISTENING") {
        agregarLog(`"${textoRaw}" → ${comando}`, "voz");
      }

      setEstadoJuego((prev) => ({
        ...prev,
        ultimoTextoWhisper:    textoRaw || prev.ultimoTextoWhisper,
        ultimaDeteccion:       comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
        whisperTranscribiendo: false,
      }));

      if (comando !== "DESCONOCIDO") {
        enviarComando(comando);
      }
    } catch (err) {
      agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
      setEstadoJuego((prev) => ({ ...prev, whisperTranscribiendo: false }));
    } finally {
      escuchandoVozRef.current = false;
    }
  }, [whisper, agregarLog, enviarComando]);

  // Mantener la ref siempre apuntando a la versión actualizada
  useEffect(() => {
    iniciarEscuchaRef.current = iniciarEscuchaVoz;
  }, [iniciarEscuchaVoz]);

  // Bucle continuo de escucha — activo para todos los estados que aceptan voz
  const bucleVoz = useCallback(async () => {
    const dormir = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
    while (bucleVozActivoRef.current) {
      if (ESTADOS_ESCUCHA.has(estadoRef.current)) {
        const t = Date.now();
        await iniciarEscuchaRef.current();
        if (!bucleVozActivoRef.current) break;
        const elapsed = Date.now() - t;
        // Retorno rápido (< 300ms): modelo aún no listo o ya escuchando → espera corta
        // En LISTENING: espera 1.5s para que el juego procese antes de volver a escuchar.
        // En otros estados (IDLE, GAMEOVER): espera más para no saturar con alucinaciones.
        const enEscuchaActiva = estadoRef.current === "LISTENING";
        await dormir(elapsed < 300 ? 400 : enEscuchaActiva ? 1500 : 3000);
      } else {
        await dormir(200);
      }
    }
  }, []); // sin deps: usa solo refs

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
            // Nuevo ciclo: limpiar datos del turno anterior
            if (msg.estado === "SHOWING") {
              whisper.cancelarEscucha();
              siguiente.ultimaDeteccion    = null;
              siguiente.ultimoTextoWhisper = null;
              siguiente.ultimoResultado    = null;
            }
            // Cuando empieza LISTENING: limpiar ventana de silencio para escuchar de inmediato
            if (msg.estado === "LISTENING") {
              silencioHastaRef.current = 0;
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
              // TTS dice "Correcto. Nivel N." (~2s) — silenciar mic
              silencioHastaRef.current = Date.now() + 2500;
            } else if (msg.resultado === "WRONG") {
              agregarLog("Incorrecto ✗", "error");
              // TTS dice "Incorrecto. Di empieza para intentar de nuevo." (~4s)
              silencioHastaRef.current = Date.now() + 4500;
            } else {
              agregarLog("Tiempo agotado ⏱", "error");
              // TTS dice "Tiempo agotado. Di empieza para intentar de nuevo." (~4s)
              silencioHastaRef.current = Date.now() + 4500;
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
            // TTS dice "Fin del juego. Obtuviste X puntos. Di empieza para volver a jugar." (~6s)
            silencioHastaRef.current = Date.now() + 7000;
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

  const conectar = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    agregarLog(`Conectando a ${WS_URL}...`, "sistema");
    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      setEstadoJuego((prev) => ({ ...prev, conectado: true }));
      agregarLog("Conexión WebSocket establecida", "sistema");
      // Silenciar mic durante la narración de bienvenida del TTS Python (~7s)
      silencioHastaRef.current = Date.now() + 8000;
      // Arrancar el bucle continuo de voz
      bucleVozActivoRef.current = true;
      bucleVoz();
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
      bucleVozActivoRef.current = false;
      whisper.cancelarEscucha();
      setEstadoJuego((prev) => ({ ...prev, conectado: false }));
      agregarLog("Conexión cerrada", "sistema");
      ws.current = null;
    };

    ws.current = socket;
  }, [agregarLog, procesarMensaje, bucleVoz, whisper]);

  const desconectar = useCallback(() => {
    bucleVozActivoRef.current = false;
    whisper.cancelarEscucha();
    ws.current?.close();
  }, [whisper]);

  const limpiarLog = useCallback(() => {
    setEstadoJuego((prev) => ({ ...prev, log: [] }));
  }, []);

  useEffect(() => {
    return () => {
      ws.current?.close();
    };
  }, []);

  // El badge de "Habla ahora" solo se muestra cuando el juego está en LISTENING.
  // En IDLE/GAMEOVER el bucle escucha en silencio para detectar "empieza".
  const enListening = estadoJuego.estado === "LISTENING";

  const estadoConWhisper: EstadoCliente = {
    ...estadoJuego,
    whisperCargado:        whisper.modeloCargado,
    whisperTranscribiendo: whisper.transcribiendo && enListening,
  };

  return {
    estadoJuego:              estadoConWhisper,
    conectar,
    desconectar,
    limpiarLog,
    reiniciar: () => {
      enviarComando("REINICIAR");
      setEstadoJuego((prev) => ({ ...prev, log: [] }));
    },
    whisperProgresoDescarga:  whisper.progresoDescarga,
    whisperNivelMic:          enListening ? whisper.nivelMic : 0,
    whisperGrabando:          whisper.grabando && enListening,
    whisperMicAbierto:        whisper.micAbierto && enListening,
    whisperProcesando:        whisper.procesando && enListening,
    whisperTiempoRestante:    enListening ? whisper.tiempoRestante : null,
  };
}
