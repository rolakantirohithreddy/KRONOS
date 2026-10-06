import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../lib/axios';
import { useAuth } from '../hooks/useAuth';
import { AuthLayout } from '../components/AuthLayout';
import kronosLogo from '../assets/kronos-logo.svg';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const cleanEmail = email.trim().toLowerCase();
    try {
      const res = await api.post('/auth/login', { email: cleanEmail, password });
      login(res.data.access_token);
      toast.success('Login successful');
      navigate('/dashboard');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Invalid credentials';
      setError(detail);
      if (err.response?.status === 403) {
        toast.error('Email not verified. Please complete verification.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout>
      {/* ── Logo + heading ── */}
      <div className="mb-8 text-center">
        <div className="mb-3 flex items-center justify-center gap-3">
          <img
            src={kronosLogo}
            alt="KRONOS"
            className="auth-logo-hover h-9 w-9 cursor-default"
          />
          <span className="text-base font-bold tracking-[0.16em] text-[var(--text-primary)]">
            KRONOS
          </span>
        </div>
        <p className="mx-auto max-w-xs text-sm leading-6 text-[var(--text-muted)]">
          Multi-Agent Explainable Incident Response for IoT Networks
        </p>
      </div>


      {/* ── Form ── */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div
            className="rounded-lg border p-3 text-sm"
            style={{
              borderColor: 'color-mix(in srgb, var(--accent-danger) 50%, transparent)',
              background:  'color-mix(in srgb, var(--accent-danger) 10%, transparent)',
              color:       'var(--accent-danger)',
            }}
          >
            {error}
            {error.toLowerCase().includes('verify') && (
              <div className="mt-2 pt-2 border-t border-[var(--accent-danger)]/30">
                <Link
                  to="/register"
                  className="font-semibold underline hover:opacity-80"
                >
                  Complete registration & verify OTP &rarr;
                </Link>
              </div>
            )}
          </div>
        )}

        <div className="space-y-1">
          <label
            htmlFor="login-email"
            className="text-sm font-medium text-[var(--text-primary)]"
          >
            Email
          </label>
          <input
            id="login-email"
            type="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="auth-input w-full rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 text-[var(--text-primary)] transition-colors placeholder:text-[var(--text-muted)]/70"
            placeholder="admin@kronos.local"
          />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label
              htmlFor="login-password"
              className="text-sm font-medium text-[var(--text-primary)]"
            >
              Password
            </label>
            <Link
              to="/forgot-password"
              className="text-sm text-[var(--accent-primary)] hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="auth-input w-full rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 pr-10 text-[var(--text-primary)] transition-colors placeholder:text-[var(--text-muted)]/70"
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPassword(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-md px-4 py-3 font-semibold transition-opacity hover:opacity-90 disabled:opacity-50"
          style={{
            background: 'var(--accent-primary)',
            color:      'var(--button-text)',
          }}
        >
          {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Login'}
        </button>
      </form>

      <p className="mt-7 text-center text-sm text-[var(--text-muted)]">
        Don't have an account?{' '}
        <Link
          to="/register"
          className="font-medium text-[var(--accent-primary)] hover:underline"
        >
          Register
        </Link>
      </p>
    </AuthLayout>
  );
}
