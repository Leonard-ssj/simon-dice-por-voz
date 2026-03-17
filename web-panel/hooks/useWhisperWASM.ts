"use client";

// ============================================================
// hooks/useWhisperWASM.ts — Whisper en el browser (WASM)
// Graba el micrófono con VAD y transcribe con Whisper WASM.
// El modelo corre en un Web Worker para no bloquear la UI.
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";

// ---- Parámetros de captura de audio ----
const SAMPLE_RATE       = 16000;  // Hz — mismo que Whisper espera
const BUFFER_SIZE       = 4096;   // muestras por bloque (~256ms a 16kHz)
const VAD_THRESHOLD     = 0.015;  // RMS mínimo para considerar voz (reducido de 0.025)
const BLOQUES_CONFIRMAR = 1;     // bloques consecutivos para confirmar voz
const SILENCIO_TOLERADO = 500;   // ms de silencio para cortar — corto para capturar UNA PALABRA rápido
const DURACION_MINIMA   = 150;   // ms mínimos de audio para enviar a Whisper
const TIMEOUT_GRABACION = 8000;  // ms máximos esperando voz antes de timeout

// ---- Tipos internos del worker ----
type MsgWorker =
  | { tipo: "listo" }
  | { tipo: "progreso"; mensaje: string }
  | { tipo: "resultado"; texto: string }
  | { tipo: "error"; mensaje: string };

// ---- RMS helper ----
function calcularRMS(buffer: Float32Array): number {
  let suma = 0;
  for (let i = 0; i < buffer.length; i++) suma += buffer[i] * buffer[i];
  return Math.sqrt(suma / buffer.length);
}

// ============================================================

export interface UseWhisperWASMReturn {
  modeloCargado:    boolean;
  transcribiendo:   boolean;
  progresoDescarga: string;
  nivelMic:         number;        // RMS actual del mic normalizado 0-1 (para la barra de nivel)
  grabando:         boolean;       // true cuando VAD detectó voz y está grabando activamente
  tiempoRestante:   number | null; // countdown en segundos hasta timeout (null = no escuchando)
  escuchar:         () => Promise<string>;
  cancelarEscucha:  () => void;
}

