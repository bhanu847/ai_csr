import { Injectable, signal } from '@angular/core';

import { voiceCatalogEntry } from './voice-catalog';

const SAMPLE_TEXT = 'Hello, thanks for calling. How can I help you today?';

@Injectable({ providedIn: 'root' })
export class VoicePreviewService {
  readonly speakingVoiceId = signal<string | null>(null);
  readonly supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  preview(voiceId: string): void {
    if (!this.supported) return;
    window.speechSynthesis.cancel();

    const entry = voiceCatalogEntry(voiceId);
    const utterance = new SpeechSynthesisUtterance(SAMPLE_TEXT);
    utterance.lang = entry.locale;

    const match = window.speechSynthesis
      .getVoices()
      .find((v) => v.lang.toLowerCase().startsWith(entry.locale.toLowerCase()));
    if (match) {
      utterance.voice = match;
    }

    utterance.onend = () => this.speakingVoiceId.set(null);
    utterance.onerror = () => this.speakingVoiceId.set(null);

    this.speakingVoiceId.set(voiceId);
    window.speechSynthesis.speak(utterance);
  }

  stop(): void {
    if (this.supported) {
      window.speechSynthesis.cancel();
    }
    this.speakingVoiceId.set(null);
  }
}
