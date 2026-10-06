import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, ArrowLeft } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../lib/axios';
import { OTPInput } from '../components/OTPInput';
import { AuthLayout } from '../components/AuthLayout';
import kronosLogo from '../assets/kronos-logo.svg';

export function ForgotPasswordPage() {
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const navigate = useNavigate();

  const cleanEmail = email.trim().toLowerCase();

  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await api.post('/auth/forgot-password', { email: cleanEmail });
      setStep(2);
      toast.success('Reset code sent to email');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send reset code');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) { setError('Passwords do not match'); return; }
    if (otp.length < 6) return;
    setIsLoading(true);
    setError('');
    try {
      await api.post('/auth/reset-password', {
        email: cleanEmail, otp_code: otp.trim(), new_password: newPassword,
      });
      toast.success('Password reset successfully');
      navigate('/login');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset password');
    } finally {
      setIsLoading(false);
    }
  };

  const errorBanner = error && (
    <div
      className="rounded-lg border p-3 text-sm"
      style={{
        borderColor: 'color-mix(in srgb, var(--accent-danger) 50%, transparent)',
        background:  'color-mix(in srgb, var(--accent-danger) 10%, transparent)',
        color:       'var(--accent-danger)',
      }}
    >
      {error}
    </div>
  );

  const btnPrimary =
    'flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 font-medium transition-opacity hover:opacity-90 disabled:opacity-50';

  return (
    <AuthLayout>
      {/* Logo row */}
      <div className="mb-7 flex items-center gap-3">
        <img
          src={kronosLogo}
          alt="KRONOS"
          className="auth-logo-hover h-9 w-9 cursor-default"
        />
        <span className="text-sm font-bold tracking-[0.16em] text-[var(--text-primary)]">
          KRONOS
        </span>
      </div>

      <AnimatePresence mode="wait">
        {/* ─── STEP 1 — request code ─── */}
        {step === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            <div className="mb-8">
              <Link
                to="/login"
                className="mb-5 inline-flex items-center gap-2 text-sm text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
              >
                <ArrowLeft size={16} /> Back to login
              </Link>
              <h2 className="mb-1 text-2xl font-bold text-[var(--text-primary)]">Reset Password</h2>
              <p className="text-sm text-[var(--text-muted)]">
                Enter your email to receive a reset code
              </p>
            </div>

            <form onSubmit={handleRequestReset} className="space-y-5">
              {errorBanner}
              <div className="space-y-1">
                <label className="text-sm font-medium text-[var(--text-muted)]">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="auth-input w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 text-[var(--text-primary)] transition-colors"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className={btnPrimary}
                style={{ background: 'var(--accent-primary)', color: 'var(--button-text)' }}
              >
                {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Send Reset Code'}
              </button>
            </form>
          </motion.div>
        )}

        {/* ─── STEP 2 — OTP + new password ─── */}
        {step === 2 && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            <div className="mb-8">
              <h2 className="mb-1 text-2xl font-bold text-[var(--text-primary)]">New Password</h2>
              <p className="text-sm text-[var(--text-muted)]">
                Enter the code and your new password
              </p>
            </div>

            <form onSubmit={handleReset} className="space-y-6">
              {errorBanner}

              <div className="space-y-2">
                <label className="block text-center text-sm font-medium text-[var(--text-muted)]">
                  Verification Code
                </label>
                <OTPInput length={6} value={otp} onChange={setOtp} />
              </div>

              <div className="space-y-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium text-[var(--text-muted)]">New Password</label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="auth-input w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 text-[var(--text-primary)] transition-colors"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-[var(--text-muted)]">Confirm Password</label>
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className="auth-input w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 text-[var(--text-primary)] transition-colors"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || otp.length < 6}
                className={btnPrimary}
                style={{ background: 'var(--accent-primary)', color: 'var(--button-text)' }}
              >
                {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Reset Password'}
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </AuthLayout>
  );
}
