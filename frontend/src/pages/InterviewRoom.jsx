import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../api';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  BarVisualizer,
  useLocalParticipant,
  useRoomContext,
} from '@livekit/components-react';

import { RoomEvent } from 'livekit-client';
import interviewerPortrait  from '../assets/ai-interviewer.png';
import interviewerSpeaking  from '../assets/ai-speaking.png';
import interviewerListening from '../assets/ai-listening.png';

// ─── Push-to-talk control ────────────────────────────────────────────────────

function PushToTalkControl({ interviewState, onCompleteInterview, onRepeatQuestion }) {
  const { localParticipant } = useLocalParticipant();
  const room  = useRoomContext();
  const state = interviewState || 'SETUP';

  // One-shot guard: prevents double-click sending stop_answering twice per session.
  const isStoppingRef = React.useRef(false);

  // ── Single authoritative mic controller ──────────────────────────────────
  // The mic is enabled ONLY while state === 'RECORDING'.
  // This is the ONLY place setMicrophoneEnabled is called — no other effect
  // or handler should call it, which eliminates the race condition where
  // isMicrophoneEnabled changing triggered an effect that immediately
  // re-disabled the mic before the state machine caught up.
  useEffect(() => {
    if (!localParticipant) return;
    if (state === 'RECORDING') {
      localParticipant.setMicrophoneEnabled(true).then(() => {
        const pub = localParticipant.getTrackPublications().find(p => p.kind === 'audio');
        console.log('[PTT AUDIO] MIC ENABLED for RECORDING', {
          publicationExists: !!pub,
          trackSid:     pub?.trackSid,
          trackEnabled: pub?.track?.mediaStreamTrack?.enabled,
          isMuted:      pub?.isMuted,
        });
      }).catch(err => console.error('[PTT AUDIO] FAILED TO ENABLE MIC', err));
    } else {
      localParticipant.setMicrophoneEnabled(false);
    }
  }, [state, localParticipant]);

  // Reset the STOP guard whenever a new recording session starts.
  useEffect(() => {
    if (state === 'RECORDING') {
      isStoppingRef.current = false;
    }
  }, [state]);

  const handleStart = async () => {
    console.log('[PTT AUDIO] START REQUESTED — sending start_answering (mic will enable when RECORDING state arrives)');
    const payload = JSON.stringify({ type: 'start_answering' });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
  };

  const handleStop = async () => {
    console.log('[PTT] STOP HANDLER ENTERED state=%s isStopping=%s', state, isStoppingRef.current);
    if (state !== 'RECORDING') return;
    if (isStoppingRef.current) {
      console.log('[PTT] STOP HANDLER BLOCKED — already stopping');
      return;
    }
    isStoppingRef.current = true;
    console.log('[PTT AUDIO] STOP — sending stop_answering (mic will disable when state leaves RECORDING)');
    const payload = JSON.stringify({ type: 'stop_answering' });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
    console.log('[PTT] STOP HANDLER EXITED');
  };

  // Complete Interview button — shown only in WAITING_FOR_COMPLETION
  if (state === 'WAITING_FOR_COMPLETION') {
    return (
      <div className="flex flex-col items-center">
        <button
          onClick={onCompleteInterview}
          className="px-8 py-4 rounded-full font-semibold text-sm tracking-wide transition-all duration-300 shadow-lg bg-[#22C55E] text-white border border-[#22C55E] cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
        >
          ✓ COMPLETE INTERVIEW
        </button>
      </div>
    );
  }

  // Generating report spinner
  if (state === 'GENERATING_REPORT') {
    return (
      <div className="flex flex-col items-center">
        <button
          disabled
          className="px-8 py-4 rounded-full font-semibold text-sm tracking-wide shadow-lg bg-[#18181B] border border-[#6366F1] text-[#6366F1] opacity-70 cursor-not-allowed animate-pulse"
        >
          ⏳ GENERATING REPORT...
        </button>
      </div>
    );
  }

  let buttonText = '';
  let disabled   = true;
  let onClick    = null;
  let bgClass    = 'bg-[#18181B] border border-[#27272A] text-[#A1A1AA]';
  let pulse      = false;

  if (state === 'SETUP' || state === 'INTERVIEW_COMPLETE') {
    buttonText = state === 'SETUP' ? 'INITIALIZING...' : 'INTERVIEW COMPLETE';
    bgClass    = 'bg-[#18181B] border border-[#6366F1] text-[#6366F1]';
    disabled   = true;
    pulse      = true;
  } else if (state === 'PROCESSING') {
    buttonText = 'PROCESSING ANSWER...';
    bgClass    = 'bg-[#18181B] border border-[#6366F1] text-[#6366F1]';
    disabled   = true;
    pulse      = true;
  } else if (state === 'AI_SPEAKING') {
    buttonText = 'AI IS SPEAKING';
    bgClass    = 'bg-[#18181B] border border-[#27272A] text-[#FAFAFA]';
    disabled   = true;
  } else if (state === 'RECORDING') {
    buttonText = 'STOP ANSWERING';
    disabled   = false;
    onClick    = handleStop;
    bgClass    = 'bg-[#EF4444] text-white border border-[#EF4444]';
    pulse      = true;
  } else if (state === 'READY_TO_ANSWER') {
    buttonText = 'START ANSWERING';
    disabled   = false;
    onClick    = handleStart;
    bgClass    = 'bg-[#FAFAFA] text-[#09090B] border border-[#FAFAFA] hover:bg-white';
  }

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={onClick}
        disabled={disabled}
        className={`px-8 py-4 rounded-full font-semibold text-sm tracking-wide transition-all duration-300 shadow-lg ${bgClass} ${disabled ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer hover:scale-[1.02] active:scale-[0.98]'} ${pulse ? 'animate-pulse' : ''}`}
      >
        {buttonText}
      </button>
      {state === 'READY_TO_ANSWER' && (
        <button
          type="button"
          onClick={onRepeatQuestion}
          className="repeat-question-button"
          aria-label="Repeat the current question"
        >
          ↻ Repeat question
        </button>
      )}
    </div>
  );
}

