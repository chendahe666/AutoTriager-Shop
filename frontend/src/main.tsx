import React from 'react';
import ReactDOM from 'react-dom/client';
import { Workbench } from './Workbench';
import { InvestigationApp } from './LiveDesk';
import './style.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><InvestigationApp apiBase="/api" historical={<Workbench apiBase="/api" />} /></React.StrictMode>
);
