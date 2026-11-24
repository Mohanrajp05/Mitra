import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import AuthLayout from '../pages/mitra/login/AuthLayout'
import { InteractiveHoverButton } from '../pages/mitra/login/ui/interactive-hover-button'
import { signUp } from '../services/auth'
import { onboardCandidate } from '../services/candidatePortal'
import { useAuth } from '../auth/AuthProvider'

const UserIcon = () => (
  <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </svg>
)

const MailIcon = () => (
  <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </svg>
)

const LockIcon = () => (
  <svg className="h-4 w-4 shrink-0 text-slate-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2Zm-8-2a3 3 0 0 1 6 0v2H9V7Z" />
  </svg>
)

const EyeIcon = ({ off }) => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="12" cy="12" r="3" />
    {off && <path d="M4 4l16 16" strokeLinecap="round" />}
  </svg>
)

const fade = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
}

export default function CandidateRegisterPage() {
  const navigate = useNavigate()
  const { refreshRole } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await signUp(email.trim(), password, { role: 'candidate', full_name: fullName.trim() })
      if (!result?.session) {
        // Email confirmation is enabled: the account exists but cannot be
        // onboarded until the user confirms and signs in.
        try {
          const { signIn } = await import('../services/auth')
          await signIn(email.trim(), password)
        } catch {
          setNotice(
            'Account created. Check your email to confirm it, then log in — your candidate dashboard will be set up automatically.',
          )
          return
        }
      }
      await onboardCandidate({ full_name: fullName.trim(), email: email.trim() })
      // The role row is created by onboarding; re-resolve it before entering
      // the protected candidate portal so a stale "recruiter" role cannot
      // bounce the new candidate to the recruiter dashboard.
      await refreshRole()
      navigate('/candidate/dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Candidate registration failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout maxWidthClass="max-w-[420px]">
      <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }}>
        <motion.div variants={fade} className="flex items-center justify-between gap-3">
          <Link to="/login" className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 hover:text-slate-800">
            <span aria-hidden="true">←</span> Back to log in
          </Link>
          <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-emerald-700">
            Candidate
          </span>
        </motion.div>

        <motion.h1 variants={fade} className="mt-7 text-[26px] font-extrabold tracking-tight text-slate-900">
          Create Your <span className="text-emerald-600">Candidate</span> Account
        </motion.h1>
        <motion.p variants={fade} className="mt-2 text-xs leading-relaxed text-slate-500">
          Discover jobs, apply for opportunities and connect directly with recruiters.
        </motion.p>

        {error && (
          <motion.p variants={fade} className="mt-5 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </motion.p>
        )}
        {notice && (
          <motion.p variants={fade} className="mt-5 rounded-lg bg-emerald-50 px-3 py-2 text-xs leading-relaxed text-emerald-700">
            {notice}
          </motion.p>
        )}

        <form onSubmit={submit} className="mt-6">
          <motion.div variants={fade}>
            <label htmlFor="candidate-name" className="text-xs font-semibold text-slate-900">
              Full Name
            </label>
            <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-100">
              <UserIcon />
              <input
                id="candidate-name"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full bg-transparent text-xs text-slate-800 outline-none placeholder:text-slate-400"
                placeholder="Your full name"
                autoComplete="name"
                required
              />
            </div>
          </motion.div>

          <motion.div variants={fade} className="mt-4">
            <label htmlFor="candidate-email" className="text-xs font-semibold text-slate-900">
              Email
            </label>
            <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-100">
              <MailIcon />
              <input
                id="candidate-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-transparent text-xs text-slate-800 outline-none placeholder:text-slate-400"
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </div>
          </motion.div>

          <motion.div variants={fade} className="mt-4">
            <label htmlFor="candidate-password" className="text-xs font-semibold text-slate-900">
              Password
            </label>
            <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-100">
              <LockIcon />
              <input
                id="candidate-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-transparent text-xs text-slate-800 outline-none"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="text-slate-400 hover:text-slate-600"
              >
                <EyeIcon off={showPassword} />
              </button>
            </div>
          </motion.div>

          <motion.div variants={fade}>
            <InteractiveHoverButton
              type="submit"
              disabled={busy}
              className="mt-5 w-full rounded-xl py-3 text-xs shadow-lg shadow-emerald-200/60 disabled:opacity-60"
            >
              {busy ? 'Creating account…' : 'Register'}
            </InteractiveHoverButton>
          </motion.div>
        </form>

        <motion.div variants={fade} className="mt-5 space-y-1 text-center text-[11px] text-slate-500">
          <p>
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-emerald-700 hover:underline">
              Log in
            </Link>
          </p>
          <p>
            Recruiter?{' '}
            <Link to="/register" className="font-semibold text-orange-600 hover:underline">
              Create a recruiter account
            </Link>
          </p>
        </motion.div>

        <motion.p variants={fade} className="mt-6 text-center text-[10px] text-slate-400">
          By continuing you agree to our <a href="#" className="underline">Terms</a> and{' '}
          <a href="#" className="underline">Privacy Policy</a>.
        </motion.p>
      </motion.div>
    </AuthLayout>
  )
}