// ─── Agent visualizer ────────────────────────────────────────────────────────

function AgentVisualizer({ interviewState }) {
  const { audioTrack } = useVoiceAssistant();

  const stateDetails = {
    SETUP: {
      variant: 'ready',
      title:   'Ready for the technical challenge?',
      detail:  "You've got this. Take a breath. Your interview is about to begin.",
    },
    AI_SPEAKING: {
      variant: 'speaking',
      title:   'AI interviewer is speaking',
      detail:  'Listen carefully to the question.',
    },
    READY_TO_ANSWER: {
      variant: 'ready',
      title:   'Your turn',
      detail:  'Press Start Answering when you are ready.',
    },
    RECORDING: {
      variant: 'listening',
      title:   'Listening…',
      detail:  'Speak naturally, then press Stop Answering.',
    },
    PROCESSING: {
      variant: 'processing',
      title:   'Analyzing your answer…',
      detail:  'Your response is being processed.',
    },
    WAITING_FOR_COMPLETION: {
      variant: 'complete',
      title:   'Screening questions complete',
      detail:  'Finish the screening to create the assessment report.',
    },
    GENERATING_REPORT: {
      variant: 'processing',
      title:   'Creating assessment report…',
      detail:  'Please keep this window open.',
    },
  };

  const visualState = stateDetails[interviewState] || {
    variant: 'ready',
    title:   'Ready for the technical challenge?',
    detail:  "You've got this. Take a breath. Your interview is about to begin.",
  };

  const isSpeaking = interviewState === 'AI_SPEAKING';

  return (
    <section
      className={`agent-visual-shell agent-visual-shell--${visualState.variant}`}
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="agent-visual-orb" aria-hidden="true">
        <span className="agent-visual-ring agent-visual-ring--outer" />
        <span className="agent-visual-ring agent-visual-ring--inner" />
        <div className="agent-orb-core">
          {isSpeaking && audioTrack ? (
            <BarVisualizer
              state="speaking"
              trackRef={audioTrack}
              className="agent-waveform"
              barCount={5}
              options={{ minHeight: 4, colors: ['#FAFAFA'] }}
            />
          ) : interviewState === 'RECORDING' ? (
            <span className="agent-mic-symbol">●</span>
          ) : interviewState === 'PROCESSING' || interviewState === 'GENERATING_REPORT' ? (
            <span className="agent-loader-dots"><i /><i /><i /></span>
          ) : interviewState === 'WAITING_FOR_COMPLETION' ? (
            <span className="agent-complete-symbol">✓</span>
          ) : (
            <span className="agent-idle-symbol">✦</span>
          )}
        </div>
      </div>
      <div className="agent-state-copy">
        <p className="agent-state-title">{visualState.title}</p>
        <p className="agent-state-detail">{visualState.detail}</p>
      </div>
    </section>
  );
}

