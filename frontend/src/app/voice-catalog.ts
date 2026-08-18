export interface VoiceCatalogEntry {
  id: string;
  label: string;
  locale: string;
  localeName: string;
  gender: 'Female' | 'Male';
}

// Azure AI Speech neural voices (https://speech.microsoft.com/portal/voicegallery)
// — id must be a real Azure voice name; the backend passes it straight
// through to the Speech REST API (see backend/app/speech/tts.py).
const CATALOG: Record<string, VoiceCatalogEntry> = {
  'en-US-JennyNeural': {
    id: 'en-US-JennyNeural',
    label: 'Jenny',
    locale: 'en-US',
    localeName: 'English (US)',
    gender: 'Female',
  },
  'en-US-GuyNeural': {
    id: 'en-US-GuyNeural',
    label: 'Guy',
    locale: 'en-US',
    localeName: 'English (US)',
    gender: 'Male',
  },
  'en-GB-RyanNeural': {
    id: 'en-GB-RyanNeural',
    label: 'Ryan',
    locale: 'en-GB',
    localeName: 'English (UK)',
    gender: 'Male',
  },
  'hi-IN-SwaraNeural': {
    id: 'hi-IN-SwaraNeural',
    label: 'Swara',
    locale: 'hi-IN',
    localeName: 'Hindi (India)',
    gender: 'Female',
  },
};

export function voiceCatalogEntry(voiceId: string): VoiceCatalogEntry {
  const known = CATALOG[voiceId];
  if (known) return known;

  const parts = voiceId.split('-');
  const locale = parts.slice(0, 2).join('-') || 'en-US';
  return { id: voiceId, label: voiceId, locale, localeName: locale, gender: 'Female' };
}
