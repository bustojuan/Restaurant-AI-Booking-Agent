import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import './styles/app.css'
const App = lazy(() => import('./app/App').then((module) => ({ default: module.App })))
const AdminApp = lazy(() =>
  import('./admin/AdminApp').then((module) => ({ default: module.AdminApp })),
)
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Suspense fallback={null}>
      {window.location.hash === '#admin' ? <AdminApp /> : <App />}
    </Suspense>
  </React.StrictMode>,
)
