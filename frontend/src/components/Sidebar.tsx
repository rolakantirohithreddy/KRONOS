import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Shield, Cpu, Settings, LogOut } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

export function Sidebar() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const navItems = [
    { to: '/dashboard', icon: <LayoutDashboard size={20} />, label: 'Dashboard' },
    { to: '/devices', icon: <Cpu size={20} />, label: 'Devices' },
    { to: '/settings', icon: <Settings size={20} />, label: 'Settings' },
  ];

  return (
    <aside className="hidden h-screen w-64 shrink-0 flex-col border-r border-[var(--border-color)] bg-[var(--bg-surface)] md:flex">
      <div className="flex items-center gap-3 border-b border-[var(--border-color)] px-6 py-5">
        <Shield className="text-[var(--accent-primary)]" size={28} />
        <span className="text-xl font-bold tracking-widest text-[var(--text-primary)]">KRONOS</span>
      </div>
      
      <nav className="mt-5 flex flex-1 flex-col gap-1 px-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md border-l-2 px-4 py-3 transition-colors ${
                isActive
                  ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]'
                  : 'border-transparent text-[var(--text-muted)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]'
              }`
            }
          >
            {item.icon}
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-[var(--border-color)] p-3">
        <button
          onClick={() => {
            logout();
            navigate('/login', { replace: true });
          }}
          className="flex w-full items-center gap-3 rounded-md px-4 py-3 text-[var(--text-muted)] transition-colors hover:bg-red-500/10 hover:text-red-500"
        >
          <LogOut size={20} />
          <span className="font-medium">Logout</span>
        </button>
      </div>
    </aside>
  );
}
