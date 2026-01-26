/**
 * Onboarding Visualizations - Demo Page
 *
 * This page allows viewing all 3 visualization options for the onboarding wizard.
 * Navigate between options using the tabs at the top.
 */

import { useState } from 'react';
import OptionA_CardStack from './OptionA_CardStack';
import OptionB_ChatStyle from './OptionB_ChatStyle';
import OptionC_Progressive from './OptionC_Progressive';
import './visualizations.css';

type Option = 'A' | 'B' | 'C';

export default function OnboardingVisualizations() {
  const [activeOption, setActiveOption] = useState<Option>('A');

  return (
    <div style={{ minHeight: '100vh', background: '#030712' }}>
      {/* Option Selector */}
      <div
        style={{
          position: 'fixed',
          top: '20px',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 2000,
          display: 'flex',
          gap: '8px',
          background: 'rgba(9, 15, 31, 0.95)',
          backdropFilter: 'blur(12px)',
          padding: '8px',
          borderRadius: '999px',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        {(['A', 'B', 'C'] as Option[]).map((option) => (
          <button
            key={option}
            onClick={() => setActiveOption(option)}
            style={{
              background: activeOption === option ? '#f97316' : 'transparent',
              color: activeOption === option ? 'white' : '#94a3b8',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '999px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              fontFamily: "'Space Grotesk', sans-serif",
            }}
          >
            Option {option}:{' '}
            {option === 'A' && 'Card Stack'}
            {option === 'B' && 'Chat Style'}
            {option === 'C' && 'Progressive'}
          </button>
        ))}
      </div>

      {/* Visualization */}
      {activeOption === 'A' && <OptionA_CardStack />}
      {activeOption === 'B' && <OptionB_ChatStyle />}
      {activeOption === 'C' && <OptionC_Progressive />}
    </div>
  );
}

// Export individual options for direct use
export { default as OptionA_CardStack } from './OptionA_CardStack';
export { default as OptionB_ChatStyle } from './OptionB_ChatStyle';
export { default as OptionC_Progressive } from './OptionC_Progressive';
