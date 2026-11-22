export const user = {
  name: 'Mohan',
  email: 'mohan@brightlabs.in',
  role: 'Recruiter',
}

export const nav = {
  workspace: [
    { to: '/dashboard', label: 'Dashboard', icon: 'grid' },
    { to: '/jobs', label: 'Jobs', icon: 'briefcase', count: '24' },
    { to: '/candidates', label: 'Candidates', icon: 'users', count: '248' },
    { to: '/matches', label: 'Matches', icon: 'spark', badge: '7 new' },
  ],
  inbox: [
    { to: '/messages', label: 'Messages', icon: 'mail', count: '3' },
    { to: '/interviews', label: 'Interviews', icon: 'calendar' },
  ],
  ai: [{ to: '/assistant', label: 'Assistant', icon: 'bot' }],
}

export const stats = [
  { label: 'Total jobs', value: '24', delta: '+6 last month', tone: 'up', icon: 'briefcase' },
  { label: 'Open roles', value: '11', delta: '+2 this week', tone: 'up', icon: 'target' },
  { label: 'Candidates', value: '248', delta: '+18 this week', tone: 'up', icon: 'users' },
  { label: 'Interviews this week', value: '9', delta: '+3 vs last week', tone: 'up', icon: 'calendar' },
]

export const suggestions = [
  {
    tone: 'purple',
    title: '3 new strong matches for AI Engineer',
    body: 'Priya, Sneha and Rohan score 81+ on PyTorch, RAG and LLM experience.',
    action: 'Review',
    to: '/jobs/ai-engineer',
  },
  {
    tone: 'amber',
    title: "2 candidates haven't heard back in 5+ days",
    body: 'Two drafted thank-you follow-ups for Kavya and Arjun are ready for your review.',
    action: 'Open drafts',
    to: '/messages',
  },
  {
    tone: 'slate',
    title: 'Data Analyst has been paused for 14 days',
    body: '4 good-fit applicants are waiting. Reopen now or close the role?',
    action: 'Decide',
    to: '/jobs/data-analyst',
  },
]

export const interviews = [
  {
    day: '15',
    month: 'MAY',
    name: 'Priya Sharma',
    role: 'AI Engineer · Technical',
    time: '10:00 – 10:45',
    status: 'Confirmed',
  },
  {
    day: '15',
    month: 'MAY',
    name: 'Kavya Nair',
    role: 'Product Designer · Portfolio',
    time: '14:30 – 15:00',
    status: 'Pending',
  },
  {
    day: '18',
    month: 'MAY',
    name: 'Arjun Mehta',
    role: 'Backend Engineer · System design',
    time: '11:00 – 12:00',
    status: 'Continue',
  },
]

export const pipeline = [
  { label: 'Applied', value: 186, width: '100%', color: '#7c6bf5' },
  { label: 'Screened', value: 108, width: '78%', color: '#8b78f7' },
  { label: 'Shortlisted', value: 64, width: '56%', color: '#9b88f8' },
  { label: 'Interview', value: 28, width: '34%', color: '#b0a0fa' },
  { label: 'Offer', value: 9, width: '16%', color: '#f0a04a' },
  { label: 'Hired', value: 4, width: '8%', color: '#d9d4ea' },
]

export const recentCandidates = [
  { name: 'Priya Sharma', meta: 'AI Engineer · 4 yrs · 92 Matches', score: 92 },
  { name: 'Arjun Mehta', meta: 'Backend Engineer · 5 yrs · NITK', score: 81 },
  { name: 'Kavya Nair', meta: 'Product Designer · 6 yrs · NIT Calicut', score: 76 },
  { name: 'Vikram Rao', meta: 'DevOps · 7 yrs · Hiring resume', score: 74 },
]

export const activity = [
  { tone: 'green', text: 'Resume Parsing processed 12 resumes · 2h' },
  { tone: 'purple', text: 'Communication drafted 2 follow-ups · 3h' },
  { tone: 'amber', text: 'Scheduling found 6 open slots · 5h' },
]

