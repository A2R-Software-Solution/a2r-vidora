import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { getCurrentPath } from './utils/siteNavigation'

const container = document.getElementById('root')
const app = (
  <StrictMode>
    <App />
  </StrictMode>
)

// Prerendered pages are hydrated in place, so the visible page is never rebuilt.
// Other routes get the home page's HTML from the SPA fallback and render fresh.
if (container.dataset.prerendered === getCurrentPath()) hydrateRoot(container, app)
else createRoot(container).render(app)
