import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '../../src/App';
createRoot(document.getElementById('root')!).render(<App closeModal={() => { (window as any).previewClosed = true; }} />);
