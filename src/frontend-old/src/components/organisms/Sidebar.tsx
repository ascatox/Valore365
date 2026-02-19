import { Link, useLocation } from 'react-router-dom';
import { FiBarChart2, FiLayers, FiPlusCircle, FiHome } from 'react-icons/fi';

const navLinks = [
  { to: '/', icon: FiBarChart2, label: 'Panoramica' },
  { to: '/holdings', icon: FiLayers, label: 'Partecipazioni' },
  { to: '/add-asset', icon: FiPlusCircle, label: 'Aggiungi Asset' }, // Kept for functionality
];

const Sidebar = ({ isOpen }) => {
  const location = useLocation();

  return (
    <div className={`bg-slate-900 border-r border-slate-800 text-slate-300 transition-all duration-300 ${isOpen ? 'w-64' : 'w-20'}`}>
      <div className="flex items-center justify-center h-16 border-b border-slate-800">
        <Link to="/">
          <FiHome className="text-2xl text-white" />
        </Link>
      </div>
      <nav className="mt-4">
        <ul>
          {navLinks.map(({ to, icon: Icon, label }) => {
            const isActive = location.pathname === to;
            return (
              <li key={to} className="px-4 py-2">
                <Link
                  to={to}
                  className={`flex items-center p-2 rounded-md transition-colors ${isActive ? 'bg-slate-700 text-white' : 'hover:bg-slate-800'}`}>
                  <Icon className={`text-xl ${isOpen ? 'mr-4' : 'mx-auto'}`} />
                  <span className={`${!isOpen && 'hidden'}`}>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
};

export default Sidebar;
