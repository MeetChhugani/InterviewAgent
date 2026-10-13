function PushToTalkControl({ interviewState }) {
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const room = useRoomContext();
  const state = interviewState || 'SETUP';

  const handleStart = async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(true);
    }
    const payload = JSON.stringify({ type: "start_answering" });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
  };

  const handleStop = async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(false);
    }
    const payload = JSON.stringify({ type: "stop_answering" });
    const encoder = new TextEncoder();
    if (room && room.localParticipant) {
      await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }
  };

  useEffect(() => {
    if (state !== 'RECORDING' && isMicrophoneEnabled) {
      localParticipant?.setMicrophoneEnabled(false);
    }
  }, [state, isMicrophoneEnabled, localParticipant]);

  let buttonText = "";
  let disabled = true;
  let onClick = null;
  let bgClass = "bg-[#18181B] border border-[#27272A] text-[#A1A1AA]";
  let pulse = false;

  if (state === 'SETUP' || state === 'INTERVIEW_COMPLETE') {
    buttonText = state === 'SETUP' ? "INITIALIZING..." : "INTERVIEW COMPLETE";
    bgClass = "bg-[#18181B] border border-[#6366F1] text-[#6366F1]";
    disabled = true;
    pulse = true;
  } else if (state === 'PROCESSING') {
    buttonText = "PROCESSING ANSWER...";
    bgClass = "bg-[#18181B] border border-[#6366F1] text-[#6366F1]";
    disabled = true;
    pulse = true;
  } else if (state === 'AI_SPEAKING') {
    buttonText = "AI IS SPEAKING";
    bgClass = "bg-[#18181B] border border-[#27272A] text-[#FAFAFA]";
    disabled = true;
  } else if (state === 'RECORDING') {
    buttonText = "STOP ANSWERING";
    disabled = false;
    onClick = handleStop;
    bgClass = "bg-[#EF4444] text-white border border-[#EF4444]";
    pulse = true;
  } else if (state === 'READY_TO_ANSWER') {
    buttonText = "START ANSWERING";
    disabled = false;
    onClick = handleStart;
    bgClass = "bg-[#FAFAFA] text-[#09090B] border border-[#FAFAFA] hover:bg-white";
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
    </div>
  );
}

function AgentVisualizer({ interviewState }) {
  const { audioTrack, agent } = useVoiceAssistant();
  
  const isActive = interviewState === 'AI_SPEAKING' || interviewState === 'PROCESSING';
  
  return (
    <div className="flex flex-col items-center justify-center space-y-6">
      <div className="relative flex items-center justify-center w-32 h-32">
        {/* Outer glowing rings */}
        <div className={`absolute inset-0 rounded-full border border-[#6366F1] transition-all duration-1000 ${isActive ? 'opacity-30 scale-150 animate-ping' : 'opacity-0 scale-100'}`}></div>
        <div className={`absolute inset-2 rounded-full border border-[#6366F1] transition-all duration-700 ${isActive ? 'opacity-50 scale-125 animate-pulse' : 'opacity-0 scale-100'}`}></div>
        
        {/* Core orb */}
        <div className={`relative z-10 w-24 h-24 rounded-full flex items-center justify-center transition-all duration-500 shadow-[0_0_30px_rgba(99,102,241,0.2)] ${
          isActive ? 'bg-gradient-to-br from-[#6366F1] to-[#4F46E5] scale-105' : 'bg-[#18181B] border border-[#27272A]'
        }`}>
          {audioTrack && interviewState === 'AI_SPEAKING' ? (
             <BarVisualizer state="speaking" trackRef={audioTrack} className="h-10 w-16" barCount={5} options={{ minHeight: 4, colors: ['#FAFAFA'] }} />
          ) : (
            <div className="w-4 h-4 rounded-full bg-[#FAFAFA] opacity-50"></div>
          )}
        </div>
      </div>
      
      <div className="text-[11px] font-bold uppercase tracking-widest text-[#6366F1]">
        {interviewState ? interviewState.replace(/_/g, ' ') : 'SETUP'}
      </div>
    </div>
  );
}

