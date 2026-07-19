import azure.cognitiveservices.speech as speechsdk

from app.config import settings


def synthesize_mulaw8k(text: str, voice: str) -> bytes:
    """Synthesize text to speech as raw 8kHz mu-law for Twilio Media Streams."""
    speech_config = speechsdk.SpeechConfig(
        subscription=settings.azure_speech_key, region=settings.azure_speech_region
    )
    speech_config.speech_synthesis_voice_name = voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Raw8Khz8BitMonoMULaw
    )
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return result.audio_data
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails(result)
        raise RuntimeError(f"TTS canceled: {details.reason} {details.error_details}")
    raise RuntimeError(f"TTS failed: {result.reason}")
