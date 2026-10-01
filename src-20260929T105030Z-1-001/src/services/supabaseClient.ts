import { createClient } from '@supabase/supabase-js';

// Vite env variables (prefix VITE_ required)
// .env (na raiz) →
// VITE_SUPABASE_URL=https://xyzcompany.supabase.co
// VITE_SUPABASE_ANON_KEY=public-anon-key

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);
