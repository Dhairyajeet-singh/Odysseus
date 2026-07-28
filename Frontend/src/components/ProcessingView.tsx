import React, { useEffect, useRef, useState } from 'react';
import { ProcessingLog } from '../types';
import { Cpu, Terminal, CheckCircle2, ShieldAlert } from 'lucide-react';

interface ProcessingViewProps {
  logs: ProcessingLog[];
  onCancel: () => void;
  candidateCount: number;
  /** Resumes finished so far, straight from the backend. */
  completed: number;
}

export const ProcessingView: React.FC<ProcessingViewProps> = ({
  logs,
  onCancel,
  candidateCount,
  completed,
}) => {
  // Progress is now measured, not animated. It was a timer that climbed to 95%
  // in a couple of seconds and sat there — which told the user nothing, and
  // actively misled them on a long batch.
  //
  // The JD is parsed once before any resume is read, so that phase is given a
  // small fixed share and the remaining 90% tracks completed/total exactly.
  const JD_SHARE = 10;
  const progress = candidateCount > 0
    ? Math.min(100, JD_SHARE + Math.round((completed / candidateCount) * (100 - JD_SHARE)))
    : JD_SHARE;

  // Rolling throughput, so the third stat means something instead of counting
  // imaginary "semantic nodes".
  const startedAt = useRef<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 500);
    return () => clearInterval(t);
  }, []);
  const perMin = elapsed > 2 && completed > 0
    ? Math.round((completed / elapsed) * 60) : 0;

  // Keep the newest log line in view without the user scrolling.
  const feedRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [logs.length]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl glass-panel rounded-3xl p-8 sm:p-10 border border-white/10 shadow-2xl space-y-8 text-center">
        
        {/* Animated Circular Progress Indicator */}
        <div className="relative mx-auto flex h-40 w-40 items-center justify-center">
          
          {/* Outer Glowing Ring */}
          <svg className="h-full w-full transform -rotate-90" viewBox="0 0 100 100">
            <circle
              cx="50"
              cy="50"
              r="42"
              className="stroke-slate-800"
              strokeWidth="8"
              fill="transparent"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              className="stroke-blue-500 transition-all duration-300 ease-out"
              strokeWidth="8"
              strokeDasharray="264"
              strokeDashoffset={264 - (264 * progress) / 100}
              strokeLinecap="round"
              fill="transparent"
            />
          </svg>

          {/* Center Brain Icon & Percentage */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <Cpu className="h-8 w-8 text-blue-400 animate-pulse mb-1" />
            <span className="text-2xl font-black text-white">{Math.min(100, progress)}%</span>
            <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Evaluating</span>
          </div>
        </div>

        {/* Title & Status */}
        <div className="space-y-2">
          <h2 className="text-2xl font-extrabold text-white">Ranking Candidates...</h2>
          <p className="text-xs text-slate-300 max-w-md mx-auto">
            Reading each resume, retrieving the evidence for every required skill, and scoring what it finds.
          </p>
        </div>

        {/* Real-time stats row */}
        <div className="grid grid-cols-3 gap-3 border-y border-white/10 py-4 text-center">
          <div>
            <p className="text-xs text-slate-400">Resumes Processed</p>
            <p className="text-lg font-bold text-white">{completed} / {candidateCount}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Throughput</p>
            <p className="text-lg font-bold text-blue-400">{perMin > 0 ? `${perMin}/min` : "—"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Scoring</p>
            <p className="text-lg font-bold text-purple-400">Deterministic</p>
          </div>
        </div>

        {/* Live Processing Terminal Logs */}
        <div className="text-left space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 px-1">
            <span className="flex items-center gap-2 font-mono">
              <Terminal className="h-3.5 w-3.5 text-blue-400" />
              Live Execution Feed
            </span>
            <span className="text-[10px] text-emerald-400 flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
              Active
            </span>
          </div>

          <div ref={feedRef} className="h-36 rounded-2xl bg-black/60 p-4 border border-white/10 overflow-y-auto font-mono text-[11px] space-y-1.5 leading-relaxed">
            {logs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className="text-slate-500 shrink-0">{log.timestamp}</span>
                <span className={
                  log.type === 'success' ? 'text-emerald-400' :
                  log.type === 'warning' ? 'text-amber-400' :
                  log.type === 'error' ? 'text-rose-400' :
                  'text-blue-300'
                }>
                  {log.message}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Cancel option */}
        <button
          onClick={onCancel}
          className="text-xs text-slate-400 hover:text-white transition-colors"
        >
          Cancel Analysis
        </button>

      </div>
    </div>
  );
};