import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { InputPanelPage } from './pages/InputPanelPage'
import { ProgressPage } from './pages/ProgressPage'
import { AssessmentViewerPage } from './pages/AssessmentViewerPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InputPanelPage />} />
        <Route path="/runs/:runId/progress" element={<ProgressPage />} />
        <Route path="/experiments/:experimentId/viewer/:runId?" element={<AssessmentViewerPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
