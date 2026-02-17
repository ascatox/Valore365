import React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { usePrivacy } from '../contexts/PrivacyContext';

const PrivacyToggleButton: React.FC = () => {
  const { isPrivacyActive, togglePrivacy } = usePrivacy();

  return (
    <button onClick={togglePrivacy} className="focus:outline-none">
      {isPrivacyActive ? <EyeOff /> : <Eye />}
    </button>
  );
};

export default PrivacyToggleButton;
