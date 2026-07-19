import azure.cognitiveservices.speech as speechsdk

from app.config import settings


def transcribe_pcm16(audio: bytes, sample_rate: int = 16000) -> str:
    """Recognize a single utterance from raw 16-bit mono PCM audio."""
    speech_config = speechsdk.SpeechConfig(
        subscription=settings.azure_speech_key, region=settings.azure_speech_region
    )
    speech_config.speech_recognition_language = settings.stt_language
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=sample_rate, bits_per_sample=16, channels=1
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    push_stream.write(audio)
    push_stream.close()

    result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    if result.reason == speechsdk.ResultReason.NoMatch:
        return ""
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.CancellationDetails(result)
        raise RuntimeError(f"STT canceled: {details.reason} {details.error_details}")
    return ""
