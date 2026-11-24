import LeftPanel from './LeftPanel'
import './login.css'

/**
 * Shared authentication layout for every Mitra sign-in / sign-up screen.
 * Keeps the left marketing panel and the right form column identical so
 * candidate and recruiter flows never diverge visually.
 */
export default function AuthLayout({ children, maxWidthClass = 'max-w-[400px]' }) {
  return (
    <div className="min-h-screen bg-white text-slate-900" style={{ background: '#ffffff', colorScheme: 'light' }}>
      <div className="grid min-h-screen font-sans lg:grid-cols-2">
        <LeftPanel />
        <div className="flex items-center justify-center bg-white px-4 py-10">
          <div className={`w-full ${maxWidthClass}`}>{children}</div>
        </div>
      </div>
    </div>
  )
}
