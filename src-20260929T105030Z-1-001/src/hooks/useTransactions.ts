// src/hooks/useTransactions.ts
import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../services/supabaseClient';
import { useScope } from '../context/ScopeContext';

type Transaction = {
  id: string;
  descricao: string;
  valor: number;
  tipo: 'entrada' | 'saida';
  escopo: 'pessoal' | 'familiar';
  categoria_id: number | null;
  data: string; // ISO date
  observacoes?: string | null;
  parcela_id?: string | null;
  created_at: string;
};

export const useTransactions = () => {
  const { scope } = useScope();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let query = supabase.from<Transaction>('transacoes').select('*');
      if (scope !== 'consolidado') {
        query = query.eq('escopo', scope);
      }
      const { data, error: supabaseError } = await query.order('data', { ascending: false });
      if (supabaseError) throw supabaseError;
      setTransactions(data ?? []);
    } catch (e: any) {
      setError(e.message ?? 'Erro ao buscar transações');
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const addTransaction = async (payload: Omit<Transaction, 'id' | 'created_at'>) => {
    setLoading(true);
    setError(null);
    try {
      const { data, error: supabaseError } = await supabase
        .from<Transaction>('transacoes')
        .insert([payload])
        .single();
      if (supabaseError) throw supabaseError;
      // Refresh list after successful insert
      await fetchTransactions();
      return data;
    } catch (e: any) {
      setError(e.message ?? 'Erro ao criar transação');
      throw e;
    } finally {
      setLoading(false);
    }
  };

  const updateTransaction = async (id: string, updates: Partial<Transaction>) => {
    setLoading(true);
    setError(null);
    try {
      const { data, error: supabaseError } = await supabase
        .from<Transaction>('transacoes')
        .update(updates)
        .eq('id', id)
        .single();
      if (supabaseError) throw supabaseError;
      await fetchTransactions();
      return data;
    } catch (e: any) {
      setError(e.message ?? 'Erro ao atualizar transação');
      throw e;
    } finally {
      setLoading(false);
    }
  };

  const deleteTransaction = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const { error: supabaseError } = await supabase.from('transacoes').delete().eq('id', id);
      if (supabaseError) throw supabaseError;
      await fetchTransactions();
    } catch (e: any) {
      setError(e.message ?? 'Erro ao remover transação');
      throw e;
    } finally {
      setLoading(false);
    }
  };

  return {
    transactions,
    loading,
    error,
    fetchTransactions,
    addTransaction,
    updateTransaction,
    deleteTransaction,
  };
};
