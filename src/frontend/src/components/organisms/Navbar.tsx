import { UserButton } from '@clerk/clerk-react';
import { Eye, EyeOff } from 'lucide-react';
import { usePrivacy } from '../../contexts/PrivacyContext';

const Navbar = () => {
  const { isPrivacyMode, togglePrivacyMode } = usePrivacy();

  return (
    <header className="flex items-center justify-between p-4 bg-slate-950 border-b border-slate-800">
      <div className="text-white text-2xl font-bold">Valore365</div>
      <div className="flex items-center gap-4">
        <button onClick={togglePrivacyMode} className="text-slate-400 hover:text-white">
          {isPrivacyMode ? <EyeOff size={20} /> : <Eye size={20} />}
        </button>
        <UserButton />
      </div>
    </header>
  );
};

export default Navbar;
