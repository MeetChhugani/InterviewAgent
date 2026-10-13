import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import InterviewSetup from './pages/InterviewSetup';
import InterviewRoom from './pages/InterviewRoom';
import InterviewReport from './pages/InterviewReport';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InterviewSetup />} />
        <Route path="/room" element={<InterviewRoom />} />
        <Route path="/report" element={<InterviewReport />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
