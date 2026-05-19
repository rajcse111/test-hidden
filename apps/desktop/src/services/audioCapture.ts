import { interviewSocket } from "./interviewSocket";

export class AudioCapture {
  private context: AudioContext | null = null;
  private processor: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private stream: MediaStream | null = null;

  async start(sessionId: string, options: { streamToBackend?: boolean } = {}): Promise<void> {
    const streamToBackend = options.streamToBackend ?? true;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    if (!streamToBackend) return;
    this.context = new AudioContext();
    await this.context.audioWorklet.addModule("/audio-worklet.js");
    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = new AudioWorkletNode(this.context, "interview-audio-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
    });
    this.processor.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      interviewSocket.send({
        type: "audio.chunk",
        sessionId,
        payloadBase64: this.toBase64(event.data),
        sampleRate: 16000,
        channels: 1,
      });
    };
    this.source.connect(this.processor);
  }

  stop(): void {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close();
    this.processor = null;
    this.source = null;
    this.stream = null;
    this.context = null;
  }

  private toBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    const chunks: string[] = [];
    for (let index = 0; index < bytes.length; index += chunkSize) {
      chunks.push(String.fromCharCode(...bytes.subarray(index, index + chunkSize)));
    }
    const binary = chunks.join("");
    return window.btoa(binary);
  }
}

export const audioCapture = new AudioCapture();
