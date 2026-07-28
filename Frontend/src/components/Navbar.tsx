import React from 'react';
import { AppScreen } from '../types';
import { Sparkles, Brain, Upload, BarChart3, ShieldCheck, Cpu } from 'lucide-react';

interface NavbarProps {
  currentScreen: AppScreen;
  onNavigate: (screen: AppScreen) => void;
  candidateCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({ currentScreen, onNavigate, candidateCount }) => {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-white/10 bg-[#051424]/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        
        {/* Brand Logo */}
        <div 
          className="flex items-center gap-3 cursor-pointer group"
          onClick={() => onNavigate('landing')}
        >
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-600 to-purple-600 p-0.5 shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <div className="flex h-full w-full items-center justify-center rounded-[10px] bg-[#051424]">
              <Brain className="h-5 w-5 text-blue-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-white">
                ODYSSEUS
              </span>
              <span className="rounded-md bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-blue-400 border border-blue-500/30">
                RANK.AI
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">Precision Resume Parsing Engine</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 rounded-full bg-white/5 p-1 border border-white/10">
          <button
            onClick={() => onNavigate('landing')}
            className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium transition-all ${
              currentScreen === 'landing'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Overview
          </button>

          <button
            onClick={() => onNavigate('upload')}
            className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium transition-all ${
              currentScreen === 'upload'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            }`}
          >
            <Upload className="h-3.5 w-3.5" />
            Upload Workspace
          </button>

          <button
            onClick={() => onNavigate('results')}
            className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium transition-all ${
              currentScreen === 'results' || currentScreen === 'processing'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            }`}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Rankings & Analysis
            {candidateCount > 0 && (
              <span className="ml-1 rounded-full bg-blue-400/20 px-1.5 py-0.2 text-[10px] text-blue-300">
                {candidateCount}
              </span>
            )}
          </button>
        </nav>

        {/* Action Button & Status */}
        <div className="flex items-center gap-3">
          <div className="hidden lg:flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-1.5 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Gemini 3.6 Active
          </div>

          <button
            onClick={() => onNavigate('upload')}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/25 transition-all hover:from-blue-500 hover:to-indigo-500 hover:scale-[1.02] active:scale-95 primary-glow"
          >
            <Cpu className="h-4 w-4" />
            <span>Analyze Resumes</span>
          </button>
        </div>

      </div>
    </header>
  );
};
