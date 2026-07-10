import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { InputPanelPage } from './pages/InputPanelPage'
import { ProgressPage } from './pages/ProgressPage'
import { AssessmentViewerPage } from './pages/AssessmentViewerPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InputPanelPage />} />
        <Route path="/experiments/:experimentId/progress" element={<ProgressPage />} />
        <Route path="/experiments/:experimentId/viewer" element={<AssessmentViewerPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
