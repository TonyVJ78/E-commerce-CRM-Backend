---
name: kantu-market-design
description: Sistema de diseño frontend para Kantu Market, un e-commerce / marketplace boliviano multi-tienda con paleta rojo, amarillo y verde. Úsala SIEMPRE que el usuario pida crear, rediseñar, maquetar o mejorar cualquier pantalla, componente, página o estilo de Kantu Market o de un e-commerce con su misma identidad - catálogo, tarjetas de producto, carrito, checkout, login/registro, panel del vendedor (empresa), panel del administrador, tablas, formularios, dashboards, badges, filtros, navbar, hero. También cuando mencione "mi frontend", "colores del proyecto", "que se vea profesional/limpio", aunque no diga "skill" ni "Kantu".
---

# Kantu Market – Sistema de diseño

Interfaz profesional, limpia y cómoda para un marketplace boliviano. Mucho blanco, un solo rojo protagonista, amarillo como acento puntual y verde para todo lo que "está bien". Prioridad: claridad al comprar y al administrar, no decoración.

## Principios rectores
1. **Densidad equilibrada:** nada de pantallas desiertas. En escritorio (1024–1440 px) organiza paneles con Bento Grid de 12 columnas (`.layout` + `.bento` + `.col-*`) en vez de columnas angostas aisladas.
2. **Cero emojis:** solo iconos SVG de trazo (Lucide/Heroicons outline, clase `.icon`) o texto.
3. **Tres estados obligatorios** en todo listado o bloque con datos: carga (skeleton), vacío (icono + acción) y error (qué pasó + cómo resolverlo).
4. **Sin dependencias CSS pesadas:** variables nativas de `kantu-tokens.css` y estilos por componente. Tailwind y Bootstrap no hacen falta.
5. **Accesibilidad WCAG AA:** contraste 4.5:1, foco visible, `aria-label` en botones de icono.

## Concepto de marca
"Kantu" remite a la cantuta, flor nacional de Bolivia, y la paleta rojo-amarillo-verde es la de la bandera. Úsalo con sobriedad: **rojo = marca y acción principal**, **amarillo = destacar/atención**, **verde = éxito, stock, confirmación**. Nunca uses los tres con el mismo peso en una misma pantalla: 70% neutros, 20% rojo, 10% amarillo + verde.

## Archivos de la skill
- `assets/kantu-tokens.css`: variables (colores, tipografía, espaciado, radios, sombras) + reset. **Cópialo tal cual al proyecto.**
- `assets/kantu-components.css`: CSS listo de navbar, botones, hero, búsqueda, filtros, chips, badges, tarjeta de producto, formularios, auth, KPIs, gráfico de barras, tablas, alertas, estado vacío, FAB, skeleton.
- `references/componentes.md`: HTML de cada componente y recetas por pantalla.
- `references/angular.md`: reglas de código Angular 19 (standalone, `@if`/`@for`, signals, `inject()`), los tres estados y ejemplos.
- `references/react-tailwind.md`: alternativa para React o Tailwind.

Flujo: lee este archivo; si vas a escribir markup, lee `references/componentes.md`; si el proyecto es Angular, lee `references/angular.md`; si usa React o Tailwind, lee `references/react-tailwind.md`. Reutiliza las clases existentes antes de inventar nuevas.

## Colores

| Rol | Token | Hex | Uso |
|---|---|---|---|
| Primario | `--red-600` | `#C8102E` | Botón principal, enlaces, chip activo, logo, FAB |
| Primario hover | `--red-700` | `#A50D26` | Hover/pressed |
| Rojo suave | `--red-50` | `#FDECEE` | Fondos de badge admin, error, hover de outline |
| Acento | `--yellow-500` | `#F5B301` | Subrayado de nav activo, estrellas, oferta, mejor día, focus ring |
| Amarillo suave | `--yellow-50` | `#FFF8DB` | Fondo de aviso, badge empresa |
| Éxito | `--green-600` | `#138A45` | Stock disponible, pedido entregado, ingresos, botón de confirmar |
| Verde suave | `--green-50` | `#E6F7EC` | Fondo de badge cliente/éxito |
| Título | `--ink` | `#1B1D24` | Encabezados y precios |
| Cuerpo | `--text` / `--muted` | `#3A3F4B` / `#5F6675` | Texto / secundario |
| Fondo | `--bg` / `--surface` | `#F6F7FA` / `#FFFFFF` | Página / tarjetas |

