        });
        return newTranscripts;
      });
    };

    room.on(RoomEvent.TranscriptionReceived, handleTranscription);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, handleTranscription);
    };
  }, [room]);
  
  return (
    <div className="flex flex-col h-full">
      <div className="text-[11px] font-medium text-[#A1A1AA] uppercase tracking-wider mb-4 border-b border-[#27272A] pb-2">
        Transcript
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 pr-2 scrollbar-thin scrollbar-thumb-[#27272A] scrollbar-track-transparent">
        {transcripts.map((msg, idx) => {
          if (!msg.text.trim()) return null;
          
          return (
            <div key={msg.id || idx} className={`flex flex-col ${msg.isAgent ? 'items-start' : 'items-end'}`}>
              <div className="text-[11px] font-semibold text-[#A1A1AA] mb-1">
                {msg.isAgent ? 'AI Interviewer' : 'You'}
              </div>
              <div className={`text-sm px-4 py-2.5 rounded-[12px] max-w-[85%] ${
                msg.isAgent 
                  ? 'bg-[#18181B] text-[#FAFAFA] border border-[#27272A]' 
                  : 'bg-[#6366F1] text-white'
              }`}>
                {msg.text}
              </div>
            </div>
          );
        })}
        {transcripts.length === 0 && (
          <div className="text-sm text-[#A1A1AA] text-center italic mt-10">
            Conversation will appear here...
          </div>
        )}
      </div>
    </div>
  );
}
