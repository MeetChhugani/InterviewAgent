import asyncio
import contextlib
import os
import json
import httpx
import re

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, llm, AgentStateChangedEvent
from livekit.plugins import silero, groq
try:
    from livekit.plugins import gnani
    _gnani_import_error = None
except ImportError as exc:
    gnani = None
    _gnani_import_error = str(exc)
try:
    from livekit.plugins import elevenlabs
    _elevenlabs_import_error = None
except ImportError as exc:
    elevenlabs = None
    _elevenlabs_import_error = str(exc)
from livekit.agents import inference

from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger("interviewer")
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "interviewer").strip() or "interviewer"

# A provider-side TTS stream can occasionally remain open without returning an
# error. Do not let that leave a candidate session permanently in AI_SPEAKING.
TTS_SPEECH_TIMEOUT_SECONDS = float(os.getenv("TTS_SPEECH_TIMEOUT_SECONDS", "40"))
REPORT_SAVE_ATTEMPTS = max(1, int(os.getenv("REPORT_SAVE_ATTEMPTS", "4")))


def parse_json_object(content: str) -> dict:
    """Parse an object even when a model wraps JSON in a Markdown fence."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("The model response did not contain a JSON object")
    value, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(value, dict):
        raise ValueError("The model response JSON was not an object")
    return value


def safe_score(value) -> int:
    """Keep model-provided scores in the report's expected 0–100 range."""
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return 0


def is_substantive_answer(answer: str) -> bool:
    """Only a genuinely empty STT result is unusable for evaluation.

    Do not perform substring-based refusal detection here: a valid answer can
    contain words such as "passages", which previously matched "pass" and
    bypassed the evaluator despite being visible in the candidate transcript.
    The evaluator receives every non-empty final transcript and determines its
    relevance and quality.
    """
    return bool((answer or "").strip())


def missing_answer_evaluation() -> dict:
    return {
        "score": 0,
        "correctness": "No substantive answer provided",
        "relevance": 0,
        "completeness": 0,
        "technical_depth": 0,
        "feedback": "No substantive answer was provided for this question.",
        "strengths": [],
        "weaknesses": ["Provide a complete, topic-relevant answer instead of skipping the question."],
    }


async def fetch_session(session_id: str):
    logger.info("FETCHING SESSION: %s", session_id)
    api_base_url = os.getenv("INTERVIEW_API_URL", "http://localhost:8000").rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{api_base_url}/api/interview/session/{session_id}")
    logger.info("SESSION RESPONSE STATUS: %s", r.status_code)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(
            f"Session {session_id} not found on FastAPI (HTTP {r.status_code}): {data}"
        )
    if "setup" not in data:
        raise RuntimeError(
            f"Session response missing 'setup' key. Got keys: {list(data.keys())}"
        )
    return data


async def complete_session(session_id: str, report: dict):
    # Locally the API and worker share localhost. In Railway they are separate
    # services, so INTERVIEW_API_URL must point to the deployed FastAPI API.
    api_base_url = os.getenv("INTERVIEW_API_URL", "http://localhost:8000").rstrip("/")
    if api_base_url in {"http://localhost:8000", "http://127.0.0.1:8000"}:
        raise RuntimeError(
            "INTERVIEW_API_URL is not configured for the deployed worker. "
            "Set it to the public URL of the FastAPI API service."
        )

    endpoint = f"{api_base_url}/api/interview/session/{session_id}/complete"
    logger.info("[REPORT] Saving report to API at %s", api_base_url)
    last_error = None
    # A newly-woken public API can briefly reject the worker connection. Retry
    # transient transport and server errors before declaring the report failed.
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        for attempt in range(1, REPORT_SAVE_ATTEMPTS + 1):
            try:
                response = await client.post(endpoint, json=report)
                response.raise_for_status()
                logger.info("[REPORT] Saved on attempt %d/%d", attempt, REPORT_SAVE_ATTEMPTS)
                return
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                last_error = error
                retryable_status = (
                    not isinstance(error, httpx.HTTPStatusError)
                    or error.response.status_code >= 500
                )
                if not retryable_status or attempt == REPORT_SAVE_ATTEMPTS:
                    break
                delay_seconds = attempt * 2
                logger.warning(
                    "[REPORT] Save attempt %d/%d failed (%s); retrying in %ss",
                    attempt,
                    REPORT_SAVE_ATTEMPTS,
                    error,
                    delay_seconds,
                )
                await asyncio.sleep(delay_seconds)

    raise RuntimeError(
        f"Could not save the report to {api_base_url} after "
        f"{REPORT_SAVE_ATTEMPTS} attempt(s): {last_error}"
    ) from last_error


server = AgentServer()