Reglas:
- Texto sobre amarillo siempre `--ink` (nunca blanco). Texto amarillo sobre fondo claro usa `--yellow-700`, no `--yellow-500`.
- Texto verde sobre fondo claro usa `--green-700`.
- Gradiente de marca (`--grad-brand`) solo en el logo. Gradiente rojo (`--grad-hero`) solo en hero y botón primario.
- El rojo de acción NO se usa para errores sin icono o texto: el error siempre lleva mensaje.
- Un solo botón primario rojo por vista; el resto `outline` o `ghost`.

### Color por rol de usuario
| Rol | Badge | Color |
|---|---|---|
| Cliente | `badge--cliente` | Verde |
| Empresa (vendedor) | `badge--empresa` | Amarillo |
| Administrador | `badge--admin` | Rojo |

### Estados de pedido
Pendiente → amarillo · Pagado / En preparación → neutro · Enviado → neutro con borde · Entregado → verde · Cancelado / Rechazado → rojo.

### Stock
Más de 10 → verde "Disponible" · 1–10 → amarillo "Quedan N" · 0 → rojo "Agotado" (botón deshabilitado).

## Tipografía
- Familia única: **Inter** (400, 500, 600, 700, 800). Fallback `system-ui`.
- Escala: 12 / 14 / 16 / 18 / 22 / 28 / 36 px; hero fluido `clamp(2rem, 4vw+1rem, 3.25rem)`.
- Títulos 700–800, interlineado 1.2, `letter-spacing: -.015em`. Cuerpo 400–500, interlineado 1.55.
- Precios y cifras: `font-variant-numeric: tabular-nums`, peso 800. Moneda con formato boliviano: `Bs 1.250,00` o el formato ya usado en el proyecto, pero consistente en todas las pantallas.
- Etiquetas pequeñas en mayúsculas solo en KPIs y encabezados de tabla.
- Largo de línea máximo ~70 caracteres en textos corridos.

## Espaciado, radios y sombras
- Base de 4 px: 4, 8, 12, 16, 24, 32, 48, 64.
- Radios con jerarquía: inputs/chips pequeños 8 · botones y tarjetas de producto 12 · paneles, login, modales 20 · chips, badges, búsqueda píldora.
- Sombras: `--sh-1` reposo, `--sh-2` filtros/hover suave, `--sh-3` modales/login/hero, `--sh-red` solo botón primario.
- Contenedor máximo 1120 px, centrado, 16 px de margen lateral en móvil.

## Layout por pantalla

### Cliente: catálogo
1. Navbar blanca: logo · Catálogo · Mis pedidos · Carrito (botón outline con contador) · nombre + badge verde · Cerrar sesión.
2. Hero rojo: etiqueta, título, subtítulo, búsqueda píldora.
3. Panel de filtros blanco que se superpone al hero: contador de resultados, orden, chips de Tienda y de Categoría (scroll horizontal en móvil).
4. Grilla de productos `auto-fill, minmax(240px, 1fr)`.
5. FAB rojo de ayuda abajo a la derecha.

Tarjeta de producto: imagen 4:3, tienda y categoría como tags sobre la imagen, título a 2 líneas, precio grande, stock, botón "Agregar al carrito". Mostrar siempre precio y stock sin necesidad de hover.

### Login y registro
Tarjeta centrada de 420 px sobre fondo con dos halos suaves (rojo y amarillo). Logo, subtítulo, campos con etiqueta arriba, botón primario a ancho completo, enlaces secundarios abajo. El botón nunca se ve "apagado" salvo que esté realmente deshabilitado: en la captura actual se ve desvaído, corrígelo con `.btn--primary` normal y deshabilitado solo mientras envía.

### Empresa: panel del vendedor
- Navbar con: Panel vendedor · Mis tiendas · Inventario · Pedidos recibidos · Identidad de marca + badge amarillo "Empresa".
- Título de página y subtítulo corto.
- Bento: 4 KPIs `col-3` (con icono y tendencia si hay dato), gráfico en `col-8`, stock bajo o últimos pedidos en `col-4`.
- KPIs: Ingresos (verde), Pedidos pendientes (amarillo), Total pedidos (rojo), Productos activos, Bajo stock (rojo si > 0, verde "Inventario saludable" si 0).
- Gráfico de barras de 7 días: barras rojas, la de mejor día en amarillo, valor encima y fecha debajo. Etiqueta del eje "dd/mm".
- Debajo: tabla de últimos pedidos con acción "Ver detalle".

