const isLocalDev = typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
  window.location.port === '4200';

export const environment = {
  production: false,
  apiUrl: isLocalDev ? 'http://localhost:8000/api' : '/api'
};
