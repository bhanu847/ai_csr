export interface VoiceCatalogEntry {
  id: string;
  label: string;
  locale: string;
  localeName: string;
  gender: 'Female' | 'Male';
}

// Open-source Piper voices (https://github.com/OHF-Voice/piper1-gpl) — id
// must match a .onnx voice model downloaded into the backend's
// PIPER_VOICES_DIR (see backend/.env.example). No native Indian-accented
// English voice exists in Piper's open voice set; hi_IN-rohan-medium is
// the only Hindi option, and it's male despite standing in for the old
// "Swara" (female) slot.
const CATALOG: Record<string, VoiceCatalogEntry> = {
  'en_US-amy-medium': {
    id: 'en_US-amy-medium',
    label: 'Amy',
    locale: 'en-US',
    localeName: 'English (US)',
    gender: 'Female',
  },
  'en_US-ryan-medium': {
    id: 'en_US-ryan-medium',
    label: 'Ryan',
    locale: 'en-US',
    localeName: 'English (US)',
    gender: 'Male',
  },
  'en_GB-alan-medium': {
    id: 'en_GB-alan-medium',
    label: 'Alan',
    locale: 'en-GB',
    localeName: 'English (UK)',
    gender: 'Male',
  },
  'hi_IN-rohan-medium': {
    id: 'hi_IN-rohan-medium',
    label: 'Rohan',
    locale: 'hi-IN',
    localeName: 'Hindi (India)',
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
