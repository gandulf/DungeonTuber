import { api } from './api';
import { t, locale } from './i18n.svelte';
import { errorToast, toast } from './stores/ui.svelte';

/** A pause of this length ends a phrase: it is transcribed while the next one is already being recorded. */
const PAUSE_MS = 1000;
/** Dictation stops by itself after this long without speech. */
const IDLE_STOP_MS = 6000;
/** Less speech than this in a phrase is noise (a click, a cough) and is not transcribed. */
const MIN_VOICED_MS = 300;
/** A phrase that goes on this long is cut and transcribed anyway. */
const MAX_PHRASE_MS = 30000;
/** The recording ends after this long, whatever is said. */
const MAX_TOTAL_MS = 5 * 60 * 1000;
/** Silence before a phrase that is kept in the recording, so that its first syllable is not cut off. */
const PRE_ROLL_MS = 1500;
const TICK_MS = 50;
const MIN_LEVEL = 0.02;
// the formats the browsers record: Chromium and Firefox webm/ogg, Safari mp4
const FORMATS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

export const dictationSupported = () => typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;

export type DictationState = 'idle' | 'recording';

/** The bars of the spectrum ball (SpectrumOrb.svelte): mirrored, so there are twice as many bars as bands. */
const BANDS = 12;
export const ORB_BARS = BANDS * 2;

/** What the microphone hears right now while dictation runs: the player shows it as a spectrum ball. `level` and the `bars` are 0 to 1. */
export const listening = $state({ active: false, level: 0, bars: Array<number>(ORB_BARS).fill(0) });
let running: { stop: (discard?: boolean) => void } | null = null;

/** Ends the running dictation (its last phrase is still transcribed). */
export const stopDictation = () => running?.stop();

/** Dictation: listens to the microphone until `toggle` is called again or nothing is said for a while. Every phrase (ended by a pause) is
 *  transcribed by the server right away and given to `ontext`, in the order it was spoken. `pending` counts the phrases being transcribed. */
export function createDictation(ontext: (text: string) => void) {
  const dictation = $state({ state: 'idle' as DictationState, pending: 0 });
  let session: { stop: (discard?: boolean) => void } | null = null;
  let queue: Promise<void> = Promise.resolve();

  /** Transcribes in the order of speaking: a short phrase must not overtake a long one. */
  function transcribe(audio: Blob) {
    dictation.pending++;
    queue = queue.then(async () => {
      try {
        const { text } = await api.transcribe(audio, locale());
        if (text.trim()) ontext(text.trim());
        else toast(t('Nothing was understood'));
      } catch (e) {
        errorToast(e);
      } finally {
        dictation.pending--;
      }
    });
  }

  async function start() {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      toast(t('The microphone is not available: {0}', e instanceof Error ? e.message : String(e)), 'error');
      return;
    }
    const mimeType = FORMATS.find((format) => MediaRecorder.isTypeSupported(format));
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const spectrum = new Uint8Array(analyser.frequencyBinCount);

    let recorder: MediaRecorder;
    let chunks: Blob[] = [];
    let voicedMs = 0; // speech in the phrase being recorded
    let phraseStart = Date.now();
    const begun = phraseStart;
    let lastVoice = 0; // when the last speech was heard (0: none in this phrase)
    let lastActivity = begun; // the last speech of the whole recording, or its start
    let floor = 0; // the level of the room: speech has to rise clearly above it
    let ended = false;
    let discard = false;

    /** Starts the recorder of the next phrase; each phrase is a file of its own, so the server can read it alone. */
    function record() {
      const own: Blob[] = []; // the handler keeps its own list: the data of a stopped recorder arrives after the next one has started
      chunks = own;
      voicedMs = 0;
      lastVoice = 0;
      phraseStart = Date.now();
      const next = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      next.ondataavailable = (event) => event.data.size && own.push(event.data);
      next.start();
      recorder = next;
    }

    /** Ends the phrase: it is transcribed when it holds speech. `more` starts the next phrase. */
    function cut(more: boolean) {
      const finished = recorder;
      const kept = chunks;
      const speech = voicedMs >= MIN_VOICED_MS && !discard;
      finished.onstop = () => {
        if (speech && kept.length) transcribe(new Blob(kept, { type: finished.mimeType }));
      };
      if (more) record();
      if (finished.state !== 'inactive') finished.stop();
    }

    const timer = setInterval(() => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2;
      const level = Math.sqrt(sum / samples.length);
      analyser.getByteFrequencyData(spectrum);
      const width = Math.floor(96 / BANDS); // the bins up to about 4.5 kHz hold the speech
      listening.level = listening.level * 0.6 + Math.min(1, level * 6) * 0.4;
      listening.bars = Array.from({ length: ORB_BARS }, (_, i) => {
        const band = i < BANDS ? i : ORB_BARS - 1 - i;
        let total = 0;
        for (let bin = 1 + band * width; bin < 1 + (band + 1) * width; bin++) total += spectrum[bin];
        return listening.bars[i] * 0.5 + Math.min(1, (total / width / 255) * 1.8) * 0.5;
      });
      const now = Date.now();
      const voice = level > Math.max(MIN_LEVEL, floor * 2.5);
      if (voice) {
        voicedMs += TICK_MS;
        lastVoice = lastActivity = now;
      } else {
        floor = floor * 0.95 + level * 0.05;
      }
      if (now - lastActivity > IDLE_STOP_MS || now - begun > MAX_TOTAL_MS) {
        controller.stop();
      } else if (lastVoice && now - lastVoice > PAUSE_MS) {
        cut(true); // a pause after speech: the phrase is done
      } else if (!lastVoice && now - phraseStart > PRE_ROLL_MS) {
        cut(true); // nothing said yet: start over, so that the silence does not pile up
      } else if (now - phraseStart > MAX_PHRASE_MS) {
        cut(true);
      }
    }, TICK_MS);

    const controller = {
      stop(throwAway = false) {
        if (ended) return;
        ended = true;
        discard = throwAway;
        clearInterval(timer);
        cut(false);
        stream.getTracks().forEach((track) => track.stop());
        void context.close();
        session = null;
        running = null;
        dictation.state = 'idle';
        listening.active = false;
        listening.level = 0;
        listening.bars = Array<number>(ORB_BARS).fill(0);
      },
    };
    session = controller;
    running = controller;
    listening.active = true;
    record();
    dictation.state = 'recording';
  }

  function toggle() {
    if (session) session.stop();
    else if (dictation.state === 'idle') void start();
  }

  /** Throws the running recording away (the component is gone). */
  function cancel() {
    session?.stop(true);
  }

  return { dictation, toggle, cancel };
}