### Administrador: panel de control
- Navbar con: Dashboard · Auditoría · Roles y permisos · Backups · Django Admin + badge rojo "Administrador".
- Encabezado con título, subtítulo y `status` verde "Sistema operativo". Luego Bento Grid de módulos (`.card` con cabecera). Antes: 4 `tile` de acceso (Bitácora, Roles, Backups, Django Admin). Evita duplicar el mismo destino en tarjeta, enlace y botón: elige tarjeta clicable completa + un botón primario por tarea frecuente.
- Para listados (bitácora, usuarios) usa `table-wrap` con búsqueda, filtros por chips y paginación.

## Componentes clave (resumen)
Detalle y HTML en `references/componentes.md`.
- **Botón**: primario (rojo), outline, ghost, éxito (verde), acento (amarillo). Alto mínimo 40 px (48 en móvil para acciones críticas).
- **Chip**: filtro. Activo = rojo sólido con texto blanco.
- **Badge**: estado/rol. Fondo suave + texto oscuro del mismo tono.
- **Input**: fondo `--surface-2`, al enfocar fondo blanco + anillo amarillo. Error: borde rojo + mensaje bajo el campo.
- **KPI**: borde izquierdo de 4 px con el color de su significado, icono en caja suave y tendencia opcional.
- **Card**: `.card` con `card__header` y `card__body`; si es clicable, `a.card`.
- **Badge con punto**: `badge__dot` para estados de pedido y sistema.
- **Tabla**: encabezado gris claro, filas con hover, números alineados a la derecha.
- **Alerta/Toast**: verde éxito, amarillo aviso, rojo error; siempre texto + color.
- **Estado vacío**: título + una acción ("Aún no tienes pedidos. Ver catálogo").
- **Skeleton**: para carga de tarjetas y tablas, nunca pantalla en blanco.

## Textos (español, tono boliviano neutro)
- Sentence case, verbos claros: "Agregar al carrito", "Guardar cambios", "Confirmar pedido". Evita "Submit/OK".
- Misma acción, mismo nombre en todo el flujo: si el botón dice "Guardar", el aviso dice "Guardado".
- Errores: qué pasó + cómo arreglarlo. "El correo o la contraseña no coinciden. Revisa e intenta de nuevo."
- Sin emojis como iconos de interfaz (en las capturas actuales hay emojis en la búsqueda, filtros y botón Carrito "[Carrito]"). Reemplázalos por un set de iconos SVG coherente (Lucide o Heroicons, trazo 1.75 px).
- No mostrar textos técnicos al usuario final ("multitenant", "/admin/") salvo en el panel de administración.

## Accesibilidad y calidad mínima
- Contraste mínimo 4.5:1 en texto. Blanco sobre `--red-600` cumple; blanco sobre `--yellow-500` NO.
- Foco visible siempre (anillo amarillo `--focus-ring`). No quites `outline` sin reemplazarlo.
- Objetivos táctiles de al menos 40×40 px.
- El color nunca es el único indicador: acompáñalo de texto o icono (stock, estado, error).
- `alt` descriptivo en imágenes de producto; `aria-label` en botones solo-icono; `aria-current="page"` en el enlace activo.
- Respeta `prefers-reduced-motion` (ya incluido en tokens).
- Responsive: probar 360, 768 y 1280 px. La grilla de productos baja a 1–2 columnas; tablas con scroll horizontal; navbar con scroll o menú hamburguesa.
- Movimiento solo como respuesta a acciones (hover de tarjeta con elevación leve, abrir carrito). Sin animaciones decorativas al cargar.

## Qué evitar
- Más de un botón rojo relleno compitiendo en la misma zona.
- Amarillo como color de texto sobre blanco.
- Gradientes en tarjetas, tablas o fondos de página.
- Sombras fuertes en todas las tarjetas; usa `--sh-1` en reposo.
- Chips o badges con colores arbitrarios fuera de la paleta.
- Mezclar radios al azar; respeta la jerarquía de radios.
- Texto de menos de 12 px.

## Checklist antes de entregar
1. ¿Usa solo variables de `kantu-tokens.css` (sin hex sueltos)?
2. ¿Hay un único botón primario por vista?
3. ¿Stock, estado y rol usan el color correcto y llevan texto?
4. ¿Hay estados de carga, vacío y error?
5. ¿Foco visible, contraste correcto, responsive a 360 px?
6. ¿Los textos están en español, claros y consistentes?
