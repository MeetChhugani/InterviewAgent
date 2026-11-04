import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import PrivateAccess from './pages/PrivateAccess';
import InterviewRoom from './pages/InterviewRoom';
import InterviewReport from './pages/InterviewReport';
import AdminDashboard from './pages/AdminDashboard';
import CandidateInvite from './pages/CandidateInvite';
import SharedReport from './pages/SharedReport';
import HrLogin from './pages/HrLogin';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HrLogin />} />
        <Route path="/room" element={<InterviewRoom />} />
        <Route path="/report" element={<InterviewReport />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/invite/:token" element={<CandidateInvite />} />
        <Route path="/shared-report/:token" element={<SharedReport />} />
        <Route path="/hr-login" element={<HrLogin />} />
        <Route path="/private" element={<PrivateAccess />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
