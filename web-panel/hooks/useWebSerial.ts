"use client";

// ============================================================
// hooks/useWebSerial.ts — Modo ESP32 (producción)
//
// Conecta directamente al ESP32 via Web Serial API (Chrome/Edge).
// Baud rate: 921600 (necesario para audio PTT del INMP441).
//
// Reconocimiento de voz — tres modos (prioridad en orden):
//
//   Modo A — Botón físico (SW1/SW2) + INMP441 (mejor):
//     ESP32 envía BTN_INICIO → ESP32 captura audio en PSRAM
//     → ESP32 envía AUDIO:START:N + base64 + AUDIO:END
//     → browser reenvía audio a servidor_voz (Whisper Python)
//     → servidor_voz devuelve comando → browser envía "ROJO\n"
//
//   Modo B — Teclado/botón UI + mic browser + Python Whisper:
//     PTT_INICIO\n → Serial (pausa timeout ESP32)
//     PTT_INICIO → WS servidor_voz (mic de la PC)
//     PTT_FIN → WS → servidor_voz transcribe → devuelve voz
//     PTT_FIN\n + ROJO\n → Serial
//
//   Modo C — Teclado/botón UI + Whisper WASM (fallback automático):
//     PTT_INICIO\n → Serial (pausa timeout ESP32)
//     WASM graba y transcribe en browser
//     PTT_FIN\n + ROJO\n → Serial
//
// TTS: window.speechSynthesis anuncia cambios de estado.
// Requisito: Chrome o Edge (Web Serial API no soportado en Firefox).
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoCliente, EstadoJuego, ColorJuego, ResultadoTurno } from "../types/game";
import { useWhisperWASM } from "./useWhisperWASM";
import { textoAComando } from "../lib/validador";

const ESTADOS_ESCUCHA = new Set<string>(["IDLE", "LISTENING", "PAUSA", "GAMEOVER"]);
const BAUD_RATE       = 921600;   // 921600 para soportar audio PTT del INMP441
const WS_VOZ_URL      = "ws://localhost:8766";

let contadorLog = 0;

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
  dispositivoMic:        null,
  dispositivoSpeaker:    null,
  whisperModelo:         null,
  log:                   [],
};

// ---- TTS del browser ----
function tts(texto: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(texto);
  u.lang  = "es-MX";
  u.rate  = 1.0;
  window.speechSynthesis.speak(u);
}

