import React, { useState } from 'react';
import { Candidate, JobDescription } from '../types';
import { SAMPLE_JOB_DESCRIPTION } from '../data/sampleData';
import { 
  Upload, 
  FileText, 
  Trash2, 
  Plus, 
  CheckCircle2, 
  Sparkles, 
  Clock, 
  Cpu, 
  AlertCircle,
  FileCheck,
  RefreshCw,
  FolderPlus
} from 'lucide-react';

interface UploadViewProps {
  jobDescription: JobDescription;
  setJobDescription: React.Dispatch<React.SetStateAction<JobDescription>>;
  candidates: Candidate[];
  setCandidates: React.Dispatch<React.SetStateAction<Candidate[]>>;
  /** The actual uploaded files. These are what get posted to the backend --
   *  the Candidate entries above exist only to render the queue. */
  resumeFiles: File[];
  setResumeFiles: React.Dispatch<React.SetStateAction<File[]>>;
  onAnalyze: () => void;
}

/** Initials avatar as a data URI, so a queued row has something to show
 *  without fetching a photo of an unrelated person from the internet. */
const initialsAvatar = (name: string): string => {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2)
    .map(w => w[0]).join('').toUpperCase() || '?';
  const hue = Array.from(name).reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">` +
    `<rect width="96" height="96" rx="48" fill="hsl(${hue},45%,32%)"/>` +
    `<text x="48" y="62" font-family="Arial,sans-serif" font-size="36" ` +
    `font-weight="600" fill="#e2e8f0" text-anchor="middle">${initials}</text></svg>`;
  return 'data:image/svg+xml;base64,' + btoa(svg);
};

