export type AppScreen = 'landing' | 'upload' | 'processing' | 'results';

export interface Candidate {
  id: string;
  name: string;
  currentRole: string;
  matchScore: number;
  skills: string[];
  experienceYears: string;
  status: 'MATCH FOUND' | 'STRONG' | 'MODERATE' | 'POTENTIAL' | 'LOW MATCH';
  summary: string;
  strengths: string[];
  gaps: string[];
  fileName: string;
  avatarUrl: string;
  fullText?: string;
  email?: string;
  phone?: string;
  education?: string;
}

export interface JobDescription {
  title: string;
  department: string;
  requirementsText: string;
  fileName?: string;
  minYearsExp?: number;
}

export interface ProcessingLog {
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

export interface AnalysisSummaryData {
  totalResumes: number;
  topScore: number;
  avgMatch: number;
  processingTimeSec: number;
  aiRecommendation: string;
  scoreDistribution: { range: string; count: number }[];
}
