// src/hooks/useCategories.ts
import { useState, useEffect } from 'react';
import { supabase } from '../services/supabaseClient';

export type Category = {
  id: number;
  nome: string;
  tipo: 'entrada' | 'saida' | 'ambos' | null;
  cor?: string | null;
};

export const useCategories = () => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCategories = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data, error: supabaseError } = await supabase
        .from('categorias')
        .select('*')
        .order('nome', { ascending: true });

      if (supabaseError) throw supabaseError;
      setCategories(data ?? []);
    } catch (e: any) {
      setError(e.message ?? 'Erro ao buscar categorias');
      setCategories([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCategories();
  }, []);

  const addCategory = async (payload: Omit<Category, 'id'>) => {
    const { data, error: supabaseError } = await supabase
      .from('categorias')
      .insert([payload])
      .select()
      .single();
    if (supabaseError) throw supabaseError;
    await fetchCategories();
    return data;
  };

  return { categories, loading, error, fetchCategories, addCategory };
};
