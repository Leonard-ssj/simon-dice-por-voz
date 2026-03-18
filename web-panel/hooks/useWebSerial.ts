"use client";

// ============================================================
// hooks/useWebSerial.ts — Modo ESP32 (producción)
//
// Conecta directamente al ESP32 via Web Serial API (Chrome/Edge).
// Reconocimiento de voz: Push-to-Talk (PTT).
//   Barra espaciadora (o botón) → abre mic → usuario habla
//   → suelta → Whisper WASM transcribe → "ROJO\n" al ESP32.
//
// Requisito: Chrome o Edge (Web Serial API no disponible en Firefox).
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoCliente, EstadoJuego, ColorJuego, ResultadoTurno } from "../types/game";
import { useWhisperWASM } from "./useWhisperWASM";
import { textoAComando } from "../lib/validador";

const ESTADOS_ESCUCHA = new Set<string>(["IDLE", "LISTENING", "PAUSA", "GAMEOVER"]);
const BAUD_RATE = 115200;

let contadorLog = 0;

const ESTADO_INICIAL: EstadoCliente = {
  conectado:            false,
  estado:               "IDLE",
  nivel:                1,
  puntuacion:           0,
  secuencia:            [],
  esperado:             null,
  ledActivo:            null,
  ultimaDeteccion:      null,
  ultimoTextoWhisper:   null,
  ultimoResultado:      null,
  whisperCargado:       false,
  whisperTranscribiendo: false,
  log:                  [],
};

