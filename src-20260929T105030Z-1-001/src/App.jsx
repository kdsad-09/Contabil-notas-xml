// src/App.jsx
import Header from './components/Header';
import Dashboard from './components/Dashboard';

function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      <Header />
      <main className="flex-1 p-4">
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
