import { createContext, useContext, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

const ThemeContext = createContext({ theme: 'light', toggle: () => {} })

export function ThemeProvider({ children }) {
  const { pathname } = useLocation()
  const isAssistant = pathname === '/assistant'
  const [theme, setTheme] = useState(() => localStorage.getItem('mitra-theme') || 'light')

  useEffect(() => {
    localStorage.setItem('mitra-theme', theme)
  }, [theme])

  const toggle = () => setTheme((current) => (current === 'light' ? 'dark' : 'light'))

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      <div className={`mitra-root ${isAssistant ? 'assistant-route' : ''}`} data-theme={theme}>
        {children}
      </div>
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