# Pre-load the VAD model once at module/worker startup.
# silero.VAD.load() is synchronous and loads a PyTorch/ONNX model.
# Calling it inside the async entrypoint (after ctx.connect()) blocks the
# event loop long enough for the LiveKit 10-second RoomIO watchdog to fire
# and the FFI layer to panic with ReadyForRoomEventRequest timeout.
logger.info("[STARTUP] Pre-loading Silero VAD model...")
_preloaded_vad = silero.VAD.load()
logger.info("[STARTUP] Silero VAD model ready")


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext):
    logger.info("[ROOM] ENTRYPOINT START")
    logger.info("[ROOM] JOB ROOM = %s", ctx.room.name)

    logger.info("[ROOM] CALLING CTX.CONNECT")
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)
    logger.info("[ROOM] CTX.CONNECT RETURNED")
    logger.info("[ROOM] ROOM CONNECTED participants=%d", len(ctx.room.remote_participants))

    session_id = ctx.room.name

    # ── Load setup ────────────────────────────────────────────────────────────
    setup = None
    raw_metadata = getattr(ctx.job, "metadata", None)
    if raw_metadata:
        try:
            setup = json.loads(raw_metadata)
            logger.info("SETUP LOADED FROM DISPATCH METADATA: %s", setup)
        except Exception as e:
            logger.warning("Failed to parse dispatch metadata: %s", e)

    if not setup:
        logger.info("No dispatch metadata - falling back to HTTP fetch")
        try:
            session_data = await fetch_session(session_id)
            setup = session_data["setup"]
            logger.info("SETUP LOADED FROM API FALLBACK: %s", setup)
        except Exception as e:
            logger.error(f"Could not fetch session {session_id}: {e}")
            return

    # ── State variables ───────────────────────────────────────────────────────
    #
    # interview_phase is the single source of truth for the state machine.
    #
    # Legal transitions:
    #   "INIT"
    #     └─► generate_interview_question("initial") ─► "GENERATING_QUESTION"
    #           └─► session.say()                   ─► "AI_SPEAKING"
    #                 └─► say() resolves             ─► "WAITING_FOR_ANSWER"
    #                       └─► STOP pressed / STT  ─► "EVALUATING_ANSWER"
    #                             ├─► current_q < 5 ─► "GENERATING_QUESTION" (loop)
    #                             └─► current_q == 5─► "WAITING_FOR_COMPLETION"
    #                                   └─► button   ─► "GENERATING_REPORT"
    #                                         └─►      "COMPLETE"
    # This is supplied by the setup screen and validated by the API.
    MAX_INTERVIEW_QUESTIONS = setup.get("num_questions", 5)
    question_count          = MAX_INTERVIEW_QUESTIONS
    current_q               = 0
    current_question_text   = ""
    current_question_language = "english"
    interview_results       = []

    # interview_phase — only generate_interview_question and handle_user_speech write this
    interview_phase = "INIT"

    # is_processing_turn — owned exclusively by handle_user_speech
    # True while handle_user_speech is executing; prevents duplicate STOP events
    is_processing_turn = False

    # report_generation_started — prevents do_complete_interview running twice
    report_generation_started = False

    # The browser explicitly acknowledges that its LiveKit data listener is
    # installed before Question 1 is published.  This avoids losing the first
    # question when the candidate joins while the worker is starting.
    candidate_ready_for_question = False

    # ── Interview config ──────────────────────────────────────────────────────
    role        = setup.get("role",       "Unknown Role")
    domain      = setup.get("domain",     "Unknown Domain")
    difficulty  = setup.get("difficulty", "Unknown Difficulty")
    topics_list = setup.get("topics", [])
    topics_str  = ", ".join(topics_list)
    # Llama 3.1 8B is no longer available to this Groq account. Keep a
    # supported default so a missing environment variable cannot leave the
    # interview frozen before its first question.
    groq_model  = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-20b")
    # Interviews are intentionally English-only. Keeping this in code (rather
    # than relying only on an environment variable) prevents an old Railway
    # variable from unexpectedly returning Hindi or Hinglish questions.
    question_languages = ["english"] * MAX_INTERVIEW_QUESTIONS

    logger.info(
        "[INTERVIEW CONFIG] role=%s domain=%s difficulty=%s topics=%s language=english",
        role, domain, difficulty, topics_list,
    )

    async def request_json(prompt: str, source: str) -> dict:
        """Use the configured LiveKit Groq plugin for JSON-only LLM work.

        Keeping all Groq calls on this client avoids requiring a second,
        separately-installed ``groq`` SDK just for scoring and reports.
        """
        logger.info("[LLM CALL] source=%s", source)
        chat_ctx = llm.ChatContext()
        chat_ctx.add_message(
            role="system",
            content="You are an expert interviewer and assessor across industries and professions. Adapt your evaluation to the role and output ONLY valid JSON matching the requested schema.",
        )
        chat_ctx.add_message(role="user", content=prompt)
        stream = groq.LLM(model=groq_model).chat(chat_ctx=chat_ctx)
        parts = []
        async with stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.content:
                    parts.append(chunk.delta.content)
        return parse_json_object("".join(parts))

    # ── Data-channel helpers ──────────────────────────────────────────────────
    async def publish(msg: dict):
        logger.info("[DATA OUT] %s", msg)
        data = json.dumps(msg).encode("utf-8")
        if ctx.room and ctx.room.local_participant:
            await ctx.room.local_participant.publish_data(data, reliable=True)

    async def broadcast_state(state: str, q_num: int = None):
        msg = {"type": "interview_state", "state": state}
        if state == "READY_TO_ANSWER" and q_num is not None:
            msg = {
                "type":            "question_state",
                "state":           state,
                "question_number": q_num,
                "question_count":  question_count,
            }
        logger.info("STATE: %s", state)
        await publish(msg)

    async def send_question_started():
        await publish({
            "type":            "question_started",
            "question_number": current_q,
            "question_count":  question_count,
        })

    # ── Question generation ───────────────────────────────────────────────────
    #
    # ONLY TWO LEGITIMATE CALLERS:
    #   1. entrypoint   → generate_interview_question("initial")
    #   2. handle_user_speech (after evaluation) → generate_interview_question("after_answer")
    #
    async def generate_interview_question(source: str):
        nonlocal current_q, current_question_text, current_question_language, interview_phase

        # ── Hard guards: refuse if state machine is wrong ─────────────────────
        if interview_phase not in ("INIT", "GENERATING_QUESTION"):
            logger.warning(
                "[FLOW] QUESTION GENERATION BLOCKED reason=wrong_phase "
                "phase=%s source=%s current_q=%s evaluated=%d",
                interview_phase, source, current_q, len(interview_results),
            )
            return None

        if current_q >= MAX_INTERVIEW_QUESTIONS:
            logger.info(
                "[FLOW] QUESTION LIMIT REACHED - NO NEW QUESTION current_q=%s max=%s",
                current_q, MAX_INTERVIEW_QUESTIONS,
            )
            return None

        # Answers must be caught up: before Q(N) we need N-1 evaluated answers
        if current_q > 0 and len(interview_results) < current_q:
            logger.warning(
                "[FLOW] QUESTION GENERATION BLOCKED reason=answer_not_evaluated "
                "current_q=%s evaluated=%d",
                current_q, len(interview_results),
            )
            return None

        # ── Increment counter and generate ────────────────────────────────────
        interview_phase = "GENERATING_QUESTION"
        current_q += 1

        logger.info(
            "[FLOW] GENERATING QUESTION current_q=%s evaluated_answers=%d "
            "phase=%s source=%s",
            current_q, len(interview_results), interview_phase, source,
        )

        try:
            await send_question_started()

            question_language = question_languages[current_q - 1]
            current_question_language = question_language
            language_instruction = {
                "english":  "Ask in clear professional English only.",
                "hindi":    "Ask in pure Hindi written in Devanagari script only. Keep unavoidable technical terms in English.",
                "hinglish": "Ask in natural Hinglish written in Roman Hindi and English. Keep technical terms in English.",
            }[question_language]
            logger.info("[QUESTION LANGUAGE] question_number=%s language=%s", current_q, question_language)

            prompt = (
                f"You are an experienced interviewer and subject-matter expert for the candidate's specific role.\n"
                f"ROLE: {role}\n"
                f"DOMAIN: {domain}\n"
                f"DIFFICULTY: {difficulty}\n"
                f"FOCUS AREAS: {topics_str if topics_str else 'None specified; infer the most important role-specific competencies from the role and domain.'}\n"
                f"LANGUAGE: {language_instruction}\n\n"
                "Output EXACTLY ONE concise, natural-sounding interview question as plain text.\n"
                "Rules:\n"
                "- Tailor the question to the stated role and domain; never assume the candidate works in software or technology.\n"
                "- Use practical, scenario-based, behavioral, domain knowledge, or technical questions as appropriate for the role.\n"
                "- If focus areas are provided, prioritize them; otherwise infer relevant competencies from the role.\n"
                "- One question only, nothing else.\n"
                "- Keep it below 35 words so it is comfortable to hear and answer aloud.\n"
                "- No bullets, numbers, or labels.\n"
                "- No notes, explanations, or meta-commentary.\n"
                "- End with exactly one question mark.\n"
            )

            llm_client = groq.LLM(model=groq_model)

            async def ask_llm() -> str:
                logger.info("[LLM CALL] source=INTERVIEW_QUESTION")
                ctx_llm = llm.ChatContext()
                ctx_llm.add_message(role="system", content=prompt)
                stream = llm_client.chat(chat_ctx=ctx_llm)
                parts = []
                logger.info("[LLM] STREAM START")
                async with stream:
                    async for chunk in stream:
                        if chunk.delta and chunk.delta.content:
                            parts.append(chunk.delta.content)
                logger.info("[LLM] STREAM COMPLETE")
                return "".join(parts).strip()

            def is_valid(q: str) -> bool:
                if not q:
                    return False
                if not q.endswith("?"):
                    return False
                if "\n" in q:
                    return False
                if q.count("?") > 1:
                    return False
                bad = ("1.", "2.", "3.", "- ", "Note:", "(Note", "Question:",
                       "candidate has not", "previous question", "already asked")
                if any(b in q for b in bad):
                    return False
                return True

            question_text = await ask_llm()
            logger.info("[LLM] QUESTION TEXT READY: %s", question_text)

            if not is_valid(question_text):
                logger.warning("[VALIDATION FAILED] Retrying. Got: %r", question_text)
                question_text = await ask_llm()
                logger.info("[LLM] RETRY TEXT READY: %s", question_text)
                if not is_valid(question_text):
                    logger.warning("[VALIDATION FAILED TWICE] Using fallback.")
                    fallback_topic = topics_list[0] if topics_list else f"a core responsibility of a {role}"
                    question_text = (
                        f"क्या आप {fallback_topic} से जुड़ी किसी मुख्य जिम्मेदारी को निभाने का अपना तरीका समझा सकते हैं?"
                        if question_language == "hindi"
                        else f"Aap {fallback_topic} se judi kisi main responsibility ko kaise sambhalenge?"
                        if question_language == "hinglish"
                        else f"How would you approach a core responsibility of {role}?"
                    )

            current_question_text = question_text

            # ── Deliver scripted question ──────────────────────────────────────
            # Browser speech is a safety fallback only. The provider voice is
            # substantially more natural and is streamed through the LiveKit
            # room, so it sounds consistent on every browser/device.
            provider_speech_played = await deliver_question_audio(question_text)
            interview_phase = "WAITING_FOR_ANSWER"
            await publish({
                "type":           "question_ready",
                "question":       question_text,
                "language":       question_language,
                "speak_in_browser": not provider_speech_played,
                "question_number": current_q,
                "question_count": question_count,
            })
            logger.info(
                "[FLOW] SETTING WAITING_FOR_ANSWER question_number=%s phase=%s",
                current_q, interview_phase,
            )
            await publish({
                "type":           "waiting_for_answer",
                "question_number": current_q,
                "question_count": question_count,
            })

            return question_text

        except Exception:
            logger.exception("[QUESTION GENERATION FAILED] Full traceback:")
            # Roll back so this slot can potentially be retried
            current_q -= 1
            interview_phase = "INIT" if current_q == 0 else "WAITING_FOR_ANSWER"
            raise

    # ── Agent / Session setup ─────────────────────────────────────────────────
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Configure it in backend/.env")

    logger.info(f"ENV CHECK - LIVEKIT_URL: {'OK' if os.getenv('LIVEKIT_URL') else 'MISSING'}")
    logger.info(f"ENV CHECK - LIVEKIT_API_KEY: {'OK' if os.getenv('LIVEKIT_API_KEY') else 'MISSING'}")
    logger.info(f"ENV CHECK - LIVEKIT_API_SECRET: {'OK' if os.getenv('LIVEKIT_API_SECRET') else 'MISSING'}")
    logger.info(f"ENV CHECK - GROQ_API_KEY: {'OK' if groq_api_key else 'MISSING'}")

    system_prompt = (
        f"You are an experienced interviewer conducting a one-on-one interview for the candidate's specific role.\n"
        f"ROLE: {role}\nDOMAIN: {domain}\nDIFFICULTY: {difficulty}\n"
        f"FOCUS TOPICS: {topics_str}\n\n"
        "Ask exactly one focused role-specific question per turn, using practical, scenario-based, behavioral, domain-specific, or technical questions as appropriate. "
        "Never list multiple questions. Never evaluate or comment on answers. "
        "Understand candidate answers in English, Hindi, and Hinglish."
    )

    interviewer_agent = Agent(instructions=system_prompt)

    use_gnani_stt = bool(os.getenv("GNANI_API_KEY")) and gnani is not None
    elevenlabs_api_key = os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
    tts_provider = os.getenv("INTERVIEW_TTS_PROVIDER", "inference").strip().lower()

    # Gnani STT is retained for Indian languages and Hinglish. LiveKit
    # Inference is the reliable default spoken-voice path for the public demo.
    # Gnani and ElevenLabs remain explicit opt-in providers.
    if use_gnani_stt:
        session_stt = gnani.STT(language="en-IN", preferred_language="hi-IN")
    else:
        if os.getenv("GNANI_API_KEY") and gnani is None:
            logger.error(
                "[VOICE] GNANI_API_KEY is configured, but the Gnani plugin could not load: %s.",
                _gnani_import_error or "unknown import error",
            )
        logger.warning("[VOICE] Gnani STT is not configured; using Groq STT")
        session_stt = groq.STT()

    if tts_provider == "elevenlabs" and elevenlabs_api_key and elevenlabs is not None:
        eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "hpp4J3VqNfWAUOO0d1Us")
        eleven_model    = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_turbo_v2_5")
        logger.info(
            "[VOICE] Using ElevenLabs TTS (voice_id=%s, model=%s); Gnani STT=%s",
            eleven_voice_id, eleven_model,
            "enabled" if use_gnani_stt else "disabled",
        )
        session_tts = elevenlabs.TTS(
            api_key=elevenlabs_api_key,
            voice_id=eleven_voice_id,
            model=eleven_model,
        )
    elif tts_provider == "gnani" and use_gnani_stt:
        # Use a natural Indian-English interviewer voice by default. The
        # interview questions are English-only, so use the explicit Indian
        # English locale rather than automatic language detection.
        gnani_voice = os.getenv("GNANI_TTS_VOICE", "Kaveri")
        gnani_language = os.getenv("GNANI_TTS_LANGUAGE", "en-IN")
        logger.info(
            "[VOICE] Using Gnani Indian TTS (model=timbre-v2.5, voice=%s, language=%s)",
            gnani_voice,
            gnani_language,
        )
        session_tts = gnani.TTS(
            model="timbre-v2.5",
            voice=gnani_voice,
            language=gnani_language,
            sample_rate=16000,
            # The provider's REST endpoint is used below through LiveKit's
            # StreamAdapter. Gnani's realtime WebSocket stream can remain open
            # without emitting audio on some Windows/network combinations.
            synthesize_method="rest",
        )
        # AgentSession otherwise selects TTS.stream(), which always uses the
        # Gnani WebSocket endpoint. Mark the provider as non-streaming so
        # LiveKit sentence-adapts it through the reliable REST synthesizer.
        session_tts.capabilities.streaming = False
        logger.info("[VOICE] Gnani TTS transport=REST (streaming WebSocket disabled)")
    else:
        if tts_provider == "elevenlabs" and elevenlabs is None:
            logger.error(
                "[VOICE] ElevenLabs was selected but its plugin is unavailable: %s. "
                "Falling back to LiveKit Inference TTS.",
                _elevenlabs_import_error or "unknown import error",
            )
        elif tts_provider == "elevenlabs" and not elevenlabs_api_key:
            logger.error(
                "[VOICE] ElevenLabs was selected but ELEVENLABS_API_KEY is missing. "
                "Falling back to LiveKit Inference TTS."
            )
        elif tts_provider == "gnani" and not use_gnani_stt:
            logger.error(
                "[VOICE] Gnani TTS was selected but Gnani is unavailable. "
                "Falling back to LiveKit Inference TTS."
            )
        # Thalia has a warm, professional delivery that suits a calm technical
        # interviewer better than the previous more synthetic default.
        inference_voice = os.getenv("LIVEKIT_TTS_VOICE", "thalia")
        logger.info(
            "[VOICE] Using LiveKit Inference TTS (Deepgram Aura-2, voice=%s)",
            inference_voice,
        )
        session_tts = inference.TTS(model="deepgram/aura-2", voice=inference_voice, language="en")

    session = AgentSession(
        stt=session_stt,
        tts=session_tts,
        vad=_preloaded_vad,
        turn_detection="manual",
    )

    async def deliver_question_audio(question_text: str) -> bool:
        """Speak through the selected provider, with a safe browser fallback.

        Returning False tells the frontend to use browser SpeechSynthesis. This
        preserves an interview even when a provider is unavailable, while the
        normal path uses the much more natural Deepgram/LiveKit voice.
        """
        delivery_mode = os.getenv("INTERVIEW_VOICE_DELIVERY", "provider").strip().lower()
        if delivery_mode == "browser":
            logger.info("[QUESTION DELIVERY] Browser TTS selected by configuration")
            return False

        speech = None
        try:
            logger.info("[QUESTION DELIVERY] Starting provider voice playback")
            await broadcast_state("AI_SPEAKING", current_q)
            speech = session.say(
                question_text,
                allow_interruptions=False,
                add_to_chat_ctx=False,
            )
            # Questions are intentionally short. Do not let a provider-side
            # stream that never closes block the entire interview.
            await asyncio.wait_for(
                speech.wait_for_playout(),
                timeout=min(TTS_SPEECH_TIMEOUT_SECONDS, 25.0),
            )
            if speech.exception() is not None:
                raise speech.exception()
            logger.info("[QUESTION DELIVERY] Provider voice playback complete")
            return True
        except Exception as error:
            logger.warning(
                "[QUESTION DELIVERY] Provider voice failed (%s); using browser fallback",
                error,
            )
            if speech is not None:
                with contextlib.suppress(Exception):
                    speech.interrupt(force=True)
            return False

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev: AgentStateChangedEvent):
        logger.info("[AGENT STATE] %s", ev.new_state)
        new_state = ev.new_state
        if new_state == "speaking":
            asyncio.create_task(broadcast_state("AI_SPEAKING"))
        elif new_state == "listening":
            # Only broadcast READY_TO_ANSWER when we are genuinely waiting.
            # DO NOT touch is_processing_turn here — it is owned by handle_user_speech.
            if interview_phase == "WAITING_FOR_ANSWER" and current_q > 0:
                asyncio.create_task(broadcast_state("READY_TO_ANSWER", current_q))

    candidate_transcript_buffer = []
    final_transcript_event = asyncio.Event()
    # Groq STT can return a final segment shortly after its first request times
    # out. Keep this flag so that late result is still evaluated instead of
    # leaving the candidate at the same question.
    awaiting_late_transcript = False

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev):
        nonlocal is_processing_turn, interview_phase, awaiting_late_transcript
        if getattr(ev, "is_final", False) and getattr(ev, "transcript", ""):
            text = ev.transcript.strip()
            if text:
                logger.info("[DEBUG-STT] TRANSCRIPT EVENT RECEIVED")
                logger.info("[DEBUG-STT] IS FINAL = True")
                logger.info("[DEBUG-STT] TRANSCRIPT TEXT = %s", text)
                candidate_transcript_buffer.append(text)
                final_transcript_event.set()
                if (
                    awaiting_late_transcript
                    and interview_phase == "WAITING_FOR_ANSWER"
                    and not is_processing_turn
                ):
                    logger.info("[DEBUG-STT] LATE FINAL TRANSCRIPT — resuming answer evaluation")
                    awaiting_late_transcript = False
                    is_processing_turn = True
                    interview_phase = "PROCESSING"
                    asyncio.create_task(process_answer_task())

    async def repeat_current_question():
        """Replay the current question without advancing the interview state."""
        nonlocal interview_phase
        if interview_phase != "WAITING_FOR_ANSWER" or not current_question_text:
            logger.info(
                "[REPEAT] Ignored phase=%s question_available=%s",
                interview_phase, bool(current_question_text),
            )
            return

        logger.info("[REPEAT] Replaying question_number=%s", current_q)
        provider_speech_played = await deliver_question_audio(current_question_text)
        await publish({
            "type":           "question_ready",
            "question":       current_question_text,
            "language":       current_question_language,
            "speak_in_browser": not provider_speech_played,
            "question_number": current_q,
            "question_count": question_count,
            "is_repeat":      True,
        })

    @ctx.room.on("data_received")
    def on_data_received(data_packet):
        nonlocal is_processing_turn, interview_phase, awaiting_late_transcript, candidate_ready_for_question
        try:
            payload_text = data_packet.data.decode("utf-8")
            logger.info("DATA RECEIVED: %s", payload_text)
            payload = json.loads(payload_text)

            if payload.get("type") == "candidate_ready":
                if candidate_ready_for_question:
                    logger.info("[ROOM] Duplicate candidate_ready ignored")
                    return
                candidate_ready_for_question = True
                logger.info("[ROOM] BROWSER DATA LISTENER READY — starting Question 1")
                asyncio.create_task(generate_interview_question("initial"))

            elif payload.get("type") == "start_answering":
                logger.info("START ANSWERING RECEIVED phase=%s", interview_phase)
                candidate_transcript_buffer.clear()
                final_transcript_event.clear()
                awaiting_late_transcript = False
                asyncio.ensure_future(broadcast_state("RECORDING"))

            elif payload.get("type") == "stop_answering":
                if is_processing_turn:
                    return
                if interview_phase != "WAITING_FOR_ANSWER":
                    return
                is_processing_turn = True
                awaiting_late_transcript = False
                interview_phase = "PROCESSING"
                logger.info("[PROCESSING LOCK] is_processing_turn = True")
                logger.info("[PTT] STOP ANSWERING RECEIVED")
                logger.info("[DEBUG-STT] STOP RECEIVED")
                logger.info("[DEBUG-STT] COMMIT USER TURN")
                logger.info("STATE: PROCESSING")
                asyncio.ensure_future(broadcast_state("PROCESSING"))
                try:
                    session.commit_user_turn()
                except Exception as e:
                    logger.warning("commit_user_turn err: %s", e)
                asyncio.create_task(process_answer_task())

            elif payload.get("type") == "complete_interview":
                logger.info("[DATA IN] complete_interview received")
                asyncio.ensure_future(do_complete_interview())

            elif payload.get("type") == "repeat_question":
                logger.info("[DATA IN] repeat_question received")
                asyncio.create_task(repeat_current_question())

        except Exception:
            logger.exception("ERROR HANDLING DATA RECEIVED")

    # ── Start session and fire Q1 ─────────────────────────────────────────────
    logger.info("[ROOM] STARTING AGENT SESSION")
    await session.start(room=ctx.room, agent=interviewer_agent)
    logger.info("[ROOM] AGENT SESSION STARTED")
    logger.info("[ROOM] ROOMIO ACTIVE")

    # Wait for the browser's explicit data-channel acknowledgement. LiveKit
    # data packets are not replayed to late joiners, so generating Question 1
    # here can race ahead of the browser's listener.
    logger.info("[ROOM] WAITING FOR BROWSER DATA LISTENER BEFORE INITIAL QUESTION")

    # ── Answer Evaluation ──────────────────────────────────────────────────────
    async def evaluate_answer(question: str, answer: str) -> dict:
        logger.info("[EVAL DEBUG] question = %s", question)
        logger.info("[EVAL DEBUG] candidate_answer = %s", answer)
        logger.info("[EVAL DEBUG] answer_length = %d", len(answer))
        prompt = f"""Evaluate the candidate's answer to the following interview question using competencies that matter for this role and domain. Do not assume the work is technical unless the role requires it.
Domain: {domain}
Role: {role}
Difficulty: {difficulty}

Question: {question}
Candidate Answer: {answer}

Provide a JSON response with the following fields:
- score (0-100)
- correctness (string describing accuracy, quality, or effectiveness for this role)
- relevance (0-10)
- completeness (0-10)
- technical_depth (0-10; interpret as role-specific competency and depth, including nontechnical skills)
- feedback (constructive feedback for the candidate)
- strengths (list of strings)
- weaknesses (list of strings)
        """
        try:
            return await request_json(prompt, "ANSWER_EVALUATION")
        except Exception:
            logger.exception("[LLM] Failed to generate or parse answer evaluation JSON")
            return {
                "score": 0,
                "correctness": "Evaluation unavailable",
                "relevance": 0,
                "completeness": 0,
                "technical_depth": 0,
                "feedback": "Unable to evaluate answer due to parsing error.",
                "strengths": [],
                "weaknesses": [],
            }

    # ── Candidate answer handler ───────────────────────────────────────────────
    async def process_answer_task():
        nonlocal is_processing_turn, interview_phase, awaiting_late_transcript
        try:
            # STT may emit several final segments for one spoken answer. Wait
            # for a short quiet period after the latest segment before scoring,
            # otherwise the first segment can be mistaken for the whole answer.
            transcript_deadline = asyncio.get_running_loop().time() + 10.0
            while True:
                remaining = transcript_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break

                final_transcript_event.clear()
                # With no text yet, allow the full window for the first final
                # transcript. Once text exists, finish after 1.5 seconds with
                # no additional segments.
                wait_seconds = min(
                    remaining,
                    1.5 if candidate_transcript_buffer else remaining,
                )
                try:
                    await asyncio.wait_for(final_transcript_event.wait(), timeout=wait_seconds)
                except asyncio.TimeoutError:
                    break

            text = " ".join(candidate_transcript_buffer).strip()

            if not text:
                logger.info("[DEBUG-STT] EMPTY FINAL TRANSCRIPT")
                awaiting_late_transcript = True
                interview_phase = "WAITING_FOR_ANSWER"
                await publish({
                    "type":           "waiting_for_answer",
                    "question_number": current_q,
                    "question_count": MAX_INTERVIEW_QUESTIONS,
                })
                return

            logger.info("[DEBUG-STT] FINAL ANSWER ACCEPTED")
            awaiting_late_transcript = False
            logger.info("[DEBUG-STT] STARTING EVALUATION")

            interview_phase = "EVALUATING_ANSWER"
            substantive_answer = is_substantive_answer(text)
            logger.info("[EVAL DEBUG] transcript_buffer = %s", candidate_transcript_buffer)
            logger.info("[EVAL DEBUG] resolved_candidate_answer = %s", text)
            logger.info("[EVAL DEBUG] resolved_answer_length = %d", len(text))
            eval_data = (
                await evaluate_answer(current_question_text, text)
                if substantive_answer
                else missing_answer_evaluation()
            )
            logger.info("[DEBUG-STT] EVALUATION COMPLETED")

            result = {
                "question_number":       current_q,
                "question":              current_question_text,
                "candidate_answer":      text,
                "answer":                text,
                "is_substantive_answer": substantive_answer,
                "evaluation":            eval_data,
                "score":                 eval_data.get("score", 0),
                "correctness":           eval_data.get("correctness", ""),
                "feedback":              eval_data.get("feedback", ""),
                "strengths":             eval_data.get("strengths", []),
                "weaknesses":            eval_data.get("weaknesses", []),
            }
            interview_results.append(result)
            logger.info("[DEBUG-STT] RESULT STORED")

            if current_q < MAX_INTERVIEW_QUESTIONS:
                logger.info(
                    "[FLOW] NEXT QUESTION AUTHORIZED current_q=%s evaluated_answers=%d",
                    current_q, len(interview_results),
                )
                interview_phase = "GENERATING_QUESTION"
                await generate_interview_question("after_answer")
            else:
                logger.info("[FLOW] Final question evaluated - waiting for completion.")
                interview_phase = "WAITING_FOR_COMPLETION"
                await publish({"type": "interview_ready_to_complete"})

        except Exception:
            logger.exception("Error in process_answer_task")
            interview_phase = "WAITING_FOR_ANSWER"
            await publish({
                "type":           "waiting_for_answer",
                "question_number": current_q,
                "question_count":  MAX_INTERVIEW_QUESTIONS,
            })
        finally:
            is_processing_turn = False
            logger.info("[PROCESSING LOCK] is_processing_turn = False")
            return

    # ── Complete interview (frontend button) ───────────────────────────────────
    async def do_complete_interview():
        nonlocal report_generation_started, interview_phase

        if report_generation_started:
            logger.info("[COMPLETE_INTERVIEW] Ignoring duplicate")
            return
        report_generation_started = True
        interview_phase = "GENERATING_REPORT"

        logger.info("[COMPLETE_INTERVIEW] Received")
        await publish({"type": "report_started"})

        logger.info(
            "[REPORT] RESULTS COUNT = %d (configured questions=%d)",
            len(interview_results), MAX_INTERVIEW_QUESTIONS,
        )
        logger.info(
            "[REPORT] Final interview_results: %s",
            json.dumps(interview_results, indent=2),
        )

        scores = [
            safe_score(result.get("score"))
            if result.get("is_substantive_answer", is_substantive_answer(result.get("answer", "")))
            else 0
            for result in interview_results
        ]
        overall = round(sum(scores) / len(scores)) if scores else 0
        has_substantive_answer = any(
            result.get("is_substantive_answer", is_substantive_answer(result.get("answer", "")))
            for result in interview_results
        )

        logger.info("[LLM CALL] source=FINAL_REPORT")
        try:
            prompt = f"""Generate a final interview report based on the following candidate evaluations. Assess fit for the specified role and domain; do not assume this is a technology role:
Domain: {domain}
Role: {role}
Difficulty: {difficulty}

Evaluations:
{json.dumps(interview_results, indent=2)}

Provide a JSON response matching this schema exactly:
- overall_score (0-100)
- technical_score (0-100; use this field for role-specific competency, whether technical or nontechnical)
- communication_score (0-100)
- strengths (list of strings)
- weaknesses (list of strings)
- final_feedback (string summarizing performance)
- recommendation (string, e.g. "STRONG HIRE", "HIRE", "NO HIRE")
"""
            # Per-question evaluation already exists. Keep the optional
            # narrative synthesis bounded so a slow model cannot leave the
            # candidate on the report-generation state indefinitely.
            report_data = await asyncio.wait_for(
                request_json(prompt, "FINAL_REPORT"),
                timeout=15.0,
            )

            report = {
                "overall_score":       report_data.get("overall_score", overall),
                "technical_score":     report_data.get("technical_score", overall),
                "communication_score": report_data.get("communication_score", overall),
                "strengths":           report_data.get("strengths", []),
                "weaknesses":          report_data.get("weaknesses", []),
                "final_feedback":      report_data.get("final_feedback", "Overall solid performance."),
                "recommendation":      report_data.get("recommendation", "CONSIDER"),
                "question_results":    interview_results,
            }
        except Exception:
            logger.exception("[LLM] Failed to generate or parse final report JSON")
            strengths = []
            weaknesses = []
            for result in interview_results:
                strengths.extend(result.get("strengths") or [])
                weaknesses.extend(result.get("weaknesses") or [])
            strengths = list(dict.fromkeys(strengths))[:5]
            weaknesses = list(dict.fromkeys(weaknesses))[:5]
            if not strengths:
                strengths = ["Completed the interview"]
            if not weaknesses:
                weaknesses = ["Review the topics covered in the interview"]
            recommendation = (
                "STRONG HIRE" if overall >= 85
                else "HIRE" if overall >= 70
                else "CONSIDER" if overall >= 50
                else "NO HIRE"
            )
            report = {
                "overall_score":       overall,
                "technical_score":     overall,
                "communication_score": overall,
                "strengths":           strengths,
                "weaknesses":          weaknesses,
                "final_feedback":      "The automated narrative report was unavailable, so this summary is based on the per-question evaluations.",
                "recommendation":      recommendation,
                "question_results":    interview_results,
            }

        # A report model must not manufacture positives from an interview with
        # no answer. This policy takes precedence over model-generated prose.
        if not has_substantive_answer:
            report.update({
                "overall_score":       0,
                "technical_score":     0,
                "communication_score": 0,
                "strengths":           [],
                "weaknesses": [
                    "Provide a substantive answer to each question.",
                    "Explain your reasoning with relevant role-specific knowledge and examples.",
                ],
                "final_feedback":  "No substantive answers were recorded, so role-specific competencies and communication could not be assessed.",
                "recommendation":  "NO HIRE",
            })

        try:
            await complete_session(session_id, report)
            logger.info("[REPORT] Stored via complete_session")
        except Exception as error:
            # Do not leave the browser on an infinite report spinner if a
            # worker-to-API network/configuration error occurs.
            logger.exception("[REPORT] Failed to store report")
            report_generation_started = False
            interview_phase = "WAITING_FOR_COMPLETION"
            await publish({"type": "report_failed", "message": str(error)})
            return

        interview_phase = "COMPLETE"
        await publish({"type": "interview_completed"})

        await asyncio.sleep(1)
        await ctx.room.disconnect()
        logger.info("[INTERVIEW] COMPLETE — disconnected")

    # user_speech_committed is intentionally NOT wired: answer processing
    # is driven by process_answer_task launched from on_data_received.


if __name__ == "__main__":
    agents.cli.run_app(server)
