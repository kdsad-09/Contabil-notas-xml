// src/components/Dashboard.tsx
import { useEffect, useState } from 'react';
import { useTransactions } from '@/hooks/useTransactions';
import { useLoans } from '@/hooks/useLoans';
import { useCategories } from '@/hooks/useCategories';
import { useScope } from '@/context/ScopeContext';
import { supabase } from '@/services/supabaseClient';
import { Calendar, CreditCard, DollarSign, ArrowUpDown } from 'lucide-react';

// Helpers --------------------------------------------------------------
const sum = (arr: number[]) => arr.reduce((a, b) => a + b, 0);

export const Dashboard = () => {
  const { scope } = useScope();
  const { transactions, loading: txLoading, error: txError, addTransaction } = useTransactions();
  const { loans, loading: loansLoading } = useLoans();
  const { categories, loading: catLoading } = useCategories();

  // ---- cálculo de resumo -------------------------------------------
  const entradas = transactions.filter((t) => t.tipo === 'entrada');
  const saidas = transactions.filter((t) => t.tipo === 'saida');
  const totalEntradas = sum(entradas.map((t) => Number(t.valor)));
  const totalSaidas = sum(saidas.map((t) => Number(t.valor)));
  const saldoAtual = totalEntradas - totalSaidas;

  // ---- parcelas a vencer neste mês ---------------------------------
  const [parcelasVencendo, setParcelasVencendo] = useState<number>(0);
  const [parcelasLoading, setParcelasLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchParcelas = async () => {
      setParcelasLoading(true);
      const hoje = new Date();
      const inicioMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
      const fimMes = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0);
      const { data, error } = await supabase
        .from('parcelas')
        .select('valor')
        .gte('data_vencimento', inicioMes.toISOString().slice(0, 10))
        .lte('data_vencimento', fimMes.toISOString().slice(0, 10))
        .eq('status', 'pendente');
      if (error) {
        console.error('Erro ao buscar parcelas', error);
        setParcelasVencendo(0);
      } else {
        const total = sum((data as any[]).map((p) => Number(p.valor)));
        setParcelasVencendo(total);
      }
      setParcelasLoading(false);
    };
    fetchParcelas();
  }, [loans]); // refaz quando empréstimos mudam

  // ---- formulário rápido de transação ------------------------------
  const [form, setForm] = useState({
    descricao: '',
    valor: '',
    tipo: 'entrada' as 'entrada' | 'saida',
    categoria_id: '' as string | number,
    data: new Date().toISOString().slice(0, 10),
    observacoes: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await addTransaction({
        descricao: form.descricao,
        valor: Number(form.valor),
        tipo: form.tipo,
        escopo: scope,
        categoria_id: form.categoria_id ? Number(form.categoria_id) : null,
        data: form.data,
        observacoes: form.observacoes || null,
        parcela_id: null,
      });
      // limpa formulário
      setForm({
        descricao: '',
        valor: '',
        tipo: 'entrada',
        categoria_id: '' as any,
        data: new Date().toISOString().slice(0, 10),
        observacoes: '',
      });
    } catch (err) {
      console.error('Erro ao salvar transação', err);
    }
    setSubmitting(false);
  };

  // ---------------------------------------------------------------
  return (
    <div className="p-6 space-y-8">
      {/* Cards de resumo */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Saldo Atual */}
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-xl p-4 shadow-lg">
          <div className="flex items-center">
            <ArrowUpDown className="w-6 h-6 mr-2" />
            <h3 className="font-semibold">Saldo Atual</h3>
          </div>
          <p className="mt-2 text-2xl font-bold">
            R$ {saldoAtual.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
        </div>
        {/* Entradas */}
        <div className="bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-xl p-4 shadow-lg">
          <div className="flex items-center">
            <CreditCard className="w-6 h-6 mr-2" />
            <h3 className="font-semibold">Entradas</h3>
          </div>
          <p className="mt-2 text-2xl font-bold">
            R$ {totalEntradas.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
        </div>
        {/* Saídas */}
        <div className="bg-gradient-to-r from-red-500 to-pink-600 text-white rounded-xl p-4 shadow-lg">
          <div className="flex items-center">
            <DollarSign className="w-6 h-6 mr-2" />
            <h3 className="font-semibold">Saídas</h3>
          </div>
          <p className="mt-2 text-2xl font-bold">
            R$ {totalSaidas.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
        </div>
        {/* Parcelas a Vencer */}
        <div className="bg-gradient-to-r from-yellow-500 to-amber-600 text-white rounded-xl p-4 shadow-lg">
          <div className="flex items-center">
            <Calendar className="w-6 h-6 mr-2" />
            <h3 className="font-semibold">Parcelas a Vencer (mês)</h3>
          </div>
          <p className="mt-2 text-2xl font-bold">
            {parcelasLoading ? '...' : `R$ ${parcelasVencendo.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`}
          </p>
        </div>
      </div>

      {/* Formulário rápido */}
      <section className="bg-gray-100 dark:bg-gray-800 rounded-xl p-6 shadow-md">
        <h2 className="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-200">
          Nova Transação Rápida
        </h2>
        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <input
            name="descricao"
            value={form.descricao}
            onChange={handleChange}
            required
            placeholder="Descrição"
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <input
            name="valor"
            type="number"
            step="0.01"
            value={form.valor}
            onChange={handleChange}
            required
            placeholder="Valor"
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <select
            name="tipo"
            value={form.tipo}
            onChange={handleChange}
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="entrada">Entrada</option>
            <option value="saida">Saída</option>
          </select>
          <select
            name="categoria_id"
            value={form.categoria_id}
            onChange={handleChange}
            disabled={catLoading}
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
          <input
            name="data"
            type="date"
            value={form.data}
            onChange={handleChange}
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <textarea
            name="observacoes"
            value={form.observacoes}
            onChange={handleChange}
            placeholder="Observações (opcional)"
            className="p-2 rounded border focus:outline-none focus:ring-2 focus:ring-indigo-500 md:col-span-2 lg:col-span-3"
          />
          <button
            type="submit"
            disabled={submitting}
            className="col-span-1 md:col-span-2 lg:col-span-1 bg-indigo-600 hover:bg-indigo-700 text-white py-2 px-4 rounded disabled:opacity-50"
          >
            {submitting ? 'Salvando…' : 'Adicionar'}
          </button>
        </form>
        {txError && <p className="mt-2 text-red-600">{txError}</p>}
      </section>
    </div>
  );
};

export default Dashboard;
