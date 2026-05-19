/// <reference types="vite/client" />

import type { InterviewApi } from "../electron/preload";

declare global {
  interface Window {
    interview?: InterviewApi;
    SpeechRecognition?: import("./services/liveSpeech").SpeechRecognitionConstructor;
    webkitSpeechRecognition?: import("./services/liveSpeech").SpeechRecognitionConstructor;
  }
}
