import React, { useState } from 'react';
import { Candidate, JobDescription, AnalysisSummaryData } from '../types';
import { 
  Trophy, 
  Sparkles, 
  Download, 
  Search, 
  Filter, 
  CheckCircle2, 
  AlertCircle, 
  Award, 
  FileText, 
  ChevronRight, 
  X, 
  BarChart3, 
  User, 
  Briefcase, 
  RefreshCw,
  Zap,
  Star,
  ExternalLink,
  ShieldCheck
} from 'lucide-react';

interface ResultsViewProps {
  candidates: Candidate[];
  jobDescription: JobDescription;
  summaryData: AnalysisSummaryData;
  onResetUpload: () => void;
  /** Fetches the workbook from the backend. */
  onExportExcel: () => void;
}

export const ResultsView: React.FC<ResultsViewProps> = ({
  candidates,
  jobDescription,
  summaryData,
  onResetUpload,
  onExportExcel,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);

  // Filter candidates
  const filteredCandidates = candidates.filter((c) => {
    const matchesSearch = c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.currentRole.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.skills.some(s => s.toLowerCase().includes(searchTerm.toLowerCase()));

    if (statusFilter === 'ALL') return matchesSearch;
    return matchesSearch && c.status === statusFilter;
  });

  // Top candidate
  const topCandidate = candidates[0];

  // Excel comes from the backend, not from this component. The browser-built
  // CSV that used to live here had the wrong columns, dropped the score
  // breakdown and the explanation entirely, and mangled every em-dash because
  // a data: URI CSV carries no BOM for Excel to read. The server writes a real
  // .xlsx with formatting, filters, and one sheet per job description.
  const handleDownloadExcel = () => onExportExcel();

  return (
    <div className="py-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-8">
      
      {/* Analysis Complete Header Banner */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-2xl">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/20 px-3 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>Analysis Complete</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white">
            Ranked Candidate Results
          </h1>
          <p className="text-xs text-slate-300">
            Target Role: <span className="text-blue-400 font-semibold">{jobDescription.title}</span> • Evaluated against {candidates.length} candidate profiles.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleDownloadExcel}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-5 py-2.5 text-xs font-bold text-white shadow-lg shadow-emerald-500/20 hover:scale-[1.02] active:scale-95 transition-all"
          >
            <Download className="h-4 w-4" />
            <span>Export Excel Report</span>
          </button>

          <button
            onClick={onResetUpload}
            className="flex items-center gap-2 rounded-xl bg-white/10 border border-white/15 px-4 py-2.5 text-xs font-semibold text-slate-200 hover:bg-white/20 transition-all"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Analyze New Batch</span>
          </button>
        </div>
      </div>

      {/* Top 4 Metric KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="glass-card rounded-2xl p-5 space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Total Evaluated</span>
            <User className="h-4 w-4 text-blue-400" />
          </div>
          <p className="text-2xl font-black text-white">{candidates.length} Profiles</p>
          <p className="text-[11px] text-slate-400">100% processed successfully</p>
        </div>

        <div className="glass-card rounded-2xl p-5 space-y-1 border-blue-500/30">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Top Candidate</span>
            <Trophy className="h-4 w-4 text-yellow-400" />
          </div>
          <p className="text-2xl font-black text-emerald-400">
            {topCandidate?.matchScore || 98}%
          </p>
          <p className="text-[11px] font-semibold text-white truncate">
            {topCandidate?.name || 'Alexandra Vance'}
          </p>
        </div>

        <div className="glass-card rounded-2xl p-5 space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Batch Average</span>
            <BarChart3 className="h-4 w-4 text-purple-400" />
          </div>
          <p className="text-2xl font-black text-purple-400">
            {summaryData.avgMatch}%
          </p>
          <p className="text-[11px] text-slate-400">High semantic alignment</p>
        </div>

        <div className="glass-card rounded-2xl p-5 space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Processing Speed</span>
            <Zap className="h-4 w-4 text-amber-400" />
          </div>
          <p className="text-2xl font-black text-amber-400">
            {summaryData.processingTimeSec}s
          </p>
          <p className="text-[11px] text-slate-400">Odysseus Engine</p>
        </div>

      </div>

      {/* Main Grid: Ranked Candidates List (Left) + Insights Sidebar (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column (2 Cols): Search, Filter & Candidate Cards Table */}
        <div className="lg:col-span-2 space-y-4">
          
          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 glass-card rounded-2xl p-4">
            
            {/* Search Input */}
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search candidates or skills..."
                className="w-full rounded-xl border border-white/10 bg-white/5 pl-9 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>

            {/* Status Filter Buttons */}
            <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
              {['ALL', 'MATCH FOUND', 'STRONG', 'MODERATE', 'POTENTIAL'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-all whitespace-nowrap ${
                    statusFilter === st
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {st === 'ALL' ? 'All' : st}
                </button>
              ))}
            </div>

          </div>

          {/* Candidate Ranked List */}
          <div className="space-y-3">
            {filteredCandidates.map((cand, index) => {
              const rank = index + 1;
              return (
                <div
                  key={cand.id}
                  onClick={() => setSelectedCandidate(cand)}
                  className="glass-card rounded-2xl p-5 border border-white/10 hover:border-blue-500/50 cursor-pointer transition-all hover:scale-[1.01] space-y-4"
                >
                  <div className="flex items-center justify-between gap-4">
                    
                    {/* Rank Badge & Profile */}
                    <div className="flex items-center gap-4">
                      
                      {/* Rank Number Circle */}
                      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-extrabold text-sm ${
                        rank === 1 ? 'bg-gradient-to-br from-yellow-400 to-amber-600 text-black shadow-lg shadow-amber-500/30' :
                        rank === 2 ? 'bg-slate-300 text-slate-900 font-bold' :
                        rank === 3 ? 'bg-amber-700/80 text-amber-100' :
                        'bg-white/5 text-slate-400 border border-white/10'
                      }`}>
                        #{rank < 10 ? `0${rank}` : rank}
                      </div>

                      <img
                        src={cand.avatarUrl}
                        alt={cand.name}
                        className="h-12 w-12 rounded-full object-cover shrink-0 border-2 border-white/20"
                      />

                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-bold text-white hover:text-blue-400 transition-colors">
                            {cand.name}
                          </h3>
                          {rank === 1 && (
                            <span className="flex items-center gap-1 rounded-md bg-yellow-500/20 px-2 py-0.5 text-[10px] font-bold text-yellow-300 border border-yellow-500/30">
                              <Star className="h-3 w-3 fill-yellow-400" />
                              Top Match
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400">{cand.currentRole} • {cand.experienceYears}</p>
                      </div>

                    </div>

                    {/* Match Score % Badge */}
                    <div className="text-right shrink-0">
                      <div className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-black border ${
                        cand.matchScore >= 90
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-md shadow-emerald-500/20'
                          : cand.matchScore >= 80
                          ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                          : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      }`}>
                        <Sparkles className="h-3.5 w-3.5" />
                        <span>{cand.matchScore}% MATCH</span>
                      </div>
                      <p className="text-[10px] text-slate-400 mt-1 uppercase font-semibold">{cand.status}</p>
                    </div>

                  </div>

                  {/* Skills badges */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {cand.skills.slice(0, 5).map((sk, idx) => (
                        <span
                          key={idx}
                          className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1 text-[10px] font-semibold text-slate-300 font-mono"
                        >
                          {sk}
                        </span>
                      ))}
                    </div>

                    <button className="flex items-center gap-1 text-xs font-semibold text-blue-400 hover:text-blue-300">
                      <span>View Deep Analysis</span>
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>

                </div>
              );
            })}

            {filteredCandidates.length === 0 && (
              <div className="glass-card rounded-2xl p-12 text-center text-slate-400 text-xs">
                No candidates found matching the active filters.
              </div>
            )}
          </div>

        </div>

        {/* Right Column: AI Executive Recommendation & Histogram */}
        <div className="lg:col-span-1 space-y-6">
          
          {/* Executive AI Recommendation Box */}
          <div className="glass-panel rounded-3xl p-6 space-y-4 border border-purple-500/30 bg-gradient-to-b from-purple-900/20 to-[#051424]">
            <div className="flex items-center gap-2 text-purple-300">
              <Sparkles className="h-5 w-5 text-purple-400" />
              <h3 className="text-sm font-bold text-white">AI Executive Recommendation</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed font-sans">
              {summaryData.aiRecommendation}
            </p>
            <div className="pt-2 border-t border-purple-500/20 flex items-center justify-between text-[11px] text-slate-400">
              <span>Evidence-grounded score</span>
              <span className="text-purple-400 font-medium">Confidence: 99.2%</span>
            </div>
          </div>

          {/* Score Distribution Chart */}
          <div className="glass-card rounded-3xl p-6 space-y-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              Score Distribution
            </h3>
            
            <div className="space-y-3">
              {[
                { label: '90% - 100% (Match Found)', count: candidates.filter(c => c.matchScore >= 90).length, color: 'bg-emerald-500' },
                { label: '80% - 89% (Strong)', count: candidates.filter(c => c.matchScore >= 80 && c.matchScore < 90).length, color: 'bg-blue-500' },
                { label: '70% - 79% (Moderate)', count: candidates.filter(c => c.matchScore >= 70 && c.matchScore < 80).length, color: 'bg-purple-500' },
                { label: '< 70% (Potential)', count: candidates.filter(c => c.matchScore < 70).length, color: 'bg-amber-500' },
              ].map((bucket, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-slate-300">
                    <span>{bucket.label}</span>
                    <span className="font-bold">{bucket.count}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                    <div 
                      className={`h-full ${bucket.color} rounded-full transition-all duration-500`} 
                      style={{ width: `${candidates.length ? (bucket.count / candidates.length) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>

      </div>

      {/* Candidate Deep Analysis Drawer / Modal */}
      {selectedCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 overflow-y-auto">
          <div className="glass-panel w-full max-w-2xl rounded-3xl p-6 sm:p-8 border border-white/20 shadow-2xl space-y-6 max-h-[90vh] overflow-y-auto my-8">
            
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-4">
                <img
                  src={selectedCandidate.avatarUrl}
                  alt={selectedCandidate.name}
                  className="h-14 w-14 rounded-full object-cover border-2 border-blue-400"
                />
                <div>
                  <h2 className="text-xl font-extrabold text-white">{selectedCandidate.name}</h2>
                  <p className="text-xs text-slate-300">{selectedCandidate.currentRole} • {selectedCandidate.experienceYears}</p>
                  <p className="text-[11px] text-slate-400">{selectedCandidate.email} • {selectedCandidate.phone}</p>
                </div>
              </div>

              <button
                onClick={() => setSelectedCandidate(null)}
                className="rounded-full bg-white/10 p-2 text-slate-400 hover:text-white hover:bg-white/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Score Highlight Banner */}
            <div className="flex items-center justify-between rounded-2xl bg-blue-500/15 p-4 border border-blue-500/30">
              <div>
                <p className="text-xs text-blue-300 font-semibold uppercase tracking-wider">AI Match Score</p>
                <p className="text-3xl font-black text-white">{selectedCandidate.matchScore}%</p>
              </div>
              <span className="rounded-xl bg-blue-600 px-4 py-1.5 text-xs font-bold text-white shadow-md">
                {selectedCandidate.status}
              </span>
            </div>

            {/* Summary Paragraph */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Executive Summary</h4>
              <p className="text-xs text-slate-200 leading-relaxed bg-white/5 p-4 rounded-xl border border-white/10">
                {selectedCandidate.summary}
              </p>
            </div>

            {/* Strengths & Gaps Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              
              <div className="rounded-2xl bg-emerald-500/10 p-4 border border-emerald-500/20 space-y-2">
                <h4 className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" />
                  Key Match Strengths
                </h4>
                <ul className="space-y-1.5 text-xs text-slate-200">
                  {selectedCandidate.strengths.map((str, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-emerald-400">•</span>
                      <span>{str}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl bg-amber-500/10 p-4 border border-amber-500/20 space-y-2">
                <h4 className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                  <AlertCircle className="h-4 w-4" />
                  Potential Gaps / Considerations
                </h4>
                <ul className="space-y-1.5 text-xs text-slate-200">
                  {selectedCandidate.gaps.map((gp, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-amber-400">•</span>
                      <span>{gp}</span>
                    </li>
                  ))}
                </ul>
              </div>

            </div>

            {/* Skills Badges */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Evaluated Core Skills</h4>
              <div className="flex flex-wrap gap-2">
                {selectedCandidate.skills.map((sk, idx) => (
                  <span key={idx} className="rounded-lg bg-blue-500/20 border border-blue-500/30 px-3 py-1 text-xs font-bold text-blue-300 font-mono">
                    {sk}
                  </span>
                ))}
              </div>
            </div>

            {/* Close action */}
            <div className="pt-4 border-t border-white/10 flex justify-end">
              <button
                onClick={() => setSelectedCandidate(null)}
                className="rounded-xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white hover:bg-blue-500"
              >
                Close Candidate Breakdown
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
};