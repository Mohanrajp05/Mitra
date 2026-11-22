import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './styles/global.css'
import './styles/auth.css'
import './styles/dashboard.css'
import './styles/forms.css'
import './styles/chat.css'
import './styles/mitra.css'
import './styles/newpages.css'
import './styles/documents.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
