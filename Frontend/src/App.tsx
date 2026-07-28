import React, { useEffect, useRef, useState } from 'react';
import { AppScreen, Candidate, JobDescription, ProcessingLog, AnalysisSummaryData } from './types';
import { SAMPLE_JOB_DESCRIPTION } from './data/sampleData';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { LandingView } from './components/LandingView';
import { UploadView } from './components/UploadView';
import { ProcessingView } from './components/ProcessingView';
import { ResultsView } from './components/ResultsView';

const EMPTY_SUMMARY: AnalysisSummaryData = {
  totalResumes: 0,
  topScore: 0,
  avgMatch: 0,
  processingTimeSec: 0,
  aiRecommendation: '',
  scoreDistribution: [],
};

/** How often to ask the backend for progress while a job runs. */
const POLL_MS = 900;

export function App() {
  const [currentScreen, setCurrentScreen] = useState<AppScreen>('landing');
  const [activeTab, setActiveTab] = useState('ranking');
  const [jobDescription, setJobDescription] = useState<JobDescription>(SAMPLE_JOB_DESCRIPTION);

  // Candidates start empty. They used to be seeded with sample data, which
  // meant the results screen showed six fictional people before anything had
  // been screened. Everything here now comes from the backend.
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [resumeFiles, setResumeFiles] = useState<File[]>([]);
  const [logs, setLogs] = useState<ProcessingLog[]>([]);
  const [summaryData, setSummaryData] = useState<AnalysisSummaryData>(EMPTY_SUMMARY);
  const [jobId, setJobId] = useState<string | null>(null);
  // Resumes finished so far, reported by the backend on every poll. This is
  // what drives the progress ring — nothing is simulated.
  const [completed, setCompleted] = useState(0);

  const pollTimer = useRef<number | null>(null);
  const cancelled = useRef(false);

  useEffect(() => () => {
    if (pollTimer.current) window.clearTimeout(pollTimer.current);
  }, []);

  const addLog = (message: string, type: ProcessingLog['type'] = 'info') =>
    setLogs(prev => [...prev, {
      timestamp: new Date().toLocaleTimeString(),
      message,
      type,
    }]);

  const handleStartAnalysis = async () => {
    if (resumeFiles.length === 0) {
      alert('Add at least one resume (PDF or DOCX) before running the analysis.');
      return;
    }
    if (!jobDescription.requirementsText.trim()) {
      alert('Add the job description text before running the analysis.');
      return;
    }

    cancelled.current = false;
    setLogs([]);
    setCompleted(0);
    setCurrentScreen('processing');
    addLog(`Uploading ${resumeFiles.length} resume(s)...`);

    const form = new FormData();
    form.append('jd_text', jobDescription.requirementsText);
    form.append('workers', '8');
    resumeFiles.forEach(file => form.append('resumes', file, file.name));

    let id: string;
    try {
      const res = await fetch('/api/jobs', { method: 'POST', body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status})`);
      id = body.jobId;
      setJobId(id);
      addLog(`Job ${id} accepted — ${body.total} file(s) received`, 'success');
    } catch (err: any) {
      addLog(err?.message || 'Could not reach the backend.', 'error');
      addLog('Check that the API is running: uvicorn app:app --port 8000', 'error');
      return;
    }

    // Poll rather than hold the request open: screening 200 resumes takes
    // minutes, and `logsFrom` means each poll only carries lines we have not
    // already displayed.
    let logsSeen = 0;
    const poll = async () => {
      if (cancelled.current) return;
      try {
        const res = await fetch(`/api/jobs/${id}?logs_from=${logsSeen}`);
        if (!res.ok) throw new Error(`Status check failed (${res.status})`);
        const s = await res.json();

        setCompleted(s.completed ?? 0);

        if (s.logs?.length) {
          setLogs(prev => [...prev, ...s.logs.map((l: any) => ({
            timestamp: l.timestamp,
            message: l.message,
            type: l.type as ProcessingLog['type'],
          }))]);
          logsSeen = s.logsTotal;
        }

        if (s.status === 'done') {
          applyResult(s.result);
          setCurrentScreen('results');
          return;
        }
        if (s.status === 'error' || s.status === 'cancelled') {
          addLog(s.error || `Job ${s.status}.`, 'error');
          return;
        }
        pollTimer.current = window.setTimeout(poll, POLL_MS);
      } catch (err: any) {
        addLog(err?.message || 'Lost contact with the backend.', 'error');
      }
    };
    poll();
  };

  const applyResult = (result: any) => {
    const ranked: Candidate[] = result.candidates ?? [];
    setCandidates(ranked);
    setJobDescription(prev => ({
      ...prev,
      title: result.jobTitle || prev.title,
      minYearsExp: result.requirements?.minYearsExperience ?? prev.minYearsExp,
    }));
    setSummaryData(result.summary ?? EMPTY_SUMMARY);
  };

  const handleCancel = async () => {
    cancelled.current = true;
    if (pollTimer.current) window.clearTimeout(pollTimer.current);
    if (jobId) {
      try {
        await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      } catch {
        /* the run is being abandoned anyway */
      }
    }
    setCurrentScreen('upload');
  };

  const handleDownloadExcel = () => {
    if (jobId) window.open(`/api/jobs/${jobId}/excel`, '_blank');
  };

  return (
    <div className="min-h-screen bg-[#051424] text-slate-100 flex flex-col font-sans">

      <Navbar
        currentScreen={currentScreen}
        onNavigate={(screen) => setCurrentScreen(screen)}
        candidateCount={candidates.length}
      />

      <div className="flex-1 flex">

        {currentScreen === 'results' && (
          <Sidebar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            candidateCount={candidates.length}
          />
        )}

        <main className="flex-1">
          {currentScreen === 'landing' && (
            <LandingView onStart={(screen) => setCurrentScreen(screen)} />
          )}

          {currentScreen === 'upload' && (
            <UploadView
              jobDescription={jobDescription}
              setJobDescription={setJobDescription}
              candidates={candidates}
              setCandidates={setCandidates}
              resumeFiles={resumeFiles}
              setResumeFiles={setResumeFiles}
              onAnalyze={handleStartAnalysis}
            />
          )}

          {currentScreen === 'processing' && (
            <ProcessingView
              logs={logs}
              onCancel={handleCancel}
              candidateCount={resumeFiles.length}
              completed={completed}
            />
          )}

          {currentScreen === 'results' && (
            <ResultsView
              candidates={candidates}
              jobDescription={jobDescription}
              summaryData={summaryData}
              onResetUpload={() => setCurrentScreen('upload')}
              onExportExcel={handleDownloadExcel}
            />
          )}
        </main>

      </div>

    </div>
  );
}

export default App;