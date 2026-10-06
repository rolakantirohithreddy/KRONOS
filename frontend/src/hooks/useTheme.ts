import { useSyncExternalStore } from 'react';

type Theme = 'dark' | 'light';

let theme: Theme = localStorage.getItem('kronos_theme') === 'light' ? 'light' : 'dark';
const listeners = new Set<() => void>();

function setTheme(nextTheme: Theme) {
  theme = nextTheme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('kronos_theme', theme);
  listeners.forEach((listener) => listener());
}

document.documentElement.setAttribute('data-theme', theme);

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const currentTheme = useSyncExternalStore(subscribe, () => theme, () => theme);
  const toggleTheme = () => setTheme(currentTheme === 'dark' ? 'light' : 'dark');

  return { theme: currentTheme, toggleTheme };
}
