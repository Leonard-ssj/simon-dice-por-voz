"use client";

// ============================================================
// hooks/useWebSerial.ts — Modo ESP32 (producción)
//
// Conecta directamente al ESP32 via Web Serial API (Chrome/Edge).
// El browser graba el micrófono, transcribe con Whisper WASM y
// escribe el comando reconocido por Serial: "ROJO\n"
//
// El ESP32 recibe el texto del comando y corre el juego
// (LEDs físicos, buzzer, lógica). No graba audio propio.
//
// Bucle continuo de voz (bucleVoz): escucha en todos los estados
// que aceptan comandos: IDLE, LISTENING, PAUSA, GAMEOVER.
//
// Requisito: Chrome o Edge (Web Serial API no disponible en Firefox).
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoCliente, EstadoJuego, ColorJuego, ResultadoTurno } from "../types/game";
import { useWhisperWASM } from "./useWhisperWASM";
import { textoAComando } from "../lib/validador";

// Estados del juego en los que el browser debe escuchar comandos de voz
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

  const puertoRef         = useRef<any>(null);
  const escritorRef       = useRef<WritableStreamDefaultWriter | null>(null);
  const leyendoRef        = useRef(false);
  const escuchandoVozRef  = useRef(false);
  const bucleVozActivoRef = useRef(false);
  const estadoRef         = useRef<EstadoJuego>("IDLE");
  // Ref que siempre apunta a la versión más reciente de iniciarEscuchaVoz
  const iniciarEscuchaRef = useRef<() => Promise<void>>(async () => {});
  // Ventana de silencio — mientras Date.now() < silencioHastaRef, el mic NO abre.
  // Evita que el mic capture el TTS del simulador Python como comandos de voz.
  const silencioHastaRef = useRef<number>(0);

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

  // ---- Grabación de voz + Whisper ----

  const iniciarEscuchaVoz = useCallback(async () => {
    if (escuchandoVozRef.current || !whisper.modeloCargado) return;
    // No abrir el mic durante la ventana de silencio (TTS hablando)
    if (Date.now() < silencioHastaRef.current) {
      escuchandoVozRef.current = false;
      return;
    }
    escuchandoVozRef.current = true;

    setEstadoJuego((prev) => ({ ...prev, whisperTranscribiendo: true }));
    agregarLog("Escuchando... habla ahora", "sistema");

    try {
      const textoRaw = await whisper.escuchar();
      const comando  = textoAComando(textoRaw);

      // Solo loguear en LISTENING — en IDLE/GAMEOVER escuchamos en segundo plano sin spam
      if (textoRaw && estadoRef.current === "LISTENING") {
        agregarLog(`"${textoRaw}" → ${comando}`, "voz");
      }

      setEstadoJuego((prev) => ({
        ...prev,
        ultimoTextoWhisper:  textoRaw || prev.ultimoTextoWhisper,
        ultimaDeteccion:     comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
        whisperTranscribiendo: false,
      }));

      if (comando !== "DESCONOCIDO") {
        await enviarComandoSerial(comando);
      }
    } catch (err) {
      agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
      setEstadoJuego((prev) => ({ ...prev, whisperTranscribiendo: false }));
    } finally {
      escuchandoVozRef.current = false;
    }
  }, [whisper, agregarLog, enviarComandoSerial]);

  // Mantener la ref siempre apuntando a la versión actualizada
  useEffect(() => {
    iniciarEscuchaRef.current = iniciarEscuchaVoz;
  }, [iniciarEscuchaVoz]);

  // Bucle continuo de escucha — activo para todos los estados que aceptan voz.
  // Sin deps: usa solo refs para evitar problemas de closure estale.
  const bucleVoz = useCallback(async () => {
    const dormir = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
    while (bucleVozActivoRef.current) {
      if (ESTADOS_ESCUCHA.has(estadoRef.current)) {
        const t = Date.now();
        await iniciarEscuchaRef.current();
        if (!bucleVozActivoRef.current) break;
        const elapsed = Date.now() - t;
        // Retorno rápido (< 300ms): modelo no listo o ya escuchando → espera corta
        // Sesión real completada: espera 1.5s para que el ESP32 procese el comando
        // antes de volver a escuchar. Evita disparos en cadena de alucinaciones.
        await dormir(elapsed < 300 ? 400 : 1500);
      } else {
        await dormir(200);
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Procesar líneas de texto del ESP32 ----

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

          // Al entrar en SHOWING no se necesita voz — cancelar si hubiera grabación activa
          if (nuevoEstado === "SHOWING") {
            whisper.cancelarEscucha();
          }
          if (nuevoEstado === "IDLE" || nuevoEstado === "SHOWING") {
            siguiente.esperado = null;
          }
          if (nuevoEstado !== "SHOWING") {
            siguiente.ledActivo = null;
          }
          // Cuando empieza LISTENING: limpiar ventana de silencio para escuchar de inmediato
          if (nuevoEstado === "LISTENING") {
            silencioHastaRef.current = 0;
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
            silencioHastaRef.current = Date.now() + 2500;
          } else if (siguiente.ultimoResultado === "WRONG") {
            agregarLog("Incorrecto ✗", "error");
            silencioHastaRef.current = Date.now() + 4500;
          } else {
            agregarLog("Tiempo agotado ⏱", "error");
            silencioHastaRef.current = Date.now() + 4500;
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
          // TTS dice "Fin del juego. Obtuviste X puntos. Di empieza para volver a jugar." (~6s)
          silencioHastaRef.current = Date.now() + 7000;
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
      agregarLog("Conectado al ESP32 por Web Serial", "sistema");
      // Silenciar mic brevemente al conectar (no hay TTS de bienvenida en modo serial)
      silencioHastaRef.current = Date.now() + 3000;

      // Arrancar el bucle continuo de voz
      bucleVozActivoRef.current = true;
      bucleVoz();

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
  }, [webSerialDisponible, whisper.modeloCargado, agregarLog, procesarLinea, bucleVoz]);

  // ---- Desconectar ----

  const desconectar = useCallback(async () => {
    bucleVozActivoRef.current = false;
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

  // Badge solo visible en LISTENING — en otros estados escucha en segundo plano
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
    webSerialDisponible,
    reiniciar: () => {
      enviarComandoSerial("REINICIAR");
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