export const UploadView: React.FC<UploadViewProps> = ({
  jobDescription,
  setJobDescription,
  candidates,
  setCandidates,
  resumeFiles,
  setResumeFiles,
  onAnalyze,
}) => {
  const [jdText, setJdText] = useState<string>(jobDescription.requirementsText);
  const [jdTitle, setJdTitle] = useState<string>(jobDescription.title);
  const [dragActiveJd, setDragActiveJd] = useState(false);
  const [dragActiveCandidate, setDragActiveCandidate] = useState(false);
  const [newCandidateName, setNewCandidateName] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);

  // Loads the sample JOB DESCRIPTION only. The sample candidates cannot be
  // loaded any more: there are no files behind them, and the backend screens
  // real documents rather than the placeholder text they carried.
  const handleLoadSample = () => {
    setJobDescription(SAMPLE_JOB_DESCRIPTION);
    setJdTitle(SAMPLE_JOB_DESCRIPTION.title);
    setJdText(SAMPLE_JOB_DESCRIPTION.requirementsText);
  };

  // Keep the real File objects. Everything the queue displays is derived from
  // the filename and is explicitly provisional -- no invented skills, no
  // invented score. The backend reads the actual document and fills these in.
  const handleCandidateFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;

    const picked = Array.from(e.target.files).filter(f =>
      /\.(pdf|docx?|DOCX?|PDF)$/.test(f.name));

    const alreadyQueued = new Set(resumeFiles.map(f => `${f.name}:${f.size}`));
    const fresh = picked.filter(f => !alreadyQueued.has(`${f.name}:${f.size}`));

    const stubs: Candidate[] = fresh.map((file, idx) => {
      const cleanName = file.name.replace(/\.[^/.]+$/, '').replace(/[_-]+/g, ' ');
      return {
        id: `file-${file.name}-${file.size}-${idx}`,
        name: cleanName || file.name,
        currentRole: 'Queued',
        matchScore: 0,
        skills: [],
        experienceYears: '—',
        status: 'POTENTIAL',
        summary: 'Queued. Not yet screened.',
        strengths: [],
        gaps: [],
        fileName: file.name,
        avatarUrl: initialsAvatar(cleanName || file.name),
      };
    });

    setResumeFiles(prev => [...prev, ...fresh]);
    setCandidates(prev => [...prev, ...stubs]);
    e.target.value = '';   // so picking the same file again still fires onChange
  };

  // Removing a row must drop the underlying File too, or the backend would
  // still receive a resume the user thought they had deleted.
  const handleDeleteCandidate = (id: string) => {
    const target = candidates.find(c => c.id === id);
    setCandidates(prev => prev.filter(c => c.id !== id));
    if (target) {
      setResumeFiles(prev => {
        const at = prev.findIndex(f => f.name === target.fileName);
        return at === -1 ? prev : prev.filter((_, i) => i !== at);
      });
    }
  };

  // A candidate with no document behind it cannot be screened, so this path is
  // closed rather than left to fail later with a confusing error.
  const handleAddManualCandidate = () => {
    if (!newCandidateName.trim()) return;
    alert('Add the candidate\u2019s resume file instead \u2014 screening reads the '
        + 'actual document, so a name on its own cannot be evaluated.');
    setNewCandidateName('');
    setShowAddModal(false);
    return;
    const newCand: Candidate = {
      id: `cand-manual-${Date.now()}`,
      name: newCandidateName,
      currentRole: 'Senior Developer',
      matchScore: 85,
      skills: ['JAVASCRIPT', 'REACT', 'NODE', 'SQL'],
      experienceYears: '7 Yrs',
      status: 'STRONG',
      summary: `Manually added profile for ${newCandidateName}. Ready for ranking.`,
      strengths: ['Custom applicant record initialized'],
      gaps: ['Pending AI evaluation'],
      fileName: `${newCandidateName.replace(/\s+/g, '_')}_Resume.pdf`,
      avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80'
    };
    setCandidates(prev => [...prev, newCand]);
    setNewCandidateName('');
    setShowAddModal(false);
  };

  const updateJdState = (newTitle: string, newText: string) => {
    setJdTitle(newTitle);
    setJdText(newText);
    setJobDescription(prev => ({
      ...prev,
      title: newTitle,
      requirementsText: newText
    }));
  };

  return (
    <div className="py-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-8">
      
      {/* Top Title & Preset Actions Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-3">
            <Upload className="h-7 w-7 text-blue-400" />
            Upload Workspace
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Provide the target job description and upload candidate resumes to run the screening pipeline.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleLoadSample}
            className="flex items-center gap-2 rounded-xl bg-blue-500/20 px-4 py-2 text-xs font-semibold text-blue-300 border border-blue-500/30 hover:bg-blue-500/30 transition-all shadow-sm"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Load Sample Job Description</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left 2 Columns: JD Upload & Resumes Dropzone */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* STEP 1: JOB DESCRIPTION */}
          <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                  1
                </span>
                <h2 className="text-lg font-bold text-white">Job Description</h2>
              </div>
              <span className="text-[11px] text-blue-400 font-medium">Step 1 of 2</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Position / Role Title
                </label>
                <input
                  type="text"
                  value={jdTitle}
                  onChange={(e) => updateJdState(e.target.value, jdText)}
                  placeholder="e.g. Senior Technical Lead / Fullstack Architect"
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Job Requirements & Key Qualifications
                </label>
                <textarea
                  rows={5}
                  value={jdText}
                  onChange={(e) => updateJdState(jdTitle, e.target.value)}
                  placeholder="Paste job description requirements, technical stack (React, Node, AWS, etc.), and minimum experience..."
                  className="w-full rounded-xl border border-white/10 bg-white/5 p-4 text-xs text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono leading-relaxed"
                />
              </div>
            </div>
          </div>

          {/* STEP 2: CANDIDATE RESUMES UPLOAD */}
          <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-purple-600 text-xs font-bold text-white">
                  2
                </span>
                <h2 className="text-lg font-bold text-white">Candidate Resumes Batch</h2>
              </div>
              <span className="text-xs text-slate-400">{resumeFiles.length} Files Ready</span>
            </div>

            {/* Dropzone area */}
            <div className="relative rounded-2xl border-2 border-dashed border-white/20 bg-white/5 p-8 text-center transition-all hover:border-blue-400 hover:bg-blue-500/5">
              <input
                type="file"
                multiple
                accept=".pdf,.txt,.doc,.docx"
                onChange={handleCandidateFileUpload}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <div className="flex flex-col items-center justify-center space-y-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/20 text-blue-400">
                  <FolderPlus className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs font-bold text-white">
                    Drag & Drop candidate resumes here, or <span className="text-blue-400 underline">Browse Files</span>
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Supports PDF, DOCX, TXT format files (up to 20MB each)
                  </p>
                </div>
              </div>
            </div>

            {/* Uploaded candidate list */}
            {candidates.length > 0 && (
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between text-xs text-slate-400 px-1">
                  <span>Candidate Files Queue ({candidates.length})</span>
                  <button 
                    onClick={() => setCandidates([])}
                    className="text-red-400 hover:underline text-[11px]"
                  >
                    Clear All
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-80 overflow-y-auto pr-1">
                  {candidates.map((cand) => (
                    <div 
                      key={cand.id} 
                      className="glass-card rounded-xl p-3.5 flex items-center justify-between border border-white/10 hover:border-blue-500/40"
                    >
                      <div className="flex items-center gap-3 overflow-hidden">
                        <img 
                          src={cand.avatarUrl} 
                          alt={cand.name} 
                          className="h-9 w-9 rounded-full object-cover shrink-0 border border-white/20"
                        />
                        <div className="truncate">
                          <p className="text-xs font-bold text-white truncate">{cand.name}</p>
                          <p className="text-[10px] text-slate-400 truncate">{cand.fileName}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className="flex items-center gap-1 rounded-md bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/30">
                          <FileCheck className="h-3 w-3" />
                          Ready
                        </span>
                        <button
                          onClick={() => handleDeleteCandidate(cand.id)}
                          className="p-1 rounded-lg text-slate-400 hover:text-red-400 hover:bg-white/10 transition-all"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick manual candidate modal button */}
            <div className="pt-2 border-t border-white/10 flex justify-end">
              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300 font-medium"
              >
                <Plus className="h-4 w-4" />
                Add candidate manually
              </button>
            </div>

          </div>

        </div>

        {/* Right Column: Analysis Summary Panel */}
        <div className="lg:col-span-1">
          <div className="sticky top-24 glass-panel rounded-3xl p-6 space-y-6 border border-white/10 shadow-2xl">
            
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
                <Cpu className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Analysis Summary</h3>
                <p className="text-[11px] text-slate-400">Odysseus Pipeline</p>
              </div>
            </div>

            {/* Metric Rows */}
            <div className="space-y-4">
              
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Target Role:</span>
                <span className="font-semibold text-white max-w-[160px] truncate text-right">
                  {jdTitle || 'Not specified'}
                </span>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Total Resumes Queue:</span>
                <span className="font-bold text-blue-400 text-sm">{candidates.length} Files</span>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Est. Processing Time:</span>
                <span className="font-semibold text-white flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5 text-slate-400" />
                  ~ 2-3 Seconds
                </span>
              </div>

              {/* AI Credits Progress Bar */}
              <div className="rounded-2xl bg-white/5 p-3.5 border border-white/10 space-y-2">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-300 font-medium flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                    AI Tokens Available
                  </span>
                  <span className="font-bold text-purple-300">4,850 / 5,000</span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div className="h-full w-[94%] bg-gradient-to-r from-blue-500 to-purple-500 rounded-full" />
                </div>
              </div>

            </div>

            {/* Warning if no candidates */}
            {candidates.length === 0 && (
              <div className="flex items-center gap-2 rounded-xl bg-amber-500/10 p-3 border border-amber-500/20 text-amber-300 text-xs">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>Please upload or load at least 1 candidate resume to start ranking.</span>
              </div>
            )}

            {/* Primary Action Button */}
            <button
              disabled={candidates.length === 0 || !jdText.trim()}
              onClick={onAnalyze}
              className={`w-full flex items-center justify-center gap-3 rounded-2xl py-4 text-sm font-bold text-white transition-all shadow-xl ${
                candidates.length > 0 && jdText.trim()
                  ? 'bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 hover:scale-[1.02] active:scale-95 primary-glow'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed opacity-60'
              }`}
            >
              <Sparkles className="h-5 w-5" />
              <span>Analyze & Rank Resumes</span>
            </button>

            <p className="text-[10px] text-center text-slate-300 leading-relaxed">
              Resumes are processed server-side and discarded after the run, without storing personal data.
            </p>

          </div>
        </div>

      </div>

      {/* Manual Candidate Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="glass-panel w-full max-w-md rounded-3xl p-6 border border-white/20 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-white">Add Candidate Profile</h3>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Candidate Full Name
              </label>
              <input
                type="text"
                value={newCandidateName}
                onChange={(e) => setNewCandidateName(e.target.value)}
                placeholder="e.g. Samantha Wright"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleAddManualCandidate}
                className="rounded-xl bg-blue-600 px-5 py-2 text-xs font-semibold text-white hover:bg-blue-500"
              >
                Add Candidate
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};