import React, { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import axios from 'axios';

export default function InterviewReport() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedQ, setExpandedQ] = useState(null);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await axios.get(`http://localhost:8000/api/interview/session/${sessionId}`);
        setReport(response.data.report);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    if (sessionId) {
      fetchReport();
    }
  }, [sessionId]);

  if (loading) return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center text-[#FAFAFA] font-sans">
      <div className="flex flex-col items-center space-y-4 animate-pulse">
        <div className="w-6 h-6 border-2 border-[#6366F1] border-t-transparent rounded-full animate-spin"></div>
        <div className="text-[12px] uppercase tracking-wider text-[#A1A1AA]">Generating Performance Report...</div>
      </div>
    </div>
  );

  if (!report) return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center font-sans">
      <div className="text-center p-8 bg-[#111113] border border-[#27272A] rounded-[16px] shadow-2xl">
        <div className="text-[#EF4444] mb-4 text-4xl">⚠</div>
        <div className="text-[#FAFAFA] font-semibold mb-2">Screening report unavailable</div>
        <div className="text-[#A1A1AA] text-sm mb-6">This candidate screening report is unavailable or incomplete.</div>
        <Link to="/" className="text-[#09090B] bg-[#FAFAFA] px-6 py-2.5 rounded-[10px] text-sm font-semibold hover:bg-white transition-colors">
          Create screening
        </Link>
      </div>
    </div>
  );

  return (
    <div className="app-shell report-shell min-h-screen bg-[#09090B] text-[#FAFAFA] font-sans selection:bg-[#6366F1] selection:text-white pb-20">
      <header className="w-full flex items-center justify-between px-6 py-4 border-b border-[#27272A] bg-[#09090B]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="text-[13px] font-semibold tracking-[0.08em] uppercase text-[#FAFAFA]">
          INTERVIEWOS
        </div>
        <Link to="/" className="text-[#A1A1AA] hover:text-[#FAFAFA] text-[12px] uppercase tracking-widest font-medium transition-colors">
          CREATE NEW SCREENING →
        </Link>
      </header>

      <main className="max-w-4xl mx-auto px-6 pt-12">
        {/* Header Section */}
        <div className="text-center mb-16">
          <div className="text-[12px] uppercase tracking-widest text-[#6366F1] font-bold mb-4">Screening complete</div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-6">Candidate Screening Report</h1>
          
          <div className="flex flex-col items-center justify-center">
            <div className="text-[80px] leading-none font-bold text-[#FAFAFA] tracking-tighter">
              {report.overall_score}
              <span className="text-3xl text-[#A1A1AA] font-normal tracking-normal ml-1">/ 100</span>
            </div>
          </div>
        </div>

        {/* Score Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-16">
          {report.technical_score !== undefined && (
            <ScoreCard title="TECHNICAL SCORE" score={report.technical_score} />
          )}
          {report.communication_score !== undefined && (
            <ScoreCard title="COMMUNICATION SCORE" score={report.communication_score} />
          )}
        </div>

        {/* Recommendation Box */}
        <div className="mb-16 bg-[#111113] border border-[#27272A] rounded-[16px] p-8 shadow-xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-[#6366F1]"></div>
          <h2 className="text-[11px] font-bold text-[#A1A1AA] uppercase tracking-widest mb-4">AI screening recommendation</h2>
          <p className="text-2xl font-bold text-[#FAFAFA] mb-3">{report.recommendation}</p>
          <p className="text-[#A1A1AA] text-sm leading-relaxed">{report.final_feedback}</p>
        </div>

        {/* Strengths & Weaknesses */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          <div className="bg-[#111113] border border-[#27272A] rounded-[16px] p-6 shadow-xl">
            <h3 className="text-[11px] font-bold text-[#22C55E] uppercase tracking-widest mb-5 flex items-center">
              <span className="w-2 h-2 rounded-full bg-[#22C55E] mr-2"></span>
              Strengths
            </h3>
            <ul className="space-y-3">
              {report.strengths?.map((s, i) => (
                <li key={i} className="text-[#FAFAFA] text-sm flex items-start">
                  <span className="text-[#22C55E] mr-3 font-bold">✓</span>
                  <span className="leading-relaxed">{s}</span>
                </li>
              ))}
              {(!report.strengths || report.strengths.length === 0) && (
                <li className="text-[#A1A1AA] text-sm leading-relaxed">
                  No demonstrated strengths were recorded because no substantive answers were provided.
                </li>
              )}
            </ul>
          </div>
          
          <div className="bg-[#111113] border border-[#27272A] rounded-[16px] p-6 shadow-xl">
            <h3 className="text-[11px] font-bold text-[#F59E0B] uppercase tracking-widest mb-5 flex items-center">
              <span className="w-2 h-2 rounded-full bg-[#F59E0B] mr-2"></span>
              Areas for Review
            </h3>
            <ul className="space-y-3">
              {report.weaknesses?.map((a, i) => (
                <li key={i} className="text-[#FAFAFA] text-sm flex items-start">
                  <span className="text-[#F59E0B] mr-3 font-bold">•</span>
                  <span className="leading-relaxed">{a}</span>
                </li>
              ))}
              {(!report.weaknesses || report.weaknesses.length === 0) && (
                <li className="text-[#A1A1AA] text-sm leading-relaxed">
                  Complete each response with relevant reasoning and examples so specific improvement areas can be assessed.
                </li>
              )}
            </ul>
          </div>
        </div>

        {/* Question Analysis */}
        <div>
          <h2 className="text-[11px] font-bold text-[#A1A1AA] uppercase tracking-widest mb-6 border-b border-[#27272A] pb-4">
            Question Performance
          </h2>
          <div className="space-y-4">
            {report.question_results?.map((q, idx) => {
              const isExpanded = expandedQ === idx;
              return (
                <div 
                  key={idx} 
                  className={`report-question-card bg-[#111113] border transition-all duration-300 rounded-[12px] overflow-hidden cursor-pointer shadow-md hover:border-[#6366F1]/50 ${isExpanded ? 'border-[#6366F1]' : 'border-[#27272A]'}`}
                  onClick={() => setExpandedQ(isExpanded ? null : idx)}
                >
                  <div className="report-question-card__summary p-5 flex justify-between items-center bg-[#18181B]/50 hover:bg-[#18181B] transition-colors">
                    <div className="flex-1 pr-4">
                      <div className="report-question-card__label text-[11px] text-[#A1A1AA] font-bold uppercase tracking-wider mb-2">QUESTION {String(idx + 1).padStart(2, '0')}</div>
                      <h4 className="report-question-card__question font-semibold text-sm text-[#FAFAFA] line-clamp-2">{q.question}</h4>
                    </div>
                    <div className="report-question-card__score text-right">
                      <div className="report-question-card__score-value text-xl font-bold text-[#FAFAFA]">{q.score}</div>
                      <div className="report-question-card__correctness text-[10px] text-[#A1A1AA] uppercase tracking-widest mt-1">{q.correctness}</div>
                    </div>
                  </div>
                  
                  {isExpanded && (
                    <div className="report-question-card__details p-6 border-t border-[#27272A] bg-[#111113] space-y-6 animate-in slide-in-from-top-2 duration-300">
                      <div>
                          <div className="text-[11px] font-bold text-[#A1A1AA] uppercase tracking-wider mb-2">Candidate Response</div>
                        <div className="text-sm text-[#FAFAFA] bg-[#18181B] border border-[#27272A] p-4 rounded-[10px] italic leading-relaxed">
                          "{q.answer}"
                        </div>
                      </div>
                      <div>
                          <div className="text-[11px] font-bold text-[#A1A1AA] uppercase tracking-wider mb-2">Assessment Feedback</div>
                        <p className="text-sm text-[#FAFAFA] leading-relaxed border-l-2 border-[#6366F1] pl-4 py-1">
                          {q.feedback}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        
        <div className="mt-16 text-center">
          <Link to="/" className="inline-flex items-center px-8 py-4 bg-[#FAFAFA] text-[#09090B] font-bold text-sm rounded-full hover:bg-white hover:scale-105 transition-all shadow-[0_0_15px_rgba(250,250,250,0.1)]">
            CREATE NEW SCREENING →
          </Link>
        </div>

      </main>
    </div>
  );
}

function ScoreCard({ title, score }) {
  return (
    <div className="bg-[#111113] border border-[#27272A] rounded-[16px] p-6 text-center shadow-xl hover:border-[#6366F1]/30 transition-colors">
      <h3 className="text-[#A1A1AA] text-[11px] uppercase tracking-widest font-bold mb-3">{title}</h3>
      <div className="text-3xl font-bold text-[#FAFAFA]">{score}</div>
    </div>
  );
}
