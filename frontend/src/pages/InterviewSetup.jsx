import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function InterviewSetup() {
  const [domain, setDomain]         = useState('');
  const [role, setRole]             = useState('');
  const [difficulty, setDifficulty] = useState('Intermediate');
  const [topicInput, setTopicInput] = useState('');
  const [topics, setTopics]         = useState([]);
  const [numQuestions, setNumQuestions] = useState(5);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState('');
  const navigate = useNavigate();

  const start = async (event) => {
    event.preventDefault();
    if (!domain.trim() || !role.trim()) {
      setError('Enter both a domain or industry and the target role to create a tailored screening.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/api/interview/session', {
        domain: domain.trim(),
        role: role.trim(),
        difficulty,
        topics,
        num_questions: numQuestions,
      });
      navigate(`/room?session_id=${response.data.id}`);
    } catch (err) {
      console.error(err);
      setError('We could not create this screening. Check that the interview service is running and try again.');
    } finally {
      setLoading(false);
    }
  };

  const addTopic = (event) => {
    if (event.key === 'Enter' && topicInput.trim()) {
      event.preventDefault();
      if (!topics.includes(topicInput.trim())) {
        setTopics([...topics, topicInput.trim()]);
      }
      setTopicInput('');
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><span className="brand-mark">✦</span>InterviewOS</div>
        <div className="status-chip"><span className="status-dot" /> AI screening ready</div>
      </header>
      <main className="setup-main">
        <section className="setup-hero">
          <div className="eyebrow">AI-powered candidate screening</div>
          <h1>Screen candidates.<br />Faster. Smarter.</h1>
          <p>Create a role-specific voice screening for any industry. Interview questions adapt to the job, its core skills, and the focus areas you choose.</p>
        </section>
        <div className="setup-layout">
          <form className="surface config-card" onSubmit={start}>
            <h2 className="card-title">Screening configuration</h2>
            <p className="card-subtitle">Set the industry and role. We’ll tailor the interview to that work.</p>
            <div className="config-grid">
              <label className="field">
                <span className="field-label">Domain</span>
                <input className="field-input" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="e.g. Healthcare, Finance, Retail, Education" required aria-label="Industry or domain" />
              </label>
              <label className="field">
                <span className="field-label">Target role</span>
                <input className="field-input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Registered Nurse, Sales Manager, Product Designer" required aria-label="Target role" />
              </label>
              <div className="field field-wide">
                <span className="field-label">Interview difficulty</span>
                <div className="choice-row">
                  {['Beginner', 'Intermediate', 'Advanced'].map((level) => (
                    <button
                      type="button"
                      key={level}
                      onClick={() => setDifficulty(level)}
                      className={`choice ${difficulty === level ? 'selected' : ''}`}
                      aria-pressed={difficulty === level}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              </div>
              <div className="field field-wide">
                <span className="field-label">Focus areas</span>
                <div className="topic-box">
                  {topics.map((topic) => (
                    <span className="topic-pill" key={topic}>
                      {topic}
                      <button
                        type="button"
                        aria-label={`Remove ${topic}`}
                        onClick={() => setTopics(topics.filter((item) => item !== topic))}
                      >×</button>
                    </span>
                  ))}
                  <input
                    className="topic-input"
                    value={topicInput}
                    onChange={(e) => setTopicInput(e.target.value)}
                    onKeyDown={addTopic}
                    placeholder="Optional: add a skill or focus area, then press Enter"
                    aria-label="Add a screening focus area"
                  />
                </div>
              </div>
              <div className="field field-wide">
                <span className="field-label">Number of questions</span>
                <div className="choice-row">
                  {[3, 5, 7, 10].map((count) => (
                    <button
                      type="button"
                      key={count}
                      className={`choice ${numQuestions === count ? 'selected' : ''}`}
                      onClick={() => setNumQuestions(count)}
                      aria-pressed={numQuestions === count}
                    >
                      {count} questions
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {error && <p role="alert" style={{ color: '#b91c61', fontSize: 13, margin: '22px 0 0' }}>{error}</p>}
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? 'Creating screening…' : 'Create AI screening'}
            </button>
          </form>
          <aside className="surface summary-card">
            <div className="summary-kicker">Screening brief</div>
            <h2 className="summary-role">{role || 'Your target role'}</h2>
            <div className="summary-domain">{domain || 'Choose any industry or field'}</div>
            <div className="summary-row"><span>Difficulty</span><b>{difficulty}</b></div>
            <div className="summary-row"><span>Questions</span><b>{numQuestions}</b></div>
            <div className="summary-row"><span>Focus</span><b>{topics.length ? `${topics.length} areas` : 'AI-tailored'}</b></div>
            <div className="summary-row"><span>Format</span><b>Role-based interview</b></div>
          </aside>
        </div>
      </main>
    </div>
  );
}
