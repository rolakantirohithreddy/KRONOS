import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export function ProtectedRoute() {
  const { token, loading } = useAuth();

  if (loading) {
    return <div className="h-screen w-screen flex items-center justify-center bg-[var(--bg-primary)] text-[var(--accent-primary)]">Loading...</div>;
  }

  return token ? <Outlet /> : <Navigate to="/login" replace />;
}
