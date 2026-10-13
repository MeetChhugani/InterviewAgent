import asyncio
import os
from dotenv import load_dotenv

from livekit.agents import utils
from livekit.agents import inference

load_dotenv()

async def main():
    if not os.getenv("LIVEKIT_URL") or not os.getenv("LIVEKIT_API_KEY") or not os.getenv("LIVEKIT_API_SECRET"):
        raise RuntimeError("LiveKit credentials (URL, API_KEY, API_SECRET) are missing")

    async with utils.http_context.open():
        tts = inference.TTS(
            model="deepgram/aura-2",
            voice="athena",
            language="en"
        )

        print("LiveKit Inference TTS created successfully")

        stream = tts.synthesize("Hello. This is a test of the AI interviewer's new voice through LiveKit Inference.")
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
            raise RuntimeError("LiveKit Inference TTS returned ZERO audio frames")

        print("SUCCESS: LiveKit Inference TTS is producing audio.")

if __name__ == "__main__":
    asyncio.run(main())
