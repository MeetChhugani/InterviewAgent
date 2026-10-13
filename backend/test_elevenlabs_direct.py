import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVENLABS_API_KEY")

if not api_key:
    print("No API key found.")
    exit(1)

print("--- Testing GET /v1/user ---")
headers = {
    "xi-api-key": api_key
}
resp_user = requests.get("https://api.elevenlabs.io/v1/user", headers=headers)
print(f"Status: {resp_user.status_code}")
if resp_user.status_code != 200:
    print(f"Body: {resp_user.text}")
    print("Relevant Headers:")
    for k, v in resp_user.headers.items():
        if k.lower() in ["www-authenticate", "x-request-id", "date"]:
            print(f"  {k}: {v}")

print("\n--- Testing POST /v1/text-to-speech/hpp4J3VqNfWAUOO0d1Us ---")
post_headers = {
    "xi-api-key": api_key,
    "Content-Type": "application/json",
    "Accept": "audio/mpeg"
}
payload = {
    "text": "Hello, this is a test of the interview assistant.",
    "model_id": "eleven_turbo_v2_5"
}
resp_tts = requests.post("https://api.elevenlabs.io/v1/text-to-speech/hpp4J3VqNfWAUOO0d1Us", headers=post_headers, json=payload)

print(f"Status: {resp_tts.status_code}")
if resp_tts.status_code == 200:
    print(f"Received audio: {len(resp_tts.content)} bytes")
else:
    print(f"Body: {resp_tts.text}")
    print("Relevant Headers:")
    for k, v in resp_tts.headers.items():
        if k.lower() in ["www-authenticate", "x-request-id", "date"]:
            print(f"  {k}: {v}")
