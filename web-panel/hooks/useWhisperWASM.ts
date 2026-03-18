"use client";

// ============================================================
// hooks/useWhisperWASM.ts — Whisper en el browser (WASM)
// Graba el micrófono y transcribe con Whisper WASM.
// El modelo corre en un Web Worker para no bloquear la UI.
//
// Modos de grabación:
//   "vad"  — VAD automático: graba cuando detecta voz por RMS
//   "ptt"  — Push-to-talk: graba desde que se llama escuchar()
//            hasta que se llama finalizarGrabacion()
// ============================================================

import { useCallback, useEffect, useRef, useState } from "react";

// ---- Parámetros de captura de audio ----
const SAMPLE_RATE       = 16000;  // Hz — mismo que Whisper espera
const BUFFER_SIZE       = 4096;   // muestras por bloque (~256ms a 16kHz)
const VAD_THRESHOLD     = 0.015;  // RMS mínimo para considerar voz
const BLOQUES_CONFIRMAR = 1;      // bloques consecutivos para confirmar voz
const SILENCIO_TOLERADO = 800;    // ms de silencio para cortar en modo VAD
const DURACION_MINIMA   = 300;    // ms mínimos de audio para enviar a Whisper (modo VAD)
const DURACION_MINIMA_PTT = 80;   // ms mínimos en modo PTT (el usuario controla)
const TIMEOUT_GRABACION = 15000;  // ms máximos grabando (safety en ambos modos)

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
  nivelMic:         number;        // RMS actual del mic normalizado 0-1
  grabando:         boolean;       // true cuando está grabando audio activamente
  micAbierto:       boolean;       // true cuando getUserMedia tuvo éxito
  procesando:       boolean;       // true mientras Whisper hace inferencia
  tiempoRestante:   number | null; // countdown en segundos (solo modo VAD)
  escuchar:         (onProcesandoInicio?: () => void, modo?: "vad" | "ptt") => Promise<string>;
  finalizarGrabacion: () => void;  // PTT: termina la grabación y envía a Whisper
  cancelarEscucha:  () => void;
}

export function useWhisperWASM(): UseWhisperWASMReturn {
  const [modeloCargado,    setModeloCargado]    = useState(false);
  const [transcribiendo,   setTranscribiendo]   = useState(false);
  const [progresoDescarga, setProgresoDescarga] = useState("");
  const [nivelMic,         setNivelMic]         = useState(0);
  const [grabando,         setGrabando]         = useState(false);
  const [micAbierto,       setMicAbierto]       = useState(false);
  const [procesando,       setProcesando]       = useState(false);
  const [tiempoRestante,   setTiempoRestante]   = useState<number | null>(null);

  const workerRef   = useRef<Worker | null>(null);
  const cancelarRef = useRef(false);
  const resolverRef = useRef<((texto: string) => void) | null>(null);
  // PTT: almacena la función terminar() para llamarla desde finalizarGrabacion()
  const terminarRef = useRef<((m: "silencio" | "timeout" | "cancelado") => void) | null>(null);

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
        setProcesando(false);
        setTranscribiendo(false);
        resolverRef.current?.(msg.texto);
        resolverRef.current = null;
      } else if (msg.tipo === "error") {
        console.error("[Whisper Worker]", msg.mensaje);
        setProcesando(false);
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

  // ---- Cancelar grabación (descarta el audio) ----
  const cancelarEscucha = useCallback(() => {
    cancelarRef.current = true;
  }, []);

  // ---- Finalizar grabación PTT (procesa el audio grabado hasta ahora) ----
  const finalizarGrabacion = useCallback(() => {
    terminarRef.current?.("silencio");
  }, []);

  // ---- Grabar micrófono y transcribir ----
  const escuchar = useCallback((
    onProcesandoInicio?: () => void,
    modo: "vad" | "ptt" = "vad"
  ): Promise<string> => {
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
        terminarRef.current = null;

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
        setMicAbierto(false);
        setTiempoRestante(null);

        const duracionMinima = modo === "ptt" ? DURACION_MINIMA_PTT : DURACION_MINIMA;
        if (motivo === "cancelado" || muestrasAcumuladas.length === 0 || duracionMs < duracionMinima) {
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

        setProcesando(true);
        onProcesandoInicio?.();   // notifica al caller que Whisper empieza a procesar
        workerRef.current?.postMessage({ tipo: "transcribir", audio }, [audio.buffer]);
        // resolve() se llama desde onmessage cuando llega el resultado
      }

      // Guardar referencia para PTT
      terminarRef.current = terminar;

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

          setMicAbierto(true);

          // En PTT: empezar a grabar inmediatamente
          if (modo === "ptt") {
            grabandoVoz = true;
            setGrabando(true);
          } else {
            // VAD: countdown
            const inicioEscucha = Date.now();
            setTiempoRestante(Math.round(TIMEOUT_GRABACION / 1000));
            countdownInterval = setInterval(() => {
              const elapsed   = Date.now() - inicioEscucha;
              const remaining = Math.max(0, Math.round((TIMEOUT_GRABACION - elapsed) / 1000));
              setTiempoRestante(remaining);
            }, 500);
          }

          processorNode.onaudioprocess = (e) => {
            if (finalizado || cancelarRef.current) {
              if (!finalizado) terminar("cancelado");
              return;
            }

            const canal    = e.inputBuffer.getChannelData(0);
            const rms      = calcularRMS(canal);
            const msBloque = (BUFFER_SIZE / SAMPLE_RATE) * 1000;

            setNivelMic(Math.min(1, rms / (VAD_THRESHOLD * 4)));

            if (modo === "ptt") {
              // PTT: siempre graba, sin detección de silencio automática
              muestrasAcumuladas.push(new Float32Array(canal));
              duracionMs += msBloque;
            } else {
              // VAD: lógica de detección por umbral RMS
              if (rms >= VAD_THRESHOLD) {
                bloquesVoz++;
                if (bloquesVoz >= BLOQUES_CONFIRMAR) {
                  if (!grabandoVoz) {
                    grabandoVoz = true;
                    setGrabando(true);
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
            }
          };

          sourceNode.connect(processorNode);
          processorNode.connect(audioCtx.destination);

          timeoutHandle = setTimeout(() => terminar("timeout"), TIMEOUT_GRABACION);
        } catch (err) {
          console.error("[Whisper PTT] Error accediendo al micrófono:", err);
          terminarRef.current = null;
          setTranscribiendo(false);
          setNivelMic(0);
          setGrabando(false);
          setMicAbierto(false);
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
    micAbierto,
    procesando,
    tiempoRestante,
    escuchar,
    finalizarGrabacion,
    cancelarEscucha,
  };
}