export const jobs = [
  {
    id: 'ai-engineer',
    title: 'AI Engineer',
    location: 'Bengaluru',
    work: 'Hybrid',
    department: 'Engineering',
    tags: ['PyTorch', 'LLMs', 'Python', 'MLOps'],
    applicants: 42,
    strong: 4,
    status: 'Open',
    type: 'Full-time',
    salary: '28–42 LPA',
    level: 'Mid-level',
    posted: '11 May',
    openings: 2,
    manager: 'Siddharth Menon',
    managerRole: 'Head of AI',
  },
  {
    id: 'senior-frontend',
    title: 'Senior Frontend Developer',
    location: 'Bengaluru',
    work: 'Hybrid',
    department: 'Engineering',
    tags: ['React', 'TypeScript', 'Design systems'],
    applicants: 67,
    strong: 6,
    status: 'Open',
    type: 'Full-time',
    salary: '32–48 LPA',
    level: 'Senior',
    posted: '8 May',
    openings: 1,
    manager: 'Mohan Kumar',
    managerRole: 'Engineering',
  },
  {
    id: 'product-designer',
    title: 'Product Designer',
    location: 'Mumbai',
    work: 'On-site',
    department: 'Design',
    tags: ['Figma', 'UX research', 'Prototyping'],
    applicants: 28,
    strong: 3,
    status: 'Open',
    type: 'Full-time',
    salary: '22–34 LPA',
    level: 'Mid-level',
    posted: '6 May',
    openings: 1,
    manager: 'Neha Kapoor',
    managerRole: 'Design',
  },
  {
    id: 'backend-go',
    title: 'Backend Engineer (Go)',
    location: 'Remote',
    work: 'Remote',
    department: 'Engineering',
    tags: ['Go', 'Kubernetes', 'gRPC'],
    applicants: 35,
    strong: 5,
    status: 'Open',
    type: 'Full-time',
    salary: '30–45 LPA',
    level: 'Mid-level',
    posted: '4 May',
    openings: 2,
    manager: 'Siddharth Menon',
    managerRole: 'Head of AI',
  },
  {
    id: 'devops',
    title: 'DevOps Engineer',
    location: 'Hyderabad',
    work: 'Hybrid',
    department: 'Platform',
    tags: ['Terraform', 'CI/CD', 'AWS'],
    applicants: 21,
    strong: 2,
    status: 'Open',
    type: 'Full-time',
    salary: '24–36 LPA',
    level: 'Mid-level',
    posted: '2 May',
    openings: 1,
    manager: 'Mohan Kumar',
    managerRole: 'Engineering',
  },
  {
    id: 'data-analyst',
    title: 'Data Analyst',
    location: 'Pune',
    work: 'On-site',
    department: 'Analytics',
    tags: ['SQL', 'Power BI', 'Python'],
    applicants: 31,
    strong: 4,
    status: 'Paused',
    type: 'Full-time',
    salary: '14–22 LPA',
    level: 'Mid-level',
    posted: '18 Apr',
    openings: 1,
    manager: 'Neha Kapoor',
    managerRole: 'Analytics',
  },
  {
    id: 'csm',
    title: 'Customer Success Manager',
    location: 'Bengaluru',
    work: 'On-site',
    department: 'Customer',
    tags: ['Onboarding', 'CRM'],
    applicants: 14,
    strong: 0,
    status: 'Paused',
    type: 'Full-time',
    salary: '16–24 LPA',
    level: 'Mid-level',
    posted: '12 Apr',
    openings: 1,
    manager: 'Mohan Kumar',
    managerRole: 'Customer',
  },
  {
    id: 'hrbp',
    title: 'HR Business Partner',
    location: 'Delhi',
    work: 'Hybrid',
    department: 'People',
    tags: ['Employee relations', 'HRBP'],
    applicants: 19,
    strong: 1,
    status: 'Closed',
    type: 'Full-time',
    salary: '20–30 LPA',
    level: 'Senior',
    posted: '1 Apr',
    openings: 1,
    manager: 'Siddharth Menon',
    managerRole: 'People',
  },
]

export const recentJobs = [
  jobs[0],
  jobs[1],
  jobs[5],
  jobs[7],
]

export const candidates = [
  {
    rank: 1,
    name: 'Priya Sharma',
    meta: 'ML Engineer at Brightworks · 4 yrs · 92 Matches',
    score: 92,
    highlight: true,
    note: 'Priya has shipped two production RAG systems and fine-tuned Llama models. Her AWS experience is limited (mostly GCP), which is easy to bridge.',
    skills: ['Python', 'PyTorch', 'LLM fine-tuning', 'AWS'],
    matched: ['RAG pipelines', 'Vector databases', 'MLOps'],
    experience: 'Within range',
  },
  {
    rank: 2,
    name: 'Sneha Reddy',
    meta: 'ML Engineer · 5 yrs · IIT Hyderabad',
    score: 88,
    skills: ['Python', 'RAG', 'PyTorch'],
  },
  {
    rank: 3,
    name: 'Rohan Iyer',
    meta: 'Senior Data Scientist at Swiggy · 6 yrs · 81 Matches',
    score: 81,
    skills: ['Python', 'LLMs'],
  },
  {
    rank: 4,
    name: 'Karan Singh',
    meta: 'ML Engineer at Postman · 4 yrs · NITK',
    score: 76,
    skills: ['PyTorch', 'AWS'],
  },
  {
    rank: 5,
    name: 'Aditya Verma',
    meta: 'AI Engineer · 3 yrs · VIT',
    score: 64,
    skills: ['Python'],
  },
]

export const requirements = {
  required: ['Python', 'RAG pipelines', 'LLM fine-tuning', 'Vector databases', 'AWS'],
  nice: ['Kubernetes', 'MLOps', 'Published research'],
  experience: '3–5 years',
  seniority: 'Mid-level',
}

export const scoreBuckets = [
  { label: '90–100', count: 3, width: '28%' },
  { label: '80–89', count: 4, width: '38%' },
  { label: '70–79', count: 8, width: '62%' },
  { label: '60–69', count: 12, width: '84%' },
  { label: '< 60', count: 15, width: '100%' },
]

export const hiringTeam = [
  { name: 'Siddharth Menon', role: 'Hiring manager' },
  { name: 'Mohan Kumar', role: 'Recruiter' },
]

export const requiredSkills = ['Python', 'PyTorch', 'LLM fine-tuning', 'RAG pipelines', 'Vector databases', 'AWS']
export const niceSkills = ['Kubernetes', 'MLOps', 'Published research']
