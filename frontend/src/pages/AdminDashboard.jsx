import React, { useEffect, useMemo, useState } from 'react';
import { api, apiBaseUrl } from '../api';

const defaults = { domain: 'Artificial Intelligence / Machine Learning', role: 'AI/ML Engineer', difficulty: 'Intermediate', topics: 'Python, Machine Learning, NLP', numQuestions: 3 };

export default function AdminDashboard() {
  const [key, setKey] = useState(() => localStorage.getItem('interviewos_admin_key') || '');
  const [interviews, setInterviews] = useState([]);
  const [form, setForm] = useState({ ...defaults, candidateName: '', candidateEmail: '', scheduledAt: '' });
  const [error, setError] = useState('');
  const [invite, setInvite] = useState('');
  const headers = useMemo(() => ({ 'X-Admin-Key': key }), [key]);

  const load = async () => {
    if (!key) return;
    try { const result = await api.get('/api/admin/interviews', { headers }); setInterviews(result.data); setError(''); }
    catch (e) { setError(e.response?.data?.detail || 'Enter the correct admin access key.'); }
  };
  useEffect(() => { load(); }, []); // intentional: initial page should not make a request without a key
  const saveKey = () => { localStorage.setItem('interviewos_admin_key', key); load(); };
  const submit = async (event) => {
    event.preventDefault(); setError(''); setInvite('');
    try {
      const response = await api.post('/api/admin/interviews', {
        candidate_name: form.candidateName, candidate_email: form.candidateEmail,
        scheduled_at: new Date(form.scheduledAt).toISOString(),
        setup: { domain: form.domain, role: form.role, difficulty: form.difficulty, topics: form.topics.split(',').map(x => x.trim()).filter(Boolean), num_questions: Number(form.numQuestions) },
      }, { headers });
      const url = `${window.location.origin}/invite/${response.data.invite_token}`;
      setInvite(url); setForm({ ...defaults, candidateName: '', candidateEmail: '', scheduledAt: '' }); await load();
    } catch (e) { setError(e.response?.data?.detail || 'Could not schedule the interview.'); }
  };
  return <main className="min-h-screen bg-slate-950 text-slate-100 p-5 md:p-10 font-sans">
    <header className="max-w-6xl mx-auto flex flex-wrap gap-4 justify-between items-center mb-8"><div><p className="text-indigo-400 text-xs font-bold tracking-widest">INTERVIEWOS ADMIN</p><h1 className="text-3xl font-bold">Candidate interviews</h1></div><div className="flex gap-2"><input className="rounded-lg bg-slate-800 border border-slate-700 p-2 text-sm" placeholder="Admin access key" value={key} onChange={e => setKey(e.target.value)} /><button onClick={saveKey} className="rounded-lg bg-indigo-600 px-4 font-bold">Unlock</button></div></header>
    <div className="max-w-6xl mx-auto grid lg:grid-cols-[380px_1fr] gap-6">
      <form onSubmit={submit} className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-3 h-fit"><h2 className="text-xl font-bold">Schedule an interview</h2>
        {[['candidateName','Candidate name'],['candidateEmail','Candidate email'],['scheduledAt','Date and time','datetime-local'],['role','Role'],['domain','Domain'],['topics','Focus areas (comma separated)']].map(([name,label,type]) => <label className="block text-sm text-slate-300" key={name}>{label}<input required type={type || 'text'} className="w-full mt-1 rounded-lg bg-slate-800 border border-slate-700 p-2 text-white" value={form[name]} onChange={e => setForm({...form,[name]:e.target.value})}/></label>)}
        <div className="grid grid-cols-2 gap-3"><label className="text-sm">Difficulty<select className="w-full mt-1 rounded-lg bg-slate-800 p-2" value={form.difficulty} onChange={e=>setForm({...form,difficulty:e.target.value})}><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select></label><label className="text-sm">Questions<select className="w-full mt-1 rounded-lg bg-slate-800 p-2" value={form.numQuestions} onChange={e=>setForm({...form,numQuestions:e.target.value})}>{[3,5,7,10].map(n=><option key={n}>{n}</option>)}</select></label></div>
        <button className="w-full rounded-lg bg-cyan-500 text-slate-950 p-3 font-bold">Create unique link</button></form>
      <section className="rounded-2xl bg-slate-900 border border-slate-800 p-6 overflow-auto"><h2 className="text-xl font-bold mb-4">Scheduled candidates</h2>{error && <p className="text-rose-400 mb-4">{error}</p>}{invite && <div className="mb-5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3"><p className="text-emerald-300 text-sm mb-1">Unique candidate link created</p><div className="flex gap-2"><input className="flex-1 bg-slate-950 rounded p-2 text-xs" readOnly value={invite}/><button type="button" className="bg-emerald-500 text-slate-950 px-3 rounded font-bold" onClick={()=>navigator.clipboard.writeText(invite)}>Copy</button></div></div>}
        <div className="space-y-3">{interviews.length === 0 ? <p className="text-slate-400">No scheduled interviews yet.</p> : interviews.map(item => <article key={item.id} className="rounded-xl border border-slate-800 p-4"><div className="flex justify-between gap-3"><div><b>{item.candidate_name}</b><p className="text-sm text-slate-400">{item.candidate_email} · {item.setup.role}</p><p className="text-xs text-slate-500 mt-1">{new Date(item.scheduled_at).toLocaleString()}</p></div><span className="h-fit rounded-full bg-indigo-500/15 text-indigo-300 px-2 py-1 text-xs">{item.status}</span></div>{item.report && <div className="mt-3 text-sm"><b>Score: {item.report.overall_score}/100</b><p className="text-slate-400">{item.report.recommendation}</p></div>}</article>)}</div>
      </section></div></main>;
}
