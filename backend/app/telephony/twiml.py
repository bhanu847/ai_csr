import uuid

from twilio.twiml.voice_response import Connect, Stream, VoiceResponse


def build_voice_stream_twiml(
    public_server_url: str, tenant_id: uuid.UUID, agent_id: uuid.UUID, call_id: uuid.UUID
) -> str:
    ws_url = public_server_url.replace("https://", "wss://").replace("http://", "ws://")
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"{ws_url}/media-stream")
    stream.parameter(name="tenant_id", value=str(tenant_id))
    stream.parameter(name="agent_id", value=str(agent_id))
    stream.parameter(name="call_id", value=str(call_id))
    connect.append(stream)
    response.append(connect)
    return str(response)