export function useWebSerial() {
  const [estadoJuego, setEstadoJuego] = useState<EstadoCliente>(ESTADO_INICIAL);

  const puertoRef       = useRef<any>(null);
  const escritorRef     = useRef<WritableStreamDefaultWriter | null>(null);
  const leyendoRef      = useRef(false);
  const escuchandoRef   = useRef(false);
  const estadoRef       = useRef<EstadoJuego>("IDLE");
  const iniciarPTTRef   = useRef<() => void>(() => {});

  const whisper = useWhisperWASM();

  const webSerialDisponible =
    typeof window !== "undefined" && "serial" in navigator;

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

  const enviarComandoSerial = useCallback(async (comando: string) => {
    if (!escritorRef.current) return;
    try {
      await escritorRef.current.write(`${comando}\n`);
    } catch (e) {
      agregarLog(`Error al enviar comando: ${e}`, "error");
    }
  }, [agregarLog]);

  // ---- PTT: iniciar grabación ----
  const iniciarPTTVoz = useCallback(async () => {
    if (escuchandoRef.current || !whisper.modeloCargado) return;
    if (!ESTADOS_ESCUCHA.has(estadoRef.current)) return;

    escuchandoRef.current = true;

    try {
      // No enviamos WHISPER_PROCESANDO al ESP32 (firmware no lo entiende)
      const textoRaw = await whisper.escuchar(undefined, "ptt");
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
        await enviarComandoSerial(comando);
      }
    } catch (err) {
      agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
    } finally {
      escuchandoRef.current = false;
    }
  }, [whisper, agregarLog, enviarComandoSerial]);

  useEffect(() => {
    iniciarPTTRef.current = iniciarPTTVoz;
  }, [iniciarPTTVoz]);

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
      whisper.finalizarGrabacion();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup",   handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup",   handleKeyUp);
    };
  }, [estadoJuego.conectado, whisper.finalizarGrabacion]); // eslint-disable-line

  // ---- Procesar líneas del ESP32 ----
  const procesarLinea = useCallback(
    (linea: string) => {
      if (!linea) return;

      setEstadoJuego((prev) => {
        const siguiente = { ...prev };

        if (linea === "READY") {
          agregarLog("ESP32 listo", "sistema");
        } else if (linea.startsWith("STATE:")) {
          const nuevoEstado = linea.slice(6) as EstadoJuego;
          siguiente.estado = nuevoEstado;
          estadoRef.current = nuevoEstado;

          if (nuevoEstado === "SHOWING") {
            whisper.cancelarEscucha();
          }
          if (nuevoEstado === "IDLE" || nuevoEstado === "SHOWING") {
            siguiente.esperado = null;
          }
          if (nuevoEstado !== "SHOWING") {
            siguiente.ledActivo = null;
          }
          agregarLog(`Estado: ${nuevoEstado}`, "info");
        } else if (linea.startsWith("LED:")) {
          const color = linea.slice(4);
          siguiente.ledActivo = color === "OFF" ? null : color as ColorJuego;
        } else if (linea.startsWith("DETECTED:")) {
          siguiente.ultimaDeteccion = linea.slice(9);
          agregarLog(`Detectado: ${siguiente.ultimaDeteccion}`, "voz");
        } else if (linea.startsWith("RESULT:")) {
          siguiente.ultimoResultado = linea.slice(7) as ResultadoTurno;
          if (siguiente.ultimoResultado === "CORRECT") {
            agregarLog("Correcto ✓", "correcto");
          } else if (siguiente.ultimoResultado === "WRONG") {
            agregarLog("Incorrecto ✗", "error");
          } else {
            agregarLog("Tiempo agotado ⏱", "error");
          }
        } else if (linea.startsWith("SEQUENCE:")) {
          siguiente.secuencia = linea.slice(9).split(",") as ColorJuego[];
        } else if (linea.startsWith("EXPECTED:")) {
          siguiente.esperado = linea.slice(9) as ColorJuego;
        } else if (linea.startsWith("LEVEL:")) {
          siguiente.nivel = parseInt(linea.slice(6));
          agregarLog(`Nivel ${siguiente.nivel}`, "sistema");
        } else if (linea.startsWith("SCORE:")) {
          siguiente.puntuacion = parseInt(linea.slice(6));
        } else if (linea === "GAMEOVER") {
          siguiente.estado = "GAMEOVER";
          estadoRef.current = "GAMEOVER";
          siguiente.esperado = null;
          siguiente.ultimaDeteccion = null;
          siguiente.ultimoTextoWhisper = null;
          agregarLog(`Fin del juego — Puntuación: ${prev.puntuacion}`, "error");
        } else if (!linea.startsWith("//")) {
          agregarLog(linea, "info");
        }

        return siguiente;
      });
    },
    [agregarLog, whisper]
  );

  // ---- Conectar ----
  const conectar = useCallback(async () => {
    if (!webSerialDisponible) {
      agregarLog("Web Serial API no disponible. Usa Chrome o Edge.", "error");
      return;
    }
    if (!whisper.modeloCargado) {
      agregarLog("Esperando a que el modelo Whisper termine de cargar...", "sistema");
      return;
    }

    try {
      const puerto = await (navigator as any).serial.requestPort();
      await puerto.open({ baudRate: BAUD_RATE });
      puertoRef.current = puerto;

      const encoder = new TextEncoderStream();
      encoder.readable.pipeTo(puerto.writable);
      escritorRef.current = encoder.writable.getWriter();

      setEstadoJuego((prev) => ({ ...prev, conectado: true }));
      agregarLog("Conectado al ESP32. Presiona ESPACIO o el botón para hablar.", "sistema");

      leyendoRef.current = true;
      const decoder = new TextDecoderStream();
      puerto.readable.pipeTo(decoder.writable);
      const lector = decoder.readable.getReader();

      let buffer = "";
      while (leyendoRef.current) {
        const { value, done } = await lector.read();
        if (done) break;
        buffer += value;
        const lineas = buffer.split("\n");
        buffer = lineas.pop() ?? "";
        for (const linea of lineas) {
          procesarLinea(linea.replace(/\r/g, "").trim());
        }
      }
    } catch (e: any) {
      agregarLog(`Error: ${e.message}`, "error");
    }
  }, [webSerialDisponible, whisper.modeloCargado, agregarLog, procesarLinea]);

  // ---- Desconectar ----
  const desconectar = useCallback(async () => {
    leyendoRef.current = false;
    whisper.cancelarEscucha();
    try {
      await escritorRef.current?.close();
      await puertoRef.current?.close();
    } catch {}
    puertoRef.current = null;
    escritorRef.current = null;
    setEstadoJuego((prev) => ({ ...prev, conectado: false }));
    agregarLog("Desconectado del ESP32", "sistema");
  }, [agregarLog, whisper]);

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
    webSerialDisponible,
    reiniciar: () => {
      enviarComandoSerial("REINICIAR");
      setEstadoJuego((prev) => ({ ...prev, log: [] }));
    },
    whisperProgresoDescarga: whisper.progresoDescarga,
    whisperNivelMic:         puedoHablar ? whisper.nivelMic : 0,
    whisperGrabando:         whisper.grabando,
    whisperMicAbierto:       whisper.micAbierto,
    whisperProcesando:       whisper.procesando,
    whisperTiempoRestante:   whisper.tiempoRestante,
    iniciarPTT:              iniciarPTTVoz,
    finalizarPTT:            whisper.finalizarGrabacion,
    puedoHablar,
  };
}
