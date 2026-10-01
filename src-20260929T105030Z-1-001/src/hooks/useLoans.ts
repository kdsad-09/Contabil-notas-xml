// src/hooks/useLoans.ts
import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../services/supabaseClient';
import { useScope } from '../context/ScopeContext';
import type { Database } from '../types/supabase'; // optional typings

export interface Loan {
  id: string;
  descricao: string;
  valor_total: number;
  taxa_juros: number;
  total_parcelas: number;
  valor_parcela: number;
  data_inicio: string; // ISO date
  recorrencia_dia: number;
  escopo: 'pessoal' | 'familiar';
  status: string;
  categoria_id: number | null;
  created_at: string;
}

/**
 * Hook que devolve a lista de empréstimos filtrada pelo escopo atual.
 * Também fornece funções para criar/atualizar empréstimos.
 */
export const useLoans = () => {
  const { scope } = useScope();
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLoans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data, error } = await supabase
        .from('emprestimos')
        .select('*')
        .or(`escopo.eq.${scope},escopo.eq.consolidado`);
      if (error) throw error;
      setLoans(data as Loan[]);
    } catch (e: any) {
      setError(e.message || 'Erro ao buscar empréstimos');
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    fetchLoans();
  }, [fetchLoans]);

  // Cria um novo empréstimo e, após sucesso, refetch
  const createLoan = async (payload: Omit<Loan, 'id' | 'created_at'>) => {
    setLoading(true);
    setError(null);
    try {
      const { error } = await supabase.from('emprestimos').insert(payload);
      if (error) throw error;
      await fetchLoans();
    } catch (e: any) {
      setError(e.message || 'Erro ao criar empréstimo');
    } finally {
      setLoading(false);
    }
  };

  // Atualiza um empréstimo existente (parcialmente)
  const updateLoan = async (id: string, updates: Partial<Loan>) => {
    setLoading(true);
    setError(null);
    try {
      const { error } = await supabase
        .from('emprestimos')
        .update(updates)
        .eq('id', id);
      if (error) throw error;
      await fetchLoans();
    } catch (e: any) {
      setError(e.message || 'Erro ao atualizar empréstimo');
    } finally {
      setLoading(false);
    }
  };

  return { loans, loading, error, fetchLoans, createLoan, updateLoan };
};
