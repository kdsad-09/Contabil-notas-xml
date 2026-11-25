import { createContext, useContext, useState, ReactNode, Dispatch, SetStateAction } from 'react';

export type ScopeOption = 'pessoal' | 'familiar' | 'consolidado';

interface ScopeContextProps {
  scope: ScopeOption;
  setScope: Dispatch<SetStateAction<ScopeOption>>;
}

const ScopeContext = createContext<ScopeContextProps | undefined>(undefined);

export const ScopeProvider = ({ children }: { children: ReactNode }) => {
  const [scope, setScope] = useState<ScopeOption>('consolidado');
  return (
    <ScopeContext.Provider value={{ scope, setScope }}>
      {children}
    </ScopeContext.Provider>
  );
};

export const useScope = (): ScopeContextProps => {
  const ctx = useContext(ScopeContext);
  if (!ctx) {
    throw new Error('useScope must be used within a ScopeProvider');
  }
  return ctx;
};
