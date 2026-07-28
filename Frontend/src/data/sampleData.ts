import { Candidate, JobDescription } from '../types';

export const SAMPLE_JOB_DESCRIPTION: JobDescription = {
  title: 'Senior Technical Lead / Fullstack Architect',
  department: 'Enterprise Platform Engineering',
  requirementsText: `Role: Senior Technical Lead / Fullstack Architect
Requirements:
- 8+ years of experience in full-stack software development with Node.js, TypeScript, and React.
- Strong knowledge of microservices architecture, Docker, Kubernetes, AWS cloud services.
- Expertise in frontend performance, state management, and modern UI frameworks.
- Demonstrated leadership in architectural decision-making, API design, and CI/CD pipelines.
- Bachelor's or Master's degree in Computer Science or equivalent experience.`,
  fileName: 'Job_Description_Sr_Tech_Lead.pdf',
  minYearsExp: 8,
};

export const SAMPLE_CANDIDATES: Candidate[] = [
  {
    id: 'cand-1',
    name: 'Alexandra Vance',
    currentRole: 'Lead Fullstack Architect',
    matchScore: 98,
    skills: ['REACT', 'NODE', 'AWS', 'TYPESCRIPT', 'SYSTEM DESIGN'],
    experienceYears: '12 Yrs',
    status: 'MATCH FOUND',
    summary: 'Architected large-scale cloud microservices serving 5M+ daily active users. Expert in React, Node, and Kubernetes.',
    strengths: [
      '100% match for React & Node core tech stack',
      'Extensive system architecture experience (12 years)',
      'Proven leadership managing teams of 15+ engineers',
      'AWS Solutions Architect Certified'
    ],
    gaps: ['Slightly higher salary expectation range'],
    fileName: 'Alexandra_Vance_Resume.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80',
    email: 'alexandra.vance@example.com',
    phone: '+1 (555) 234-5678',
    education: 'M.S. Computer Science, Stanford University'
  },
  {
    id: 'cand-2',
    name: 'David Chen',
    currentRole: 'Senior DevOps & Backend Specialist',
    matchScore: 89,
    skills: ['K8S', 'DOCKER', 'NODE', 'PYTHON', 'GO'],
    experienceYears: '8 Yrs',
    status: 'STRONG',
    summary: 'Deep expertise in Kubernetes container orchestration, CI/CD automated pipelines, and high-throughput Node services.',
    strengths: [
      'Exceptional DevOps & Infrastructure automation skillset',
      '8 years of relevant backend & cloud experience',
      'Strong background in security compliance & monitoring'
    ],
    gaps: ['Less emphasis on frontend React UI development'],
    fileName: 'David_Chen_CV.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    email: 'david.chen@example.com',
    phone: '+1 (555) 876-5432',
    education: 'B.S. Software Engineering, UC Berkeley'
  },
  {
    id: 'cand-3',
    name: 'Julian Mars',
    currentRole: 'Frontend Lead & UI Engineer',
    matchScore: 82,
    skills: ['REACT', 'TYPESCRIPT', 'TAILWIND', 'NEXT.JS', 'GRAPHQL'],
    experienceYears: '6 Yrs',
    status: 'STRONG',
    summary: 'Specializes in modern React applications, state architecture, component design systems, and frontend optimization.',
    strengths: [
      'Mastery of React, TypeScript, and modern styling frameworks',
      'Great focus on developer tooling and design systems',
      'Proven track record of improving web performance by 40%'
    ],
    gaps: ['6 years experience vs 8+ target in JD', 'Lacks heavy Kubernetes background'],
    fileName: 'Julian_Mars_Resume.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
    email: 'julian.mars@example.com',
    phone: '+1 (555) 345-6789',
    education: 'B.S. Computer Science, MIT'
  },
  {
    id: 'cand-4',
    name: 'Sarah Chen',
    currentRole: 'Senior Full Stack Engineer',
    matchScore: 94,
    skills: ['REACT', 'NODE', 'TYPESCRIPT', 'AWS', 'POSTGRES'],
    experienceYears: '9 Yrs',
    status: 'MATCH FOUND',
    summary: 'Full stack developer with 9 years of experience delivering SaaS products with Node, React, and serverless cloud APIs.',
    strengths: [
      'Exceeds 8-year experience requirement',
      'Strong match across both React frontend and Node backend',
      'Solid cloud deployment experience on AWS'
    ],
    gaps: ['Limited team management experience'],
    fileName: 'Sarah_Chen_Resume.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150&auto=format&fit=crop&q=80',
    email: 'sarah.chen@example.com',
    phone: '+1 (555) 456-7890',
    education: 'B.S. Computer Engineering, University of Washington'
  },
  {
    id: 'cand-5',
    name: 'Marcus Vance',
    currentRole: 'Cloud Infrastructure Lead',
    matchScore: 78,
    skills: ['AWS', 'TERRAFORM', 'PYTHON', 'DOCKER', 'LINUX'],
    experienceYears: '10 Yrs',
    status: 'MODERATE',
    summary: 'Infrastructure engineer focused on cloud automation, multi-region failover, and infrastructure-as-code.',
    strengths: [
      '10 years of deep cloud & DevOps engineering',
      'Terraform & CloudFormation expert'
    ],
    gaps: ['Minimal frontend JavaScript/React experience'],
    fileName: 'Marcus_V_CV.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80',
    email: 'marcus.v@example.com',
    phone: '+1 (555) 567-8901',
    education: 'B.S. Information Technology, Georgia Tech'
  },
  {
    id: 'cand-6',
    name: 'Elena Rodriguez',
    currentRole: 'Software Engineer II',
    matchScore: 71,
    skills: ['TYPESCRIPT', 'EXPRESS', 'REACT', 'MONGODB'],
    experienceYears: '4 Yrs',
    status: 'POTENTIAL',
    summary: 'Versatile middle-tier developer building web services, REST endpoints, and dynamic web interfaces.',
    strengths: [
      'Solid foundations in React and Express Node services',
      'Fast learner with high productivity velocity'
    ],
    gaps: ['4 years experience vs 8+ requirement', 'Needs growth in system architecture'],
    fileName: 'Elena_Rodriguez_CV.pdf',
    avatarUrl: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=80',
    email: 'elena.r@example.com',
    phone: '+1 (555) 678-9012',
    education: 'B.S. Computer Science, UT Austin'
  }
];