export function useWhisperWASM(): UseWhisperWASMReturn {
  const [modeloCargado,    setModeloCargado]    = useState(false);
  const [transcribiendo,   setTranscribiendo]   = useState(false);
  const [progresoDescarga, setProgresoDescarga] = useState("");
  const [nivelMic,         setNivelMic]         = useState(0);
  const [grabando,         setGrabando]         = useState(false);
  const [tiempoRestante,   setTiempoRestante]   = useState<number | null>(null);

  const workerRef   = useRef<Worker | null>(null);
  const cancelarRef = useRef(false);
  const resolverRef = useRef<((texto: string) => void) | null>(null);

  // ---- Inicializar worker al montar ----
  useEffect(() => {
    const worker = new Worker(
      new URL("../workers/whisper.worker.ts", import.meta.url)
    );

    worker.onmessage = (e: MessageEvent<MsgWorker>) => {
      const msg = e.data;
      if (msg.tipo === "listo") {
        setModeloCargado(true);
        setProgresoDescarga("");
      } else if (msg.tipo === "progreso") {
        setProgresoDescarga(msg.mensaje);
      } else if (msg.tipo === "resultado") {
        setTranscribiendo(false);
        resolverRef.current?.(msg.texto);
        resolverRef.current = null;
      } else if (msg.tipo === "error") {
        console.error("[Whisper Worker]", msg.mensaje);
        setTranscribiendo(false);
        resolverRef.current?.("");
        resolverRef.current = null;
      }
    };

    workerRef.current = worker;
    worker.postMessage({ tipo: "cargar" });

    return () => {
      worker.terminate();
      workerRef.current = null;
    };
  }, []);

  // ---- Cancelar grabación en curso ----
  const cancelarEscucha = useCallback(() => {
    cancelarRef.current = true;
  }, []);

  // ---- Grabar micrófono con VAD y transcribir ----
  const escuchar = useCallback((): Promise<string> => {
    return new Promise((resolve) => {
      if (!modeloCargado || transcribiendo) {
        resolve("");
        return;
      }

      cancelarRef.current = false;
      resolverRef.current = resolve;
      setTranscribiendo(true);

      let audioCtx:       AudioContext | null      = null;
      let sourceNode:     MediaStreamAudioSourceNode | null = null;
      let processorNode:  ScriptProcessorNode | null = null;
      let stream:         MediaStream | null       = null;
      let timeoutHandle:  ReturnType<typeof setTimeout> | null   = null;
      let silencioHandle: ReturnType<typeof setTimeout> | null   = null;
      let countdownInterval: ReturnType<typeof setInterval> | null = null;

      const muestrasAcumuladas: Float32Array[] = [];
      let duracionMs        = 0;
      let grabandoVoz       = false;
      let bloquesVoz        = 0;
      let finalizado        = false;

      function terminar(motivo: "silencio" | "timeout" | "cancelado") {
        if (finalizado) return;
        finalizado = true;

        // Limpiar timers
        if (timeoutHandle)     clearTimeout(timeoutHandle);
        if (silencioHandle)    clearTimeout(silencioHandle);
        if (countdownInterval) clearInterval(countdownInterval);

        // Limpiar audio
        processorNode?.disconnect();
        sourceNode?.disconnect();
        stream?.getTracks().forEach((t) => t.stop());
        try { audioCtx?.close(); } catch {}

        // Resetear indicadores UI
        setNivelMic(0);
        setGrabando(false);
        setTiempoRestante(null);

        if (motivo === "cancelado" || muestrasAcumuladas.length === 0 || duracionMs < DURACION_MINIMA) {
          setTranscribiendo(false);
          resolve("");
          resolverRef.current = null;
          return;
        }

        // Concatenar y enviar al worker
        const totalMuestras = muestrasAcumuladas.reduce((acc, b) => acc + b.length, 0);
        const audio = new Float32Array(totalMuestras);
        let offset = 0;
        for (const bloque of muestrasAcumuladas) {
          audio.set(bloque, offset);
          offset += bloque.length;
        }

        workerRef.current?.postMessage({ tipo: "transcribir", audio }, [audio.buffer]);
        // resolve() se llama desde onmessage cuando llega el resultado
      }

      async function iniciarGrabacion() {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              sampleRate:       SAMPLE_RATE,
              channelCount:     1,
              echoCancellation: true,
              noiseSuppression: true,
            },
          });

          audioCtx      = new AudioContext({ sampleRate: SAMPLE_RATE });
          sourceNode    = audioCtx.createMediaStreamSource(stream);
          processorNode = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);

          // Countdown desde que abre el mic
          const inicioEscucha = Date.now();
          setTiempoRestante(Math.round(TIMEOUT_GRABACION / 1000));
          countdownInterval = setInterval(() => {
            const elapsed    = Date.now() - inicioEscucha;
            const remaining  = Math.max(0, Math.round((TIMEOUT_GRABACION - elapsed) / 1000));
            setTiempoRestante(remaining);
          }, 500);

          processorNode.onaudioprocess = (e) => {
            if (finalizado || cancelarRef.current) {
              if (!finalizado) terminar("cancelado");
              return;
            }

            const canal    = e.inputBuffer.getChannelData(0);
            const rms      = calcularRMS(canal);
            const msBloque = (BUFFER_SIZE / SAMPLE_RATE) * 1000;

            // Actualizar barra de nivel de micrófono (normalizado 0-1)
            setNivelMic(Math.min(1, rms / (VAD_THRESHOLD * 4)));

            if (rms >= VAD_THRESHOLD) {
              bloquesVoz++;
              if (bloquesVoz >= BLOQUES_CONFIRMAR) {
                if (!grabandoVoz) {
                  grabandoVoz = true;
                  setGrabando(true);  // VAD confirmado — grabando voz activamente
                }
                if (silencioHandle) {
                  clearTimeout(silencioHandle);
                  silencioHandle = null;
                }
              }
            } else {
              bloquesVoz = 0;
              if (grabandoVoz && !silencioHandle) {
                silencioHandle = setTimeout(() => terminar("silencio"), SILENCIO_TOLERADO);
              }
            }

            if (grabandoVoz) {
              muestrasAcumuladas.push(new Float32Array(canal));
              duracionMs += msBloque;
            }
          };

          sourceNode.connect(processorNode);
          processorNode.connect(audioCtx.destination);

          timeoutHandle = setTimeout(() => terminar("timeout"), TIMEOUT_GRABACION);
        } catch (err) {
          console.error("[Whisper VAD] Error accediendo al micrófono:", err);
          setTranscribiendo(false);
          setNivelMic(0);
          setGrabando(false);
          setTiempoRestante(null);
          resolve("");
          resolverRef.current = null;
        }
      }

      iniciarGrabacion();
    });
  }, [modeloCargado, transcribiendo]);

  return {
    modeloCargado,
    transcribiendo,
    progresoDescarga,
    nivelMic,
    grabando,
    tiempoRestante,
    escuchar,
    cancelarEscucha,
  };
}
