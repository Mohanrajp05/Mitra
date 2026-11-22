import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Logo } from '../../mitra/Icons'
import NwIcon from '../../new-pages/NwIcon'
import { isSupabaseConfigured, signIn, signInWithGoogle, signUp } from '../../services/auth'
import { validateEmail } from '../../utils/validation'

const points = [
  { tone: 'blue', text: 'Six helpful AI agents, one calm workspace' },
  { tone: 'violet', text: 'You review every AI suggestion before it goes out' },
  { tone: 'indigo', text: 'Built for recruiters and small HR teams' },
]

const roles = [
  { cls: 'role-1', tone: 'coral', icon: 'edit', label: 'Product Designer' },
  { cls: 'role-2', tone: 'green', icon: 'dashboard', label: 'Data Analyst' },
  { cls: 'role-3', tone: 'amber', icon: 'search', label: 'UX Researcher' },
  { cls: 'role-4', tone: 'blue', icon: 'lightning', label: 'Frontend Engineer' },
  { cls: 'role-5', tone: 'violet', icon: 'list', label: 'Product Manager' },
]

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" />
      <circle cx="12" cy="12" r="2.6" />
    </svg>
  )
}

export default function LoginPage({ start = 'login' }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState(start)
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const emailResult = validateEmail(email)
  const emailInvalid = email.length > 0 && !emailResult.valid

  const switchMode = (nextMode) => {
    setMode(nextMode)
    setError('')
    setNotice('')
  }

  async function socialSignIn() {
    if (!isSupabaseConfigured) {
      setError('Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY to frontend/.env.local and restart Vite.')
      return
    }
    setError('')
    setNotice('')
    setGoogleLoading(true)
    try {
      const from = location.state?.from
      const destination = typeof from === 'string' && from.startsWith('/') && !from.startsWith('/login') && !from.startsWith('/register')
        ? from
        : '/dashboard'
      await signInWithGoogle(`${window.location.origin}${destination}`)
    } catch (err) {
      setError(err.message || 'Google sign-in failed. Please try again.')
      setGoogleLoading(false)
    }
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (!isSupabaseConfigured) {
      setError('Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY to frontend/.env.local and restart Vite.')
      return
    }
    if (!emailResult.valid || !password) {
      setError('Enter a valid work email and your password.')
      return
    }

    setLoading(true)
    try {
      const from = location.state?.from
      const destination = typeof from === 'string' && from.startsWith('/') && !from.startsWith('/login') && !from.startsWith('/register')
        ? from
        : '/dashboard'
      if (mode === 'login') {
        await signIn(email.trim(), password)
        navigate(destination, { replace: true })
      } else {
        const data = await signUp(email.trim(), password, {
          full_name: name.trim(),
        })
        if (data.session) {
          navigate(destination, { replace: true })
        } else {
          setNotice('Account created. Check your email for a confirmation link, then log in.')
          setPassword('')
          setMode('login')
        }
      }
    } catch (err) {
      setError(err.message || (mode === 'login' ? 'Login failed. Please check your details.' : 'Registration failed. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-screen">
      <section className="auth-hero">
        <div className="auth-brand-row">
          <Logo />
        </div>

        <div className="hero-art" aria-hidden="true">
          <span className="hero-orbit" />
          <span className="hero-halo" />

          <svg className="hero-buddy" viewBox="0 0 220 220" role="img" aria-label="Friendly AI helper illustration">
            <defs>
              <radialGradient id="orbGrad" cx="35%" cy="30%" r="80%">
                <stop offset="0%" stopColor="#c4b5fd" />
                <stop offset="55%" stopColor="#8b7cf6" />
                <stop offset="100%" stopColor="#5b52e8" />
              </radialGradient>
            </defs>
            <circle cx="110" cy="118" r="88" fill="url(#orbGrad)" />
            <ellipse cx="82" cy="82" rx="26" ry="14" fill="#fff" opacity="0.28" transform="rotate(-25 82 82)" />
            <circle cx="88" cy="120" r="7" fill="#fff" />
            <circle cx="132" cy="120" r="7" fill="#fff" />
            <circle cx="89" cy="121" r="3.2" fill="#2e2a7a" />
            <circle cx="133" cy="121" r="3.2" fill="#2e2a7a" />
            <path d="M92 144c8 10 28 10 36 0" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" />
            <circle cx="70" cy="138" r="8" fill="#f9a8d4" opacity="0.55" />
            <circle cx="150" cy="138" r="8" fill="#f9a8d4" opacity="0.55" />
          </svg>

          <svg className="hero-ghost" viewBox="0 0 40 44" aria-hidden="true">
            <path d="M6 40V20a14 14 0 0 1 28 0v20l-5-4-4 4-5-4-5 4-4-4z" fill="#a78bfa" />
            <circle cx="15" cy="19" r="2.4" fill="#fff" />
            <circle cx="25" cy="19" r="2.4" fill="#fff" />
          </svg>

          {roles.map((role) => (
            <span key={role.cls} className={`role-chip ${role.cls}`}>
              <span className={`role-ico role-${role.tone}`}><NwIcon name={role.icon} /></span>
              {role.label}
              <span className="presence" />
            </span>
          ))}

          <div className="hero-bubble">
            Mitra will find roles that <strong>matches your interest</strong>.
          </div>
        </div>

        <h1>
          Hiring feels lighter
          <br />
          with a <em>friend</em> by your side.
        </h1>
        <p className="hero-copy">
          Mitra reads resumes, finds great matches, drafts thoughtful emails and books interviews — so you can focus on people.
        </p>
        <ul className="hero-points">
          {points.map((point) => (
            <li key={point.text}>
              <span className={`dot dot-${point.tone}`} />
              {point.text}
            </li>
          ))}
        </ul>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-tabs" role="tablist">
            <button type="button" className={mode === 'login' ? 'on' : ''} onClick={() => switchMode('login')}>
              Log in
            </button>
            <button type="button" className={mode === 'signup' ? 'on' : ''} onClick={() => switchMode('signup')}>
              Sign up
            </button>
          </div>

          <h2>{mode === 'login' ? 'Welcome back 👋' : 'Create your account ✨'}</h2>
          <p className="auth-lead">
            {mode === 'login' ? 'Log in to pick up where you and Mitra left off.' : 'Set up your workspace in under a minute.'}
          </p>
-
          <button type="button" className="google-btn" onClick={socialSignIn} disabled={googleLoading}>
            <span className="g-mark">G</span> {googleLoading ? 'Redirecting to Google…' : 'Continue with Google'}
          </button>
          <p className="or-line"><span>or continue with email</span></p>

          {!isSupabaseConfigured && (
            <div className="alert alert-warning" role="alert">
              Supabase is not configured. Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code>, add your project URL and publishable key, then restart Vite.
            </div>
          )}

          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}

          {notice && (
            <div className="alert alert-success" role="status">
              {notice}
            </div>
          )}

          <form onSubmit={submit} className="auth-form">
            {mode === 'signup' ? (
              <label>
                Full name
                <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Mohan Kumar" required />
              </label>
            ) : null}
            <label>
              Email
              <span className="input-ico">
                <NwIcon name="mail" />
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="mohan@brightlabs.in"
                  aria-invalid={emailInvalid}
                  required
                />
              </span>
            </label>
            <div className="field-head">
              <span className="field-label-text">Password</span>
              {mode === 'login' ? (
                <button type="button" className="forgot-link">Forgot password?</button>
              ) : null}
            </div>
            <label className="stacked">
              <span className="input-ico">
                <NwIcon name="lock" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                />
                <button
                  type="button"
                  className="eye-btn"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  <EyeIcon />
                </button>
              </span>
            </label>
            {mode === 'login' ? (
              <label className="check-row">
                <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
                Keep me signed in for 30 days
              </label>
            ) : null}
            <button type="submit" className="primary-btn full" disabled={loading}>
              {loading ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
            </button>
          </form>

          <p className="switch-line">
            {mode === 'login' ? (
              <>
                New to Mitra? <button type="button" className="cta-link" onClick={() => switchMode('signup')}>Create a free account</button>
              </>
            ) : (
              <>
                Already have an account? <button type="button" className="cta-link" onClick={() => switchMode('login')}>Log in</button>
              </>
            )}
          </p>

          <blockquote>
            <span className="t-avatar" aria-hidden="true">NK</span>
            <p>
              “Mitra cut our screening time in half. It genuinely feels like a teammate.”
              <cite>Neha Kapoor · Head of People, Loopwell</cite>
            </p>
          </blockquote>
          <p className="legal">
            By continuing you agree to our <Link to="/login">Terms</Link> and <Link to="/login">Privacy Policy</Link>.
          </p>
        </div>
      </section>
    </div>
  )
}
