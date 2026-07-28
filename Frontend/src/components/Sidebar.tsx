import React from 'react';
import { 
  LayoutDashboard, 
  Trophy, 
  Users, 
  Briefcase, 
  FileText, 
  History, 
  HelpCircle, 
  LogOut,
  Sparkles,
  Zap
} from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  candidateCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab, candidateCount }) => {
  const mainNav = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'ranking', label: 'Candidate Ranking', icon: Trophy, badge: candidateCount > 0 ? candidateCount : undefined },
    { id: 'pipeline', label: 'Talent Pipeline', icon: Users },
    { id: 'jobs', label: 'Job Positions', icon: Briefcase },
    { id: 'audit', label: 'Audit Logs', icon: History },
  ];

  return (
    <aside className="w-64 shrink-0 hidden md:flex flex-col border-r border-white/10 bg-[#06182c]/80 min-h-[calc(100vh-4rem)] p-4 justify-between">
      <div className="space-y-6">
        
        {/* Workspace info badge */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/20 text-blue-400">
              <Zap className="h-4 w-4" />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Enterprise HR Studio</p>
              <p className="text-[11px] text-slate-400">Plan: Enterprise AI Unlimited</p>
            </div>
          </div>
        </div>

        {/* Main Nav Section */}
        <div>
          <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
            Workspace
          </p>
          <div className="space-y-1">
            {mainNav.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between rounded-xl px-3 py-2.5 text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`h-4 w-4 ${isActive ? 'text-blue-400' : 'text-slate-400'}`} />
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== undefined && (
                    <span className="rounded-full bg-blue-500 px-2 py-0.5 text-[10px] font-bold text-white shadow-sm">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* AI Capabilities Box */}
        <div className="rounded-xl border border-purple-500/20 bg-gradient-to-b from-purple-500/10 to-blue-500/10 p-3.5 space-y-2">
          <div className="flex items-center gap-2 text-purple-300 text-xs font-semibold">
            <Sparkles className="h-3.5 w-3.5 text-purple-400" />
            <span>Semantic Matching</span>
          </div>
          <p className="text-[11px] text-slate-300 leading-relaxed">
            AI evaluates deep skill coverage, leadership indicators, and domain suitability beyond simple keyword counts.
          </p>
        </div>

      </div>

      {/* Bottom links */}
      <div className="space-y-1 pt-4 border-t border-white/10">
        <button className="w-full flex items-center gap-3 rounded-xl px-3 py-2 text-xs font-medium text-slate-400 hover:bg-white/5 hover:text-white transition-all">
          <HelpCircle className="h-4 w-4" />
          <span>Documentation</span>
        </button>
        <button className="w-full flex items-center gap-3 rounded-xl px-3 py-2 text-xs font-medium text-slate-400 hover:bg-white/5 hover:text-white transition-all">
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
};