export function useWebSerial() {
  const [estadoJuego, setEstadoJuego] = useState<EstadoCliente>(ESTADO_INICIAL);

  const puertoRef         = useRef<any>(null);
  const escritorRef       = useRef<WritableStreamDefaultWriter | null>(null);
  const leyendoRef        = useRef(false);
  const escuchandoRef     = useRef(false);
  const estadoRef         = useRef<EstadoJuego>("IDLE");
  const iniciarPTTRef     = useRef<() => void>(() => {});

  // WebSocket hacia servidor_voz (Python Whisper local)
  const wsVozRef          = useRef<WebSocket | null>(null);
  const wsVozActivoRef    = useRef(false);   // true = servidor_voz conectado y listo

  // Acumulación de audio base64 enviado por el ESP32 (botón físico)
  const audioModoRef      = useRef(false);       // true mientras llegan líneas base64
  const audioTotalRef     = useRef(0);           // bytes esperados (del header)
  const audioLineasRef    = useRef<string[]>([]); // líneas base64 acumuladas

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

  // ---- Relay de audio ESP32 → servidor_voz / WASM ----
  const procesarAudioFinal = useCallback(async (lineasB64: string[]) => {
    agregarLog("Audio PTT recibido del INMP441 — transcribiendo...", "voz");

    // Decodificar base64 → ArrayBuffer
    const b64 = lineasB64.join("");
    const binStr = atob(b64);
    const bytes  = new Uint8Array(binStr.length);
    for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);

    // Int16 little-endian → Float32 normalizado para Whisper
    const samples = bytes.length / 2;
    const float32 = new Float32Array(samples);
    const view    = new DataView(bytes.buffer);
    for (let i = 0; i < samples; i++) {
      float32[i] = view.getInt16(i * 2, true) / 32768.0;
    }

    let texto  = "";
    let comando = "DESCONOCIDO";

    if (wsVozActivoRef.current && wsVozRef.current?.readyState === WebSocket.OPEN) {
      // Enviar al servidor_voz como Float32Array binario
      wsVozRef.current.send(JSON.stringify({ tipo: "audio_float32", datos: Array.from(float32) }));
      // La respuesta llega por ws.onmessage → no esperamos aquí
      return;
    }

    // Fallback WASM
    try {
      const res = await whisper.transcribirAudio(float32);
      texto   = res.texto ?? "";
      comando = textoAComando(texto);
    } catch (e) {
      agregarLog(`Error WASM: ${e}`, "error");
    }

    if (texto) agregarLog(`"${texto}" → ${comando}`, "voz");
    setEstadoJuego((prev) => ({
      ...prev,
      ultimoTextoWhisper: texto || prev.ultimoTextoWhisper,
      ultimaDeteccion:    comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
    }));
    await enviarComandoSerial("PTT_FIN");
    if (comando !== "DESCONOCIDO") await enviarComandoSerial(comando);
  }, [agregarLog, whisper, enviarComandoSerial]);

  // ---- Conectar servidor_voz (intento silencioso) ----
  const conectarVozWS = useCallback(() => {
    if (typeof WebSocket === "undefined") return;

    const ws = new WebSocket(WS_VOZ_URL);
    wsVozRef.current = ws;

    ws.onopen = () => {
      // esperamos el mensaje "ready" para confirmar que Whisper cargó
    };

    ws.onmessage = (ev) => {
      try {
        const datos = JSON.parse(ev.data);

        if (datos.tipo === "ready") {
          if (datos.whisperDisponible) {
            wsVozActivoRef.current = true;
            setEstadoJuego((prev) => ({
              ...prev,
              whisperModelo:  datos.whisperModelo ?? prev.whisperModelo,
              dispositivoMic: datos.dispositivoMic ?? prev.dispositivoMic,
            }));
            agregarLog("Servidor de voz Python conectado (Whisper local activo)", "sistema");
          } else {
            ws.close();
          }
        }

        // Respuesta de transcripción tras PTT_FIN (teclado) o audio_float32 (botón físico)
        if (datos.tipo === "voz") {
          const texto   = datos.texto   as string;
          const comando = datos.comando as string;

          if (texto) {
            agregarLog(`"${texto}" → ${comando}`, "voz");
          }
          setEstadoJuego((prev) => ({
            ...prev,
            ultimoTextoWhisper: texto || prev.ultimoTextoWhisper,
            ultimaDeteccion:    comando !== "DESCONOCIDO" ? comando : prev.ultimaDeteccion,
          }));

          // Reanudar timeout en ESP32 y enviar comando
          enviarComandoSerial("PTT_FIN").then(() => {
            if (comando !== "DESCONOCIDO") {
              enviarComandoSerial(comando);
            }
          });

          escuchandoRef.current = false;
        }

        // Confirmación de ptt_estado del servidor (opcional, para UI)
        if (datos.tipo === "ptt_estado") {
          agregarLog(`Mic: ${datos.estado}`, "info");
        }
      } catch {}
    };

    ws.onclose = () => {
      wsVozActivoRef.current = false;
      wsVozRef.current       = null;
    };

    ws.onerror = () => {
      // servidor_voz no disponible — fallback WASM silencioso
      wsVozActivoRef.current = false;
      wsVozRef.current       = null;
    };
  }, [agregarLog, enviarComandoSerial]);

  // ---- PTT: iniciar grabación ----
  const iniciarPTTVoz = useCallback(async () => {
    if (escuchandoRef.current) return;
    if (!ESTADOS_ESCUCHA.has(estadoRef.current)) return;

    escuchandoRef.current = true;

    // Pausa el timeout del ESP32
    await enviarComandoSerial("PTT_INICIO");

    if (wsVozActivoRef.current && wsVozRef.current?.readyState === WebSocket.OPEN) {
      // Modo A — Python Whisper local
      // El servidor abre el mic; cuando el usuario suelte PTT enviamos PTT_FIN al WS.
      // La respuesta voz llegará por ws.onmessage y completará el flujo.
      wsVozRef.current.send(JSON.stringify({ tipo: "control", accion: "PTT_INICIO" }));
      // escuchandoRef se libera en ws.onmessage cuando llega "voz"
    } else {
      // Modo B — Whisper WASM en browser
      try {
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

        await enviarComandoSerial("PTT_FIN");
        if (comando !== "DESCONOCIDO") {
          await enviarComandoSerial(comando);
        }
      } catch (err) {
        agregarLog(`Error en reconocimiento de voz: ${err}`, "error");
        await enviarComandoSerial("PTT_FIN"); // reanudar timeout aunque falle
      } finally {
        escuchandoRef.current = false;
      }
    }
  }, [whisper, agregarLog, enviarComandoSerial]);

  // PTT_FIN al servidor_voz cuando el usuario suelta la tecla (solo modo A)
  const finalizarPTTVoz = useCallback(() => {
    whisper.finalizarGrabacion(); // para WASM (no-op si no está grabando)
    if (wsVozActivoRef.current && wsVozRef.current?.readyState === WebSocket.OPEN) {
      wsVozRef.current.send(JSON.stringify({ tipo: "control", accion: "PTT_FIN" }));
    }
  }, [whisper]);

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
      finalizarPTTVoz();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup",   handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup",   handleKeyUp);
    };
  }, [estadoJuego.conectado, finalizarPTTVoz]); // eslint-disable-line

  // ---- Procesar líneas del ESP32 ----
  const procesarLinea = useCallback(
    (linea: string) => {
      if (!linea) return;

      setEstadoJuego((prev) => {
        const siguiente = { ...prev };

        // ── Audio PTT desde botón físico ESP32 ──────────────────
        if (linea === "BTN_INICIO") {
          // El jugador presionó SW1/SW2 en el kit físico
          agregarLog("Botón PTT presionado — grabando INMP441...", "voz");
          audioModoRef.current   = false;
          audioTotalRef.current  = 0;
          audioLineasRef.current = [];
          return siguiente;
        }

        if (linea.startsWith("AUDIO:START:")) {
          const n = parseInt(linea.slice(12));
          audioModoRef.current   = true;
          audioTotalRef.current  = n;
          audioLineasRef.current = [];
          agregarLog(`Recibiendo audio (${n} bytes)...`, "info");
          return siguiente;
        }

        if (linea === "AUDIO:END") {
          audioModoRef.current = false;
          const lineas = audioLineasRef.current;
          audioLineasRef.current = [];
          // Procesar en background — no bloquea el loop de lectura
          procesarAudioFinal(lineas);
          return siguiente;
        }

        if (linea === "AUDIO:VACIO") {
          agregarLog("Sin audio capturado (botón muy corto)", "info");
          return siguiente;
        }

        // Línea de datos base64 dentro de AUDIO:START...AUDIO:END
        if (audioModoRef.current) {
          audioLineasRef.current.push(linea);
          return siguiente;
        }
        // ────────────────────────────────────────────────────────

        if (linea === "READY") {
          agregarLog("ESP32 listo", "sistema");
          tts("ESP32 listo. Presiona espacio para hablar.");
        } else if (linea.startsWith("STATE:")) {
          const nuevoEstado = linea.slice(6) as EstadoJuego;
          siguiente.estado = nuevoEstado;
          estadoRef.current = nuevoEstado;

          if (nuevoEstado === "SHOWING") {
            whisper.cancelarEscucha();
            tts("Mira y escucha.");
          }
          if (nuevoEstado === "LISTENING") {
            tts("Tu turno. Presiona espacio para hablar.");
          }
          if (nuevoEstado === "PAUSA") {
            tts("Juego pausado.");
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
            tts("Correcto.");
          } else if (siguiente.ultimoResultado === "WRONG") {
            agregarLog("Incorrecto ✗", "error");
            tts("Incorrecto. Di empieza para intentar de nuevo.");
          } else {
            agregarLog("Tiempo agotado ⏱", "error");
            tts("Tiempo agotado. Di empieza para intentar de nuevo.");
          }
        } else if (linea.startsWith("SEQUENCE:")) {
          siguiente.secuencia = linea.slice(9).split(",") as ColorJuego[];
        } else if (linea.startsWith("EXPECTED:")) {
          siguiente.esperado = linea.slice(9) as ColorJuego;
        } else if (linea.startsWith("LEVEL:")) {
          siguiente.nivel = parseInt(linea.slice(6));
          agregarLog(`Nivel ${siguiente.nivel}`, "sistema");
          if (siguiente.nivel > 1) tts(`Nivel ${siguiente.nivel}.`);
        } else if (linea.startsWith("SCORE:")) {
          siguiente.puntuacion = parseInt(linea.slice(6));
        } else if (linea === "GAMEOVER") {
          siguiente.estado = "GAMEOVER";
          estadoRef.current = "GAMEOVER";
          siguiente.esperado = null;
          siguiente.ultimaDeteccion = null;
          siguiente.ultimoTextoWhisper = null;
          agregarLog(`Fin del juego — Puntuación: ${prev.puntuacion}`, "error");
          tts(`Fin del juego. Obtuviste ${prev.puntuacion} puntos. Di empieza para volver a jugar.`);
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

    // Intentar conectar servidor_voz en segundo plano (sin bloquear)
    conectarVozWS();

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
  }, [webSerialDisponible, agregarLog, procesarLinea, conectarVozWS]);

  // ---- Desconectar ----
  const desconectar = useCallback(async () => {
    leyendoRef.current = false;
    whisper.cancelarEscucha();
    wsVozRef.current?.close();
    wsVozActivoRef.current = false;
    try {
      await escritorRef.current?.close();
      await puertoRef.current?.close();
    } catch {}
    puertoRef.current   = null;
    escritorRef.current = null;
    setEstadoJuego((prev) => ({ ...prev, conectado: false }));
    agregarLog("Desconectado del ESP32", "sistema");
  }, [agregarLog, whisper]);

  const puedoHablar = ESTADOS_ESCUCHA.has(estadoJuego.estado) && estadoJuego.conectado;

  const estadoConWhisper: EstadoCliente = {
    ...estadoJuego,
    whisperCargado:        wsVozActivoRef.current || whisper.modeloCargado,
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
    whisperLocalActivo:      wsVozActivoRef.current,
    iniciarPTT:              iniciarPTTVoz,
    finalizarPTT:            finalizarPTTVoz,
    puedoHablar,
  };
}
