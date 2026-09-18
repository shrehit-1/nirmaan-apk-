/**
 * NIRMAAN - Audio & Speech Manager
 * Handles browser Web Speech recognition, microphone recording waveforms, and voice reading (TTS).
 */

export const AudioManager = {
  recognition: null,
  isRecording: false,
  synth: window.speechSynthesis || null,

  // --- Real microphone recording (MediaRecorder) ---
  // This captures the artisan's ACTUAL voice as an audio file so it can be
  // sent to the backend for genuine transcription (see api.js
  // transcribeAudioBlob / /api/voice/transcribe-audio). It intentionally
  // never invents or substitutes a canned recording.
  mediaRecorder: null,
  mediaStream: null,
  recordedChunks: [],
  isCapturingAudio: false,

  _pickSupportedMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
      "audio/mp4"
    ];
    for (const type of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return ""; // let the browser pick a default
  },

  async startCapturingAudio() {
    // Android production APKs use a native recorder. This avoids WebView
    // getUserMedia/MediaRecorder audio-source conflicts on some Android devices.
    if (window.NirmaanAndroidAudio) {
      const result = await new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          window.__nirmaanNativeMicPermission = null;
          resolve(value);
        };

        window.__nirmaanNativeMicPermission = (granted) => {
          if (!granted) {
            finish("permission_denied");
            return;
          }
          try {
            finish(window.NirmaanAndroidAudio.startRecording());
          } catch (e) {
            finish("error:" + (e.message || "Could not start audio source"));
          }
        };

        try {
          const response = window.NirmaanAndroidAudio.startRecording();
          if (response !== "permission_required") finish(response);
        } catch (e) {
          finish("error:" + (e.message || "Could not start audio source"));
        }
      });

      if (result === "started") {
        this.isCapturingAudio = true;
        this.mediaRecorder = null;
        this.mediaStream = null;
        return;
      }
      if (result === "permission_denied") {
        throw new Error("Microphone permission was denied.");
      }
      if (String(result).startsWith("error:")) {
        throw new Error(String(result).slice(6));
      }
      throw new Error("Could not start audio source");
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      throw new Error("Microphone recording is not supported in this browser.");
    }
    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = this._pickSupportedMimeType();
    this.mediaRecorder = mimeType
      ? new MediaRecorder(this.mediaStream, { mimeType })
      : new MediaRecorder(this.mediaStream);
    this.recordedChunks = [];

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.recordedChunks.push(event.data);
      }
    };

    this.mediaRecorder.start();
    this.isCapturingAudio = true;
  },
  /** Resolves with the recorded audio Blob (real voice, not simulated). */
  stopCapturingAudio() {
    if (window.NirmaanAndroidAudio) {
      return new Promise((resolve, reject) => {
        try {
          const result = window.NirmaanAndroidAudio.stopRecording();
          if (!String(result).startsWith("ok:")) {
            reject(new Error(String(result).replace(/^error:/, "") || "Recording failed."));
            return;
          }
          const base64 = String(result).slice(3);
          const binary = atob(base64);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          this.isCapturingAudio = false;
          resolve(new Blob([bytes], { type: "audio/mp4" }));
        } catch (e) {
          this.isCapturingAudio = false;
          reject(e);
        }
      });
    }

    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder || !this.isCapturingAudio) {
        reject(new Error("Not currently recording."));
        return;
      }
      this.mediaRecorder.onstop = () => {
        const mimeType = this.mediaRecorder.mimeType || "audio/webm";
        const blob = new Blob(this.recordedChunks, { type: mimeType });
        this.recordedChunks = [];
        this.isCapturingAudio = false;
        if (this.mediaStream) {
          this.mediaStream.getTracks().forEach(track => track.stop());
          this.mediaStream = null;
        }
        resolve(blob);
      };
      try {
        this.mediaRecorder.stop();
      } catch (e) {
        reject(e);
      }
    });
  },
  init() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.lang = "hi-IN";
    }
  },

  startListening(onResult, onEnd, lang = "hi-IN") {
    // On Android, recording is handled by the native bridge. Do not also start
    // Web Speech recognition because it can open a second microphone session and
    // cause MediaRecorder to fail with "Could not start audio source".
    if (window.NirmaanAndroidAudio) {
      this.isRecording = true;
      return;
    }

    if (!this.recognition) {
      this.init();
    }
    
    if (this.recognition) {
      this.recognition.lang = lang;
      this.isRecording = true;

      this.recognition.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        if (onResult) onResult(transcript);
      };

      this.recognition.onerror = (event) => {
        console.warn("Speech recognition notice:", event.error);
        this.isRecording = false;
        if (onEnd) onEnd();
      };

      this.recognition.onend = () => {
        this.isRecording = false;
        if (onEnd) onEnd();
      };

      try {
        this.recognition.start();
      } catch (e) {
        console.warn("Speech start exception:", e);
      }
    } else {
      console.log("Web Speech not natively supported in this browser, using simulation fallback.");
    }
  },

  stopListening() {
    if (this.recognition && this.isRecording) {
      try {
        this.recognition.stop();
      } catch (e) {}
      this.isRecording = false;
    }
  },

  speakText(text, lang = "hi-IN") {
    if (!this.synth) return;
    try {
      this.synth.cancel(); // Stop prior speech
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = 0.95;
      this.synth.speak(utterance);
    } catch (e) {
      console.warn("TTS error:", e);
    }
  }
};
