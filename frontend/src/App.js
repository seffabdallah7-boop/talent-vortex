import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { DarkModeProvider } from "@/context/DarkModeContext";
import { Toaster } from "@/components/ui/sonner";
import ProtectedRoute from "@/components/ProtectedRoute";
import Landing from "@/pages/Landing";
import Auth from "@/pages/Auth";
import AuthCallback from "@/pages/AuthCallback";
import JobDetail from "@/pages/JobDetail";
import CandidateDashboard from "@/pages/CandidateDashboard";
import AdminDashboard from "@/pages/AdminDashboard";
import RecordingShare from "@/pages/RecordingShare";
import useAutoTranslate from "@/hooks/useAutoTranslate";

function AppInner() {
  useAutoTranslate();
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Auth />} />
      <Route path="/jobs/:id" element={<JobDetail />} />
      <Route path="/dashboard" element={<ProtectedRoute role="candidate"><CandidateDashboard /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute role="admin"><AdminDashboard /></ProtectedRoute>} />
      <Route path="/recordings/shared/:token" element={<ProtectedRoute role="admin"><RecordingShare /></ProtectedRoute>} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <DarkModeProvider>
        <AuthProvider>
          <ThemeProvider>
            <AppInner />
            <Toaster position="top-right" richColors />
          </ThemeProvider>
        </AuthProvider>
      </DarkModeProvider>
    </BrowserRouter>
  );
}

export default App;
