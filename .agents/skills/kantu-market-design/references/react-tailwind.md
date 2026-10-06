# Kantu Market en React y Tailwind

## React / CSS global
1. Copia `assets/kantu-tokens.css` y `assets/kantu-components.css` a `src/styles/` e impórtalos una vez en el punto de entrada (`main.jsx` / `index.js`).
2. Crea componentes finos que solo aplican clases:
```jsx
export const Button = ({ variant = 'primary', size, block, ...p }) => (
  <button
    className={['btn', `btn--${variant}`, size && `btn--${size}`, block && 'btn--block'].filter(Boolean).join(' ')}
    {...p}
  />
);

export const RoleBadge = ({ role }) => {
  const map = { cliente: 'badge--cliente', empresa: 'badge--empresa', administrador: 'badge--admin' };
  return <span className={`badge ${map[role]}`}>{role}</span>;
};
```
3. Estado de pedido a badge: `{ pendiente: 'warning', entregado: 'success', cancelado: 'danger' }`.

## Tailwind (`tailwind.config.js`)
```js
export default {
  theme: {
    extend: {
      colors: {
        red:    { 50: '#FDECEE', 100: '#FAD1D6', 500: '#DC2640', 600: '#C8102E', 700: '#A50D26', 800: '#7F0A1E' },
        yellow: { 50: '#FFF8DB', 100: '#FFEFA8', 400: '#FFC933', 500: '#F5B301', 700: '#8A6200' },
        green:  { 50: '#E6F7EC', 100: '#C4EBD2', 500: '#1FA55A', 600: '#138A45', 700: '#0D6B35' },
        ink: '#1B1D24', muted: '#5F6675', line: '#E6E8EE', page: '#F6F7FA',
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      borderRadius: { md: '12px', lg: '20px' },
      boxShadow: {
        card: '0 1px 2px rgba(27,29,36,.06), 0 1px 3px rgba(27,29,36,.08)',
        pop: '0 18px 40px rgba(27,29,36,.14)',
        red: '0 8px 20px rgba(200,16,46,.28)',
      },
    },
  },
};
```
Clases típicas:
- Botón primario: `inline-flex min-h-10 items-center justify-center rounded-md bg-red-600 px-4 text-sm font-semibold text-white shadow-red hover:bg-red-700 focus-visible:ring-4 focus-visible:ring-yellow-500/45`
- Tarjeta: `rounded-md bg-white shadow-card overflow-hidden`
- Chip activo: `rounded-full bg-red-600 px-3 py-1.5 text-sm font-semibold text-white`
- Badge empresa: `rounded-full bg-yellow-50 px-2.5 py-0.5 text-xs font-bold text-yellow-700`

## Django / plantillas
Servir los dos CSS desde `static/` y cargarlos en `base.html` con `{% static %}`. Para el admin de Django, sobreescribir `admin/base_site.html` con `--primary: #C8102E` para que coincida con la marca.
