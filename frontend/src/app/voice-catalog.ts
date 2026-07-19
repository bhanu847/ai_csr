export interface VoiceCatalogEntry {
  id: string;
  label: string;
  locale: string;
  localeName: string;
  gender: 'Female' | 'Male';
}

const CATALOG: Record<string, VoiceCatalogEntry> = {
  'en-IN-NeerjaNeural': {
    id: 'en-IN-NeerjaNeural',
    label: 'Neerja',
    locale: 'en-IN',
    localeName: 'English (India)',
    gender: 'Female',
  },
  'hi-IN-SwaraNeural': {
    id: 'hi-IN-SwaraNeural',
    label: 'Swara',
    locale: 'hi-IN',
    localeName: 'Hindi (India)',
    gender: 'Female',
  },
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
};

export function voiceCatalogEntry(voiceId: string): VoiceCatalogEntry {
  const known = CATALOG[voiceId];
  if (known) return known;

  const parts = voiceId.split('-');
  const locale = parts.slice(0, 2).join('-') || 'en-US';
  return { id: voiceId, label: voiceId, locale, localeName: locale, gender: 'Female' };
}