// ─── Interview room content (inside LiveKitRoom) ──────────────────────────────

function InterviewRoomContent({ sessionData, sessionId }) {
  const room     = useRoomContext();
  const navigate = useNavigate();
  const [interviewState, setInterviewState] = useState('SETUP');
  const [browserSpeechActive, setBrowserSpeechActive] = useState(false);
  const [currentQ, setCurrentQ] = useState(1);
  const [totalQ, setTotalQ]     = useState(sessionData.setup.num_questions || 5);
  const speechRequestRef = useRef(0);
  const speechTimerRef   = useRef(null);

  // ── Browser Speech Synthesis (fallback TTS) ───────────────────────────────
  const speakQuestionInBrowser = useCallback(async (question, questionLanguage = 'english') => {
    if (!question?.trim() || !('speechSynthesis' in window)) {
      setBrowserSpeechActive(false);
      return;
    }

    const requestId = ++speechRequestRef.current;
    if (speechTimerRef.current) window.clearTimeout(speechTimerRef.current);
    window.speechSynthesis.cancel();

    // Chrome can expose an empty voice list on the first utterance. Waiting
    // briefly for voiceschanged avoids the crackle/truncated first question.
    const voices = await new Promise((resolve) => {
      const available = window.speechSynthesis.getVoices();
      if (available.length) { resolve(available); return; }
      const finish = () => {
        window.speechSynthesis.removeEventListener('voiceschanged', finish);
        resolve(window.speechSynthesis.getVoices());
      };
      window.speechSynthesis.addEventListener('voiceschanged', finish, { once: true });
      window.setTimeout(finish, 700);
    });
    if (speechRequestRef.current !== requestId) return;

    const utterance = new SpeechSynthesisUtterance(question);
    const isHindi       = questionLanguage === 'hindi' || /[\u0900-\u097F]/.test(question);
    const hindiVoice    = voices.find((v) => /^hi[-_]/i.test(v.lang));
    const indianFemale  = voices.find((v) => /en[-_]in/i.test(v.lang) && /female|woman|zira|heera|priya|kavya|neerja/i.test(v.name));
    const femaleVoice   = voices.find((v) => /female|woman|zira|heera|samantha|karen|susan|priya|kavya|neerja/i.test(v.name));
    const indianVoice   = voices.find((v) => /en[-_]in/i.test(v.lang));
    const voice         = isHindi ? (hindiVoice || indianFemale || femaleVoice || indianVoice) : (indianFemale || femaleVoice || indianVoice || voices[0]);

    if (voice) utterance.voice = voice;
    utterance.lang  = voice?.lang || (isHindi ? 'hi-IN' : 'en-IN');
    utterance.rate  = 0.96;
    utterance.pitch = 1;
    utterance.onend = utterance.onerror = () => {
      if (speechRequestRef.current === requestId) setBrowserSpeechActive(false);
    };

    setBrowserSpeechActive(true);
    // Let Chrome settle after the initial room/navigation work before its
    // first synthesis request. This prevents the first-word crackle seen on
    // some desktop and Android browsers.
    speechTimerRef.current = window.setTimeout(() => {
      if (speechRequestRef.current !== requestId) return;
      window.speechSynthesis.speak(utterance);
      window.speechSynthesis.resume();
    }, 120);
  }, []);

  // Cancel any in-progress speech on unmount
  useEffect(() => () => {
    speechRequestRef.current += 1;
    if (speechTimerRef.current) window.clearTimeout(speechTimerRef.current);
    window.speechSynthesis?.cancel();
  }, []);

  const displayedInterviewState = browserSpeechActive ? 'AI_SPEAKING' : interviewState;
  const interviewerVisual = interviewState === 'AI_SPEAKING'
    ? { source: interviewerSpeaking,  label: 'AI interviewer speaking'  }
    : interviewState === 'RECORDING'
      ? { source: interviewerListening, label: 'AI interviewer listening' }
      : { source: interviewerPortrait,  label: 'AI interviewer avatar'   };

  // ── Complete interview handler ─────────────────────────────────────────────
  const handleCompleteInterview = async () => {
    setInterviewState('GENERATING_REPORT');
    const payload = JSON.stringify({ type: 'complete_interview' });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
    console.log('[PTT] Sent complete_interview');
  };

  // ── Repeat question handler ───────────────────────────────────────────────
  const handleRepeatQuestion = async () => {
    const payload = JSON.stringify({ type: 'repeat_question' });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
    console.log('[PTT] Sent repeat_question');
  };

  // ── Data channel listener ─────────────────────────────────────────────────
  useEffect(() => {
    if (!room) return;

    const handleData = (payload) => {
      try {
        const data = JSON.parse(new TextDecoder().decode(payload));
        console.log('[DATA IN]', data);

        if (
          data.type === 'interview_state' ||
          data.type === 'question_state'  ||
          data.type === 'question_started'
        ) {
          if (data.state)           setInterviewState(data.state);
          if (data.question_number) setCurrentQ(data.question_number);
          if (data.question_count)  setTotalQ(data.question_count);
        }

        if (data.type === 'question_ready') {
          if (data.question_number) setCurrentQ(data.question_number);
          if (data.question_count)  setTotalQ(data.question_count);
          // Deepgram/LiveKit voice is the default. Browser speech is kept only
          // for the backend's explicit provider-failure fallback.
          if (data.speak_in_browser !== false) {
            speakQuestionInBrowser(data.question, data.language);
          }
        }

        if (data.type === 'waiting_for_answer') {
          console.log('[FLOW] waiting_for_answer received — transitioning to READY_TO_ANSWER');
          setInterviewState('READY_TO_ANSWER');
          if (data.question_number) setCurrentQ(data.question_number);
          if (data.question_count)  setTotalQ(data.question_count);
        }

        if (data.type === 'interview_ready_to_complete') {
          console.log('[FLOW] interview_ready_to_complete received — showing Complete Interview button');
          setInterviewState('WAITING_FOR_COMPLETION');
          if (data.question_number) setCurrentQ(data.question_number);
          if (data.question_count)  setTotalQ(data.question_count);
        }

        if (data.type === 'interview_completed') {
          console.log('[FLOW] interview_completed received — navigating to report');
          navigate(`/report?session_id=${sessionId}`);
        }

        if (data.type === 'report_failed') {
          console.error('[REPORT] Worker could not store the report', data.message);
          setInterviewState('WAITING_FOR_COMPLETION');
        }

        // Legacy: auto-navigate on INTERVIEW_COMPLETE state (kept for safety)
        if (data.state === 'INTERVIEW_COMPLETE') {
          navigate(`/report?session_id=${sessionId}`);
        }
      } catch (e) {
        console.error('Failed to parse data message', e);
      }
    };

    room.on(RoomEvent.DataReceived, handleData);
    return () => { room.off(RoomEvent.DataReceived, handleData); };
  }, [room, navigate, sessionId, speakQuestionInBrowser]);

  // ── Report polling (fallback if LiveKit disconnects during generation) ────
  useEffect(() => {
    if (interviewState !== 'GENERATING_REPORT') return undefined;

    let cancelled = false;
    let attempts  = 0;
    const checkForReport = async () => {
      attempts += 1;
      try {
        const response = await api.get(`/api/interview/session/${sessionId}`);
        if (!cancelled && response.data?.report) {
          navigate(`/report?session_id=${sessionId}`, { replace: true });
          return;
        }
      } catch (error) {
        console.warn('[REPORT] Waiting for saved report', error);
      }
      // The worker limits narrative generation to 15 seconds. If the report
      // still hasn't saved after a minute, restore the completion button.
      if (!cancelled && attempts >= 40) {
        setInterviewState('WAITING_FOR_COMPLETION');
      }
    };

    checkForReport();
    const pollTimer = window.setInterval(checkForReport, 1500);
    return () => { cancelled = true; window.clearInterval(pollTimer); };
  }, [interviewState, navigate, sessionId]);

  // ── Candidate-ready handshake ─────────────────────────────────────────────
  // Tell the worker that the browser's data listener is installed before
  // Question 1 is fired. LiveKit data packets are not replayed to late joiners.
  useEffect(() => {
    if (!room) return undefined;

    let announced = false;
    const announceReady = async () => {
      if (announced || !room.localParticipant || room.state !== 'connected') return;
      try {
        const payload = JSON.stringify({ type: 'candidate_ready' });
        await room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
        announced = true;
        console.log('[ROOM] Candidate browser data listener ready');
      } catch (error) {
        console.error('[ROOM] Could not announce browser readiness', error);
      }
    };

    announceReady();
    room.on(RoomEvent.Connected, announceReady);
    // A room can finish connecting just after this component mounted. Retry a
    // few times so the initial question cannot be lost to that timing window.
    const retryTimer = window.setInterval(announceReady, 500);

    return () => {
      room.off(RoomEvent.Connected, announceReady);
      window.clearInterval(retryTimer);
    };
  }, [room]);

  // ── Debug log ─────────────────────────────────────────────────────────────
  useEffect(() => {
    console.log('[PTT STATE]', { interviewState, currentQuestion: currentQ });
  }, [interviewState, currentQ]);

  return (
    <>
      {/* Header */}
      <header className="w-full flex items-center justify-between px-6 py-4 border-b border-[#27272A] bg-[#09090B]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="text-[13px] font-semibold tracking-[0.08em] uppercase text-[#FAFAFA]">
          INTERVIEWOS
        </div>
        <div className="flex items-center space-x-6">
          <div className="hidden lg:flex text-[11px] text-[#A1A1AA] uppercase tracking-widest font-semibold">
            AI Technical Screening
          </div>
          <div className="hidden md:flex text-[12px] text-[#A1A1AA] uppercase tracking-widest font-medium">
            {sessionData.setup.role}
          </div>
          <div className="px-3 py-1 rounded-full bg-[#18181B] border border-[#27272A] text-[11px] font-bold text-[#FAFAFA]">
            Q {currentQ} / {totalQ}
          </div>
        </div>
      </header>

      {/* Progress Bar */}
      <div className="w-full h-1 bg-[#18181B]">
        <div
          className="h-full bg-[#6366F1] transition-all duration-500 ease-out"
          style={{ width: `${(currentQ / totalQ) * 100}%` }}
        />
      </div>

      <main className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 w-full max-w-7xl mx-auto">
        <div className="interview-room-layout w-full h-full min-h-[600px]">

          {/* Left Column: Visualizer & Controls */}
          <div className="interview-control-panel w-full flex flex-col items-center justify-center space-y-12 bg-[#111113] border border-[#27272A] rounded-[24px] p-8 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-[#6366F1]/5 to-transparent pointer-events-none" />

            <AgentVisualizer interviewState={displayedInterviewState} />

            <div className="w-full flex justify-center pt-8">
              <PushToTalkControl
                interviewState={displayedInterviewState}
                onCompleteInterview={handleCompleteInterview}
                onRepeatQuestion={handleRepeatQuestion}
              />
            </div>

            <button
              onClick={handleCompleteInterview}
              disabled={interviewState === 'GENERATING_REPORT'}
              className="text-[#A1A1AA] hover:text-[#4F46E5] disabled:opacity-50 text-[11px] font-medium uppercase tracking-wider transition-colors mt-auto"
            >
              Finish screening and view report
            </button>
          </div>

          {/* Right Column: AI Interviewer Presence */}
          <aside className="interviewer-presence" aria-label="AI interviewer">
            <div className="interviewer-presence-glow" aria-hidden="true" />
            <div className="interviewer-avatar-wrap">
              <span className="interviewer-avatar-ring interviewer-avatar-ring--one" aria-hidden="true" />
              <span className="interviewer-avatar-ring interviewer-avatar-ring--two" aria-hidden="true" />
              <div className="interviewer-avatar">
                <img src={interviewerVisual.source} alt={interviewerVisual.label} />
              </div>
              <span className="interviewer-online-dot" aria-hidden="true" />
            </div>
            <div className="interviewer-presence-copy">
              <p className="interviewer-presence-eyebrow">AI interviewer</p>
              <h2>Technical screening assistant</h2>
              <p>Guiding the candidate through this role-specific assessment.</p>
            </div>
            <div className="interviewer-presence-status">
              <span className="interviewer-presence-status-dot" aria-hidden="true" />
              <span>
                {displayedInterviewState === 'AI_SPEAKING'
                  ? 'Speaking now'
                  : displayedInterviewState === 'RECORDING'
                    ? 'Listening to candidate'
                    : 'Ready for the next response'}
              </span>
            </div>
          </aside>

        </div>
      </main>
    </>
  );
}

// ─── InterviewRoom (top-level, renders LiveKitRoom) ───────────────────────────

export default function InterviewRoom() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [token,       setToken]       = useState(null);
  const [url,         setUrl]         = useState(null);
  const [error,       setError]       = useState(null);
  const [sessionData, setSessionData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sessionId) { navigate('/'); return; }
    const fetchData = async () => {
      try {
        const [tokenRes, sessionRes] = await Promise.all([
          api.get(`/api/interview/session/${sessionId}/token`,  { timeout: 12000 }),
          api.get(`/api/interview/session/${sessionId}`,        { timeout: 12000 }),
        ]);
        setToken(tokenRes.data.token);
        setUrl(tokenRes.data.livekit_url);
        setSessionData(sessionRes.data);
      } catch (err) {
        console.error('Unable to initialize screening session:', err);
        setError('Unable to initialize the screening session. Confirm that the API and AI interviewer are running, then start a new screening.');
      }
    };
    fetchData();
  }, [sessionId, navigate]);

  if (error) return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center text-[#EF4444] p-4 font-sans">
      {error}
    </div>
  );

  if (!token || !url || !sessionData) return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center text-[#A1A1AA] font-sans">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-6 h-6 border-2 border-[#6366F1] border-t-transparent rounded-full animate-spin" />
        <div className="text-[12px] uppercase tracking-wider">Connecting to secure screening...</div>
      </div>
    </div>
  );

  return (
    <LiveKitRoom
      serverUrl={url}
      token={token}
      connect={true}
      audio={true}
      video={false}
      className="app-shell room-shell min-h-screen bg-[#09090B] text-[#FAFAFA] font-sans flex flex-col"
      onDisconnected={() => navigate(`/report?session_id=${sessionId}`)}
    >
      <InterviewRoomContent sessionData={sessionData} sessionId={sessionId} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
