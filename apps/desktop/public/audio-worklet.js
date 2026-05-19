class InterviewAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.chunkSize = Math.floor(16000 * 1.5);
    this.pending = [];
    this.pendingLength = 0;
    this.sourceRate = sampleRate;
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || input.length === 0) return true;

    const resampled = this.resample(input);
    this.pending.push(resampled);
    this.pendingLength += resampled.length;

    while (this.pendingLength >= this.chunkSize) {
      const chunk = new Float32Array(this.chunkSize);
      let offset = 0;
      while (offset < this.chunkSize && this.pending.length > 0) {
        const head = this.pending[0];
        const remaining = this.chunkSize - offset;
        if (head.length <= remaining) {
          chunk.set(head, offset);
          offset += head.length;
          this.pending.shift();
          this.pendingLength -= head.length;
        } else {
          chunk.set(head.subarray(0, remaining), offset);
          this.pending[0] = head.subarray(remaining);
          this.pendingLength -= remaining;
          offset += remaining;
        }
      }
      const pcm = new Int16Array(chunk.length);
      for (let index = 0; index < chunk.length; index += 1) {
        const sample = Math.max(-1, Math.min(1, chunk[index]));
        pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }

    return true;
  }

  resample(input) {
    if (this.sourceRate === this.targetSampleRate) return new Float32Array(input);
    const ratio = this.sourceRate / this.targetSampleRate;
    const outputLength = Math.floor(input.length / ratio);
    const output = new Float32Array(outputLength);
    for (let index = 0; index < outputLength; index += 1) {
      const srcPos = index * ratio;
      const low = Math.floor(srcPos);
      const high = Math.min(low + 1, input.length - 1);
      const frac = srcPos - low;
      output[index] = input[low] * (1 - frac) + input[high] * frac;
    }
    return output;
  }
}

registerProcessor("interview-audio-processor", InterviewAudioProcessor);
