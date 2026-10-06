import { useState, useRef, KeyboardEvent, ClipboardEvent } from 'react';

interface OTPInputProps {
  length?: number;
  value: string;
  onChange: (value: string) => void;
}

export function OTPInput({ length = 6, value, onChange }: OTPInputProps) {
  const [activeInput, setActiveInput] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const focusInput = (index: number) => {
    const target = Math.max(0, Math.min(length - 1, index));
    inputRefs.current[target]?.focus();
    setActiveInput(target);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>, index: number) => {
    const val = e.target.value.replace(/\D/g, '');
    if (!val) return;
    
    const newVal = value.substring(0, index) + val[val.length - 1] + value.substring(index + 1);
    onChange(newVal.slice(0, length));
    
    if (index < length - 1) {
      focusInput(index + 1);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      const newVal = value.substring(0, index) + ' ' + value.substring(index + 1);
      onChange(newVal.trimEnd());
      if (index > 0) focusInput(index - 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      if (index > 0) focusInput(index - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      if (index < length - 1) focusInput(index + 1);
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text/plain').replace(/\D/g, '').slice(0, length);
    if (pastedData) {
      onChange(pastedData.padEnd(length, ' '));
      focusInput(Math.min(pastedData.length, length - 1));
    }
  };

  return (
    <div className="flex gap-2 justify-center">
      {Array.from({ length }).map((_, i) => (
        <input
          key={i}
          ref={(el) => (inputRefs.current[i] = el)}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={value[i] && value[i] !== ' ' ? value[i] : ''}
          onChange={(e) => handleChange(e, i)}
          onKeyDown={(e) => handleKeyDown(e, i)}
          onPaste={handlePaste}
          onFocus={() => setActiveInput(i)}
          className={`w-12 h-14 text-center text-xl font-mono bg-[var(--bg-surface)] border-2 rounded-md outline-none transition-colors ${
            activeInput === i
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)]'
              : 'border-[var(--border-color)] text-[var(--text-primary)]'
          }`}
        />
      ))}
    </div>
  );
}
