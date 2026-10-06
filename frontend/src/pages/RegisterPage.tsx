import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Eye, EyeOff, Loader2, ArrowRight } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../lib/axios';
import { AuthLayout } from '../components/AuthLayout';
import { OTPInput } from '../components/OTPInput';
import kronosLogo from '../assets/kronos-logo.svg';

export function RegisterPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [otp, setOtp] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);

  const navigate = useNavigate();

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    if (countdown > 0) timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const cleanEmail = email.trim().toLowerCase();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await api.post('/auth/register/request-otp', { email: cleanEmail });
      setStep(2);
      setCountdown(30);
      toast.success('Verification code sent to email');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otp.length < 6) return;
    setIsLoading(true);
    setError('');
    try {
      await api.post('/auth/register/check-otp', { email: cleanEmail, otp_code: otp.trim() });
      setStep(3);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid verification code');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) { setError('Passwords do not match'); return; }
    setIsLoading(true);
    setError('');
    try {
      await api.post('/auth/register/set-password', {
        email: cleanEmail, otp_code: otp.trim(), password, confirm_password: confirmPassword,
      });
      toast.success('Account verified successfully');
      navigate('/login');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid verification code');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    try {
      await api.post('/auth/resend-otp', { email: cleanEmail });
      setCountdown(30);
      toast.success('Verification code resent');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to resend verification code');
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
      <div className="mb-6 flex items-center justify-center gap-3">
        <img
          src={kronosLogo}
          alt="KRONOS"
          className="auth-logo-hover h-9 w-9 cursor-default"
        />
        <span className="text-base font-bold tracking-[0.16em] text-[var(--text-primary)]">
          KRONOS
        </span>
      </div>

      <div className="relative">
        <AnimatePresence mode="wait">
          {/* ─── STEP 1 — email ─── */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
            >
              <div className="mb-8">
                <h2 className="mb-1 text-2xl font-bold text-[var(--text-primary)]">
                  Create an account
                </h2>
                <p className="text-sm text-[var(--text-muted)]">Register for KRONOS access</p>
              </div>

              <form onSubmit={handleRegister} className="space-y-5">
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
                  {isLoading ? <Loader2 className="animate-spin" size={20} /> : <>Continue <ArrowRight size={18} /></>}
                </button>
              </form>

              <p className="mt-8 text-center text-sm text-[var(--text-muted)]">
                Already have an account?{' '}
                <Link to="/login" className="font-medium text-[var(--accent-primary)] hover:underline">Login</Link>
              </p>
            </motion.div>
          )}

          {/* ─── STEP 2 — OTP ─── */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
            >
              <div className="mb-8">
                <h2 className="mb-1 text-2xl font-bold text-[var(--text-primary)]">Verify email</h2>
                <p className="text-sm text-[var(--text-muted)]">
                  Enter the 6-digit code sent to {email}
                </p>
              </div>

              <form onSubmit={handleVerify} className="space-y-7">
                {errorBanner}
                <OTPInput length={6} value={otp} onChange={setOtp} />
                <div className="space-y-3">
                  <button
                    type="submit"
                    disabled={isLoading || otp.length < 6}
                    className={btnPrimary}
                    style={{ background: 'var(--accent-primary)', color: 'var(--button-text)' }}
                  >
                    {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Verify Account'}
                  </button>
                  <button
                    type="button"
                    disabled={countdown > 0}
                    onClick={handleResend}
                    className="w-full rounded-lg border border-[var(--border-color)] bg-transparent px-4 py-3 font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-primary)] disabled:opacity-50"
                  >
                    {countdown > 0 ? `Resend in ${countdown}s` : 'Resend Code'}
                  </button>
                </div>
              </form>
            </motion.div>
          )}

          {/* ─── STEP 3 — password ─── */}
          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
            >
              <div className="mb-8">
                <h2 className="mb-1 text-2xl font-bold text-[var(--text-primary)]">
                  Create your password
                </h2>
                <p className="text-sm text-[var(--text-muted)]">
                  Your email is verified. Set a password for KRONOS.
                </p>
              </div>

              <form onSubmit={handleSetPassword} className="space-y-5">
                {errorBanner}
                <div className="space-y-1">
                  <label className="text-sm font-medium text-[var(--text-muted)]">Password</label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="auth-input w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 pr-10 text-[var(--text-primary)] transition-colors"
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
                <div className="space-y-1">
                  <label className="text-sm font-medium text-[var(--text-muted)]">Confirm Password</label>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className="auth-input w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 text-[var(--text-primary)] transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isLoading}
                  className={btnPrimary}
                  style={{ background: 'var(--accent-primary)', color: 'var(--button-text)' }}
                >
                  {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Create Account'}
                </button>
              </form>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </AuthLayout>
  );
}