function InterviewRoomContent({ sessionData, sessionId }) {
  const room = useRoomContext();
  const navigate = useNavigate();
  const [interviewState, setInterviewState] = useState('SETUP');
  const [currentQ, setCurrentQ] = useState(1);
  const totalQ = sessionData.setup.num_questions;

  useEffect(() => {
    if (!room) return;
    
    const handleData = (payload, participant, kind, topic) => {
      try {
        const data = JSON.parse(new TextDecoder().decode(payload));
        if (data.type === 'interview_state' || data.type === 'question_state') {
          setInterviewState(data.state);
          if (data.question_number) {
            setCurrentQ(data.question_number);
          }
          if (data.state === 'INTERVIEW_COMPLETE') {
            navigate(`/report?session_id=${sessionId}`);
          }
        }
      } catch (e) {
        console.error("Failed to parse data message", e);
      }
    };
    
    room.on(RoomEvent.DataReceived, handleData);
    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room, navigate, sessionId]);

  return (
    <>
      {/* Header */}
      <header className="w-full flex items-center justify-between px-6 py-4 border-b border-[#27272A] bg-[#09090B]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="text-[13px] font-semibold tracking-[0.08em] uppercase text-[#FAFAFA]">
          INTERVIEWOS
        </div>
        <div className="flex items-center space-x-6">
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
        ></div>
      </div>

      <main className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 w-full max-w-5xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8 w-full h-full min-h-[600px]">
          
          {/* Left Column: Visualizer & Controls */}
          <div className="lg:col-span-2 flex flex-col items-center justify-center space-y-12 bg-[#111113] border border-[#27272A] rounded-[24px] p-8 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-[#6366F1]/5 to-transparent pointer-events-none"></div>
            
            <AgentVisualizer interviewState={interviewState} />
            
            <div className="w-full flex justify-center pt-8">
              <PushToTalkControl interviewState={interviewState} />
            </div>

            <button 
              onClick={() => navigate(`/report?session_id=${sessionId}`)}
              className="text-[#A1A1AA] hover:text-[#EF4444] text-[11px] font-medium uppercase tracking-wider transition-colors mt-auto"
            >
              End Interview Early
            </button>
          </div>

          {/* Right Column: Transcript */}
          <div className="lg:col-span-3 bg-[#111113] border border-[#27272A] rounded-[24px] p-6 shadow-2xl flex flex-col h-full max-h-[700px]">
             <TranscriptViewer />
          </div>

        </div>
      </main>
      
    </>
  );
}

export default function InterviewRoom() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [token, setToken] = useState(null);
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(null);
  const [sessionData, setSessionData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sessionId) {
      navigate('/');
      return;
    }
    const fetchData = async () => {
      try {
        const [tokenRes, sessionRes] = await Promise.all([
          axios.get(`http://localhost:8000/api/interview/session/${sessionId}/token`),
          axios.get(`http://localhost:8000/api/interview/session/${sessionId}`)
        ]);
        setToken(tokenRes.data.token);
        setUrl(tokenRes.data.livekit_url);
        setSessionData(sessionRes.data);
      } catch (err) {
        setError('Failed to connect to interview session.');
      }
    };
    fetchData();
  }, [sessionId, navigate]);

  if (error) return <div className="min-h-screen bg-[#09090B] flex items-center justify-center text-[#EF4444] p-4 font-sans">{error}</div>;
  if (!token || !url || !sessionData) return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center text-[#A1A1AA] font-sans">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-6 h-6 border-2 border-[#6366F1] border-t-transparent rounded-full animate-spin"></div>
        <div className="text-[12px] uppercase tracking-wider">Connecting to Secure Room...</div>
      </div>
    </div>
  );

  return (
    <LiveKitRoom
      serverUrl={url}
      token={token}
      connect={true}
      audio={false}
      video={false}
      className="min-h-screen bg-[#09090B] text-[#FAFAFA] font-sans flex flex-col"
      onDisconnected={() => navigate(`/report?session_id=${sessionId}`)}
    >
      <InterviewRoomContent sessionData={sessionData} sessionId={sessionId} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
