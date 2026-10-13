import asyncio
import os

from dotenv import load_dotenv
from livekit.plugins import elevenlabs

load_dotenv()


async def main():
    api_key = (
        os.getenv("ELEVEN_API_KEY")
        or os.getenv("ELEVENLABS_API_KEY")
    )

    if not api_key:
        raise RuntimeError("ELEVEN_API_KEY / ELEVENLABS_API_KEY is missing")

    from livekit.agents import utils
    
    async with utils.http_context.open():
        tts = elevenlabs.TTS(
            api_key=api_key,
            voice_id="hpp4J3VqNfWAUOO0d1Us",
            model="eleven_turbo_v2_5",
        )

        print("TTS created successfully")

        stream = tts.synthesize(
            "Hello. This is a test of the AI interviewer's voice."
        )

        frame_count = 0

        async for audio in stream:
            frame_count += 1
            print(
                f"Audio frame {frame_count}: "
                f"{audio.frame.sample_rate} Hz, "
                f"{audio.frame.num_channels} channels, "
                f"{len(audio.frame.data)} bytes"
            )

        print(f"\nTOTAL AUDIO FRAMES: {frame_count}")

        if frame_count == 0:
            raise RuntimeError("ElevenLabs returned ZERO audio frames")

        print("SUCCESS: ElevenLabs TTS is producing audio.")


if __name__ == "__main__":
    asyncio.run(main())