import React, { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../api';

function ScoreCard({ title, score }) {
  return (
    <div className="bg-[#111113] border border-[#27272A] rounded-[16px] p-6 text-center shadow-xl hover:border-[#6366F1]/30 transition-colors">
      <h3 className="text-[#A1A1AA] text-[11px] uppercase tracking-widest font-bold mb-3">{title}</h3>
      <div className="text-3xl font-bold text-[#FAFAFA]">{score}</div>
    </div>
  );
}

export default function InterviewReport() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [report,     setReport]     = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [expandedQ,  setExpandedQ]  = useState(null);
  const [loadError,  setLoadError]  = useState(false);
  const [waitingLong, setWaitingLong] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setLoading(false);
      setLoadError(true);
      return undefined;
    }

    let cancelled = false;
    let timer;
    const startedAt = Date.now();
    const fetchReport = async () => {
      try {
        const response = await api.get(`/api/interview/session/${sessionId}`);
        if (cancelled) return;
        if (response.data?.report) {
          setReport(response.data.report);
          setLoading(false);
          return;
        }
      } catch (err) {
        if (cancelled) return;
        if (err.response?.status === 404) {
          setLoadError(true);
          setLoading(false);
          return;
        }
        console.warn('[REPORT] Waiting for report service', err);
      }

      if (cancelled) return;
      if (Date.now() - startedAt >= 90000) {
        setLoadError(true);
        setLoading(false);
        return;
      }
      if (Date.now() - startedAt >= 20000) setWaitingLong(true);
      timer = window.setTimeout(fetchReport, 1800);
    };

    fetchReport();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sessionId]);

  if (loading) return (
    <div className="min-h-screen bg-[#F5F6FF] text-[#20264A] font-sans flex flex-col">
      <header className="w-full flex items-center justify-between px-6 md:px-10 py-5 border-b border-indigo-100 bg-white/80">
        <div className="text-sm font-extrabold tracking-[0.12em] text-[#312E81]">INTERVIEWOS</div>
        <div className="text-xs font-semibold text-[#73799A]">SCREENING COMPLETE</div>
      </header>
      <main className="flex-1 flex items-center justify-center p-6">
        <section className="w-full max-w-xl rounded-[28px] border border-indigo-100 bg-white px-8 py-12 md:px-14 text-center shadow-[0_28px_80px_rgba(60,69,145,0.12)]">
          <div className="relative mx-auto mb-8 grid h-24 w-24 place-items-center">
            <div className="absolute inset-0 rounded-full border-[3px] border-indigo-100" />
            <div className="absolute inset-0 rounded-full border-[3px] border-transparent border-t-indigo-600 animate-spin" />
            <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-violet-600 to-cyan-500 shadow-lg shadow-indigo-200" />
          </div>
          <p className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.2em] text-indigo-600">Thank you for your time</p>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-[#20264A]">Your screening is complete</h1>
          <p className="mx-auto mt-4 max-w-md text-sm md:text-base leading-relaxed text-[#73799A]">
            {waitingLong
              ? 'We’re still preparing your report. This can take a little longer; you can keep this page open.'
              : 'We’re bringing your responses together and preparing your screening report.'}
          </p>
          <div className="mt-9 flex items-center justify-center gap-2 text-xs font-bold text-[#526080]">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Interview finished
            <span className="mx-2 h-px w-8 bg-indigo-200" />
            <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" /> Report in progress
          </div>
        </section>
      </main>
      <footer className="pb-6 text-center text-xs text-[#9298B1]">You may leave this page open while the report is prepared.</footer>
    </div>
  );

  if (!report) return (
    <div className="min-h-screen bg-[#F5F6FF] flex items-center justify-center p-6 font-sans text-[#20264A]">
      <div className="w-full max-w-lg text-center p-9 md:p-12 bg-white border border-indigo-100 rounded-[24px] shadow-[0_24px_70px_rgba(60,69,145,0.1)]">
        <div className="mx-auto mb-6 grid h-14 w-14 place-items-center rounded-2xl bg-amber-50 text-amber-600 text-2xl">!</div>
        <p className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-indigo-600 mb-3">Screening complete</p>
        <h1 className="text-2xl font-extrabold mb-3">We couldn’t load the report yet</h1>
        <p className="text-sm leading-relaxed text-[#73799A] mb-7">
          {loadError
            ? 'The report service did not return a report. Please return to the screening page and try again.'
            : 'The report is not available right now. Please try again in a moment.'}
        </p>
        <Link to="/" className="inline-flex items-center justify-center rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white hover:bg-indigo-700 transition-colors">
          Return to screenings
        </Link>
      </div>
    </div>
  );

  return (
    <div className="app-shell report-shell min-h-screen bg-[#09090B] text-[#FAFAFA] font-sans selection:bg-[#6366F1] selection:text-white pb-20">
      <header className="w-full flex items-center justify-between px-6 py-4 border-b border-[#27272A] bg-[#09090B]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="text-[13px] font-semibold tracking-[0.08em] uppercase text-[#FAFAFA]">INTERVIEWOS</div>
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

        {/* Recommendation */}
        <div className="mb-16 bg-[#111113] border border-[#27272A] rounded-[16px] p-8 shadow-xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-[#6366F1]" />
          <h2 className="text-[11px] font-bold text-[#A1A1AA] uppercase tracking-widest mb-4">AI screening recommendation</h2>
          <p className="text-2xl font-bold text-[#FAFAFA] mb-3">{report.recommendation}</p>
          <p className="text-[#A1A1AA] text-sm leading-relaxed">{report.final_feedback}</p>
        </div>

        {/* Strengths & Weaknesses */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          <div className="bg-[#111113] border border-[#27272A] rounded-[16px] p-6 shadow-xl">
            <h3 className="text-[11px] font-bold text-[#22C55E] uppercase tracking-widest mb-5 flex items-center">
              <span className="w-2 h-2 rounded-full bg-[#22C55E] mr-2" />
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
              <span className="w-2 h-2 rounded-full bg-[#F59E0B] mr-2" />
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

        {/* Question Performance */}
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
                      <div className="report-question-card__label text-[11px] text-[#A1A1AA] font-bold uppercase tracking-wider mb-2">
                        QUESTION {String(idx + 1).padStart(2, '0')}
                      </div>
                      <h4 className="report-question-card__question font-semibold text-sm text-[#FAFAFA] line-clamp-2">
                        {q.question}
                      </h4>
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
          <Link
            to="/"
            className="inline-flex items-center px-8 py-4 bg-[#FAFAFA] text-[#09090B] font-bold text-sm rounded-full hover:bg-white hover:scale-105 transition-all shadow-[0_0_15px_rgba(250,250,250,0.1)]"
          >
            CREATE NEW SCREENING →
          </Link>
        </div>
      </main>
    </div>
  );
}
