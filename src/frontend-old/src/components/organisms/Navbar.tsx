import { FiMenu } from 'react-icons/fi';

const Navbar = ({ toggleSidebar }) => {
  return (
    <header className="flex items-center justify-between p-4 bg-slate-950 border-b border-slate-800">
      <div className="flex items-center">
        <button onClick={toggleSidebar} className="text-white mr-4">
          <FiMenu size={24} />
        </button>
      </div>
      {/* Placeholder for future Navbar items like search or user profile */}
      <div></div>
    </header>
  );
};

export default Navbar;
