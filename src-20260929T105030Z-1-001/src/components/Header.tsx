// src/components/Header.tsx
import { useScope } from '@/context/ScopeContext';
import { Moon, Sun } from 'lucide-react';

export const Header = () => {
  const { scope, setScope } = useScope();

  const toggleDark = () => {
    document.documentElement.classList.toggle('dark');
  };

  return (
    <header className="flex items-center justify-between p-4 bg-gray-800 text-white dark:bg-gray-900">
      <h1 className="text-2xl font-bold">Finanças Dark</h1>

      {/* Scope selector (global) */}
      <select
        value={scope}
        onChange={(e) => setScope(e.target.value as any)}
        className="rounded bg-gray-700 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 px-2 py-1"
      >
        <option value="pessoal">Pessoal</option>
        <option value="familiar">Familiar</option>
        <option value="consolidado">Consolidado</option>
      </select>

      {/* Dark‑mode toggle */}
      <button
        onClick={toggleDark}
        className="ml-4 p-2 rounded hover:bg-gray-700"
        aria-label="Toggle dark mode"
      >
        {document.documentElement.classList.contains('dark') ? (
          <Sun size={20} className="text-yellow-400" />
        ) : (
          <Moon size={20} className="text-gray-300" />
        )}
      </button>
    </header>
  );
};

export default Header;

