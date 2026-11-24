import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { supabase } from '../services/auth'
import { getMyRole } from '../services/account'

const AuthContext = createContext({
  session: null,
  loading: true,
  role: null,
  roleLoading: false,
  roleError: '',
  refreshRole: async () => {},
})

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(Boolean(supabase))
  const [role, setRole] = useState(null)
  const [roleLoading, setRoleLoading] = useState(false)
  const [roleError, setRoleError] = useState('')
  const roleRequestId = useRef(0)
  // Tracks the user id we have already resolved a role for, so token refreshes
  // (which Supabase emits on tab focus/visibility) do not trigger a re-fetch.
  const resolvedUserIdRef = useRef(null)

  useEffect(() => {
    if (!supabase) {
      setLoading(false)
      return undefined
    }
    let active = true
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return
      const s = data.session ?? null
      setSession(s)
      resolvedUserIdRef.current = s?.user?.id ?? null
      setLoading(false)
    })
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return
      // Preserve the previous session object reference when nothing meaningful
      // changed (same user + same access token). This prevents unnecessary
      // re-renders and role re-fetches on tab focus / token refresh events.
      setSession((prev) => {
        const prevUid = prev?.user?.id ?? null
        const nextUid = nextSession?.user?.id ?? null
        const prevToken = prev?.access_token ?? null
        const nextToken = nextSession?.access_token ?? null
        if (prevUid === nextUid && prevToken === nextToken) {
          return prev
        }
        return nextSession ?? null
      })
    })
    return () => {
      active = false
      subscription.subscription.unsubscribe()
    }
  }, [])

  const refreshRole = useCallback(async () => {
    const requestId = roleRequestId.current + 1
    roleRequestId.current = requestId
    setRole(null)
    setRoleError('')
    setRoleLoading(true)
    try {
      const data = await getMyRole()
      if (roleRequestId.current !== requestId) return
      setRole(data?.role || null)
    } catch (err) {
      if (roleRequestId.current !== requestId) return
      setRole(null)
      setRoleError(err?.message || 'Could not determine your account type.')
    } finally {
      if (roleRequestId.current === requestId) setRoleLoading(false)
    }
  }, [])

  // Re-resolve the role only when the authenticated user identity changes.
  // Token refreshes and tab-focus events must not cause a role re-fetch or
  // the "Checking your session…" screen to reappear.
  useEffect(() => {
    if (loading) return undefined
    const uid = session?.user?.id ?? null
    if (!session) {
      if (resolvedUserIdRef.current !== null) {
        roleRequestId.current += 1
        resolvedUserIdRef.current = null
        setRole(null)
        setRoleError('')
        setRoleLoading(false)
      }
      return undefined
    }
    if (uid === resolvedUserIdRef.current && role !== null) {
      // Same user, role already resolved — do nothing.
      return undefined
    }
    resolvedUserIdRef.current = uid
    refreshRole()
    return undefined
  }, [session, loading, role, refreshRole])

  const value = useMemo(
    () => ({ session, loading, role, roleLoading, roleError, refreshRole }),
    [session, loading, role, roleLoading, roleError, refreshRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
