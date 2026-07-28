import React from 'react';
import { AppScreen } from '../types';
import { 
  ArrowRight, 
  Sparkles, 
  Brain, 
  Zap, 
  ShieldCheck, 
  CheckCircle2, 
  FileText, 
  BarChart2, 
  Layers, 
  Award,
  Download,
  Users
} from 'lucide-react';

interface LandingViewProps {
  onStart: (screen: AppScreen) => void;
}

export const LandingView: React.FC<LandingViewProps> = ({ onStart }) => {
  return (
    <div className="min-h-screen bg-[#051424] text-slate-100 overflow-hidden">
      
      {/* Background Radial Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[500px] bg-gradient-to-b from-blue-600/15 via-purple-600/10 to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Hero Section */}
      <section className="relative pt-12 pb-20 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center">
        
        {/* Release Tag Pill */}
        <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-4 py-1.5 text-xs font-semibold text-blue-300 backdrop-blur-md mb-8 shadow-inner shadow-blue-500/20">
          <Sparkles className="h-3.5 w-3.5 text-blue-400" />
          <span>Odysseus — “of many devices”</span>
        </div>

        {/* Main Hero Title */}
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white max-w-5xl mx-auto leading-[1.15]">
          Find the Best Candidate <br />
          <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent drop-shadow-lg">
            in Seconds.
          </span>
        </h1>

        {/* Hero Subtitle */}
        <p className="mt-6 text-base sm:text-xl text-slate-300 max-w-3xl mx-auto leading-relaxed">
          Upload your job description and candidate resumes to instantly receive AI-powered rankings, semantic skill gap evaluations, and verified interview recommendations.
        </p>

        {/* Call to Action Buttons */}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <button
            onClick={() => onStart('upload')}
            className="w-full sm:w-auto flex items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 px-8 py-4 text-base font-semibold text-white shadow-xl shadow-blue-500/30 transition-all hover:scale-105 active:scale-95 primary-glow"
          >
            <span>Start Ranking Resumes</span>
            <ArrowRight className="h-5 w-5" />
          </button>

          <button
            onClick={() => onStart('results')}
            className="w-full sm:w-auto flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/5 px-8 py-4 text-base font-semibold text-slate-200 transition-all hover:bg-white/10 hover:border-white/25"
          >
            <BarChart2 className="h-5 w-5 text-blue-400" />
            <span>View Sample Rankings</span>
          </button>
        </div>

        {/* Hero 3D Graphic & Floating Badges */}
        <div className="relative mt-16 max-w-4xl mx-auto">
          
          {/* Glass Hero Stage Container */}
          <div className="relative rounded-3xl border border-white/10 bg-gradient-to-b from-white/10 via-white/5 to-transparent p-8 sm:p-12 backdrop-blur-2xl shadow-2xl overflow-hidden">
            
            <div className="flex flex-col md:flex-row items-center justify-around gap-8">
              
              {/* Floating candidate sample badge left */}
              <div className="hidden md:block absolute top-12 left-8 glass-card rounded-2xl p-4 text-left w-56 shadow-xl border border-emerald-500/30 float-animation" style={{ animationDelay: '0s' }}>
                <div className="flex items-center gap-3">
                  <img 
                    src="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=100&auto=format&fit=crop&q=80" 
                    alt="Alexandra Vance" 
                    className="h-10 w-10 rounded-full object-cover border border-emerald-400"
                  />
                  <div>
                    <p className="text-xs font-bold text-white">Alexandra Vance</p>
                    <p className="text-[10px] text-slate-400">Lead Architect</p>
                  </div>
                </div>
                <div className="mt-2.5 flex items-center justify-between border-t border-white/10 pt-2">
                  <span className="text-[10px] text-slate-400">AI Match Score</span>
                  <span className="text-xs font-black text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-md border border-emerald-500/30">
                    98% MATCH
                  </span>
                </div>
              </div>

              {/* Central 3D AI Brain Graphic */}
              <div className="relative flex items-center justify-center py-6">
                <div className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-purple-500/30 rounded-full blur-3xl animate-pulse" />
                <div className="relative flex h-48 w-48 sm:h-56 sm:w-56 items-center justify-center rounded-full border-2 border-blue-400/30 bg-gradient-to-br from-blue-900/60 via-indigo-950/80 to-[#051424] p-6 shadow-2xl shadow-blue-500/40">
                  <Brain className="h-28 w-28 text-blue-400 animate-pulse" />
                  <div className="absolute -bottom-2 rounded-full bg-blue-600/90 px-4 py-1 text-xs font-bold text-white shadow-lg border border-blue-300/40">
                    Evidence Evaluation
                  </div>
                </div>
              </div>

              {/* Floating candidate sample badge right */}
              <div className="hidden md:block absolute bottom-12 right-8 glass-card rounded-2xl p-4 text-left w-56 shadow-xl border border-blue-500/30 float-animation" style={{ animationDelay: '2s' }}>
                <div className="flex items-center gap-3">
                  <img 
                    src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" 
                    alt="David Chen" 
                    className="h-10 w-10 rounded-full object-cover border border-blue-400"
                  />
                  <div>
                    <p className="text-xs font-bold text-white">David Chen</p>
                    <p className="text-[10px] text-slate-400">Senior DevOps</p>
                  </div>
                </div>
                <div className="mt-2.5 flex items-center justify-between border-t border-white/10 pt-2">
                  <span className="text-[10px] text-slate-400">AI Match Score</span>
                  <span className="text-xs font-black text-blue-400 bg-blue-500/20 px-2 py-0.5 rounded-md border border-blue-500/30">
                    89% STRONG
                  </span>
                </div>
              </div>

            </div>

            {/* Bottom feature summary banner inside hero */}
            <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-white/10 pt-6 text-center">
              <div>
                <p className="text-2xl font-bold text-white">10x</p>
                <p className="text-xs text-slate-400">Faster Hiring Velocity</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-400">99.4%</p>
                <p className="text-xs text-slate-400">Skill Match Accuracy</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-purple-400">50,000+</p>
                <p className="text-xs text-slate-400">Resumes Processed</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-emerald-400">100%</p>
                <p className="text-xs text-slate-400">Bias-Free Protocol</p>
              </div>
            </div>

          </div>

        </div>

      </section>

      {/* 4-Step Process Workflow Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-xs font-bold uppercase tracking-widest text-blue-400 mb-2">
            Precision Engineering for Hiring
          </h2>
          <p className="text-2xl sm:text-3xl font-bold text-white">
            How Odysseus AI Ranks Your Candidates
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          
          <div className="glass-card rounded-2xl p-6 relative">
            <span className="text-4xl font-black text-blue-500/20 absolute top-4 right-4">01</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/20 text-blue-400 mb-4">
              <FileText className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">1. Upload Job Description</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Paste or upload your target job requirements, required technologies, experience levels, and role goals.
            </p>
          </div>

          <div className="glass-card rounded-2xl p-6 relative">
            <span className="text-4xl font-black text-blue-500/20 absolute top-4 right-4">02</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-purple-500/20 text-purple-400 mb-4">
              <Users className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">2. Add Candidate Resumes</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Batch upload PDF or TXT candidate files or select pre-loaded applicant profiles from your talent pool.
            </p>
          </div>

          <div className="glass-card rounded-2xl p-6 relative">
            <span className="text-4xl font-black text-blue-500/20 absolute top-4 right-4">03</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 mb-4">
              <Zap className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">3. Evidence Analysis</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Our neural network performs cross-referencing of semantic skill graphs, years of experience, and leadership context.
            </p>
          </div>

          <div className="glass-card rounded-2xl p-6 relative">
            <span className="text-4xl font-black text-blue-500/20 absolute top-4 right-4">04</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400 mb-4">
              <Award className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">4. Ranked Insights & Export</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Instantly view ranked candidates, detailed match breakdowns, skill gap summaries, and download Excel/CSV reports.
            </p>
          </div>

        </div>
      </section>

      {/* Bento Grid Feature Highlights */}
      <section className="py-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="glass-panel rounded-3xl p-8 sm:p-12 border border-white/10">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-center">
            
            <div className="md:col-span-1 space-y-4">
              <div className="inline-flex items-center gap-2 rounded-lg bg-blue-500/20 px-3 py-1 text-xs font-semibold text-blue-300">
                <ShieldCheck className="h-4 w-4" />
                <span>Enterprise Grade Security</span>
              </div>
              <h3 className="text-2xl sm:text-3xl font-bold text-white leading-tight">
                Unrivaled Intelligence for Talent Acquisition
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Traditional keyword-matching tools fail when candidates use different terminology. Odysseus uses semantic vector evaluation to understand actual capability.
              </p>
              <button
                onClick={() => onStart('upload')}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-blue-500 transition-all shadow-md shadow-blue-500/20"
              >
                <span>Try Workspace Now</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>

            <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
              
              <div className="glass-card rounded-2xl p-5 space-y-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/20 text-blue-400">
                  <Layers className="h-5 w-5" />
                </div>
                <h4 className="text-sm font-bold text-white">Semantic Skill Graph</h4>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Maps implicit engineering skills (e.g. recognizing that Kubernetes experience implies Docker and containerization mastery).
                </p>
              </div>

              <div className="glass-card rounded-2xl p-5 space-y-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/20 text-purple-400">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <h4 className="text-sm font-bold text-white">Automated Gap Analysis</h4>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Highlights missing core requirements and potential risk areas before inviting candidates to technical interviews.
                </p>
              </div>

              <div className="glass-card rounded-2xl p-5 space-y-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <h4 className="text-sm font-bold text-white">Blind Evaluation Protocol</h4>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Evaluates candidates strictly on demonstrated technical merit, eliminating implicit gender, age, or background bias.
                </p>
              </div>

              <div className="glass-card rounded-2xl p-5 space-y-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
                  <Download className="h-5 w-5" />
                </div>
                <h4 className="text-sm font-bold text-white">Excel & CSV Reports</h4>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Export complete candidate matrices with single-click spreadsheet files ready for team reviews.
                </p>
              </div>

            </div>

          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-8 px-4 text-center text-xs text-slate-300">
        <p>© 2026 Odysseus. Evidence-grounded candidate ranking. All rights reserved.</p>
      </footer>

    </div>
  );
};