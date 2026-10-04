const isLocalDev = typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
  window.location.port === '4200';

export const environment = {
  production: false,
  apiUrl: isLocalDev ? 'http://localhost:8000/api' : '/api',
  stripePublishableKey: 'pk_test_51TbNoP8hCYSgZ3ixRXI1KgVdj7MAMAPcYSbIlVOMrN7D8UxBG2akaOBkmTg4aag1ETPs4TWiKt4lzSR0UOp89Sgt007NJPVlUF'
};
