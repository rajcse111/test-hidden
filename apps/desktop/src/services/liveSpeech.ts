export type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0: { transcript: string };
};

export type SpeechRecognitionEventLike = Event & {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

export type SpeechRecognitionLike = EventTarget & {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
};

export type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

export class LiveSpeech {
  private recognition: SpeechRecognitionLike | null = null;
  private shouldRun = false;

  isSupported(): boolean {
    return this.getConstructor() !== null;
  }

  start(onInterim: (text: string) => void, onFinal: (text: string) => void): void {
    const Constructor = this.getConstructor();
    if (!Constructor) return;
    this.stop();
    this.shouldRun = true;
    this.recognition = new Constructor();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = "en-US";
    this.recognition.onresult = (event) => {
      let interim = "";
      let finalText = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (!result) continue;
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      if (interim.trim()) onInterim(interim.trim());
      if (finalText.trim()) {
        onFinal(finalText.trim());
        onInterim("");
      }
    };
    this.recognition.onerror = (event) => {
      onInterim("");
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        this.shouldRun = false;
      }
    };
    this.recognition.onend = () => {
      if (this.shouldRun) window.setTimeout(() => this.recognition?.start(), 250);
    };
    this.recognition.start();
  }

  stop(): void {
    this.shouldRun = false;
    this.recognition?.abort();
    this.recognition = null;
  }

  private getConstructor(): SpeechRecognitionConstructor | null {
    const candidate = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    return candidate ?? null;
  }
}

export const liveSpeech = new LiveSpeech();
