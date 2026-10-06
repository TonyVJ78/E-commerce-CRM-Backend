# Componentes Kantu Market – HTML de referencia

Todos usan clases de `assets/kantu-components.css`.

## Navbar
```html
<header class="nav">
  <div class="container nav__inner">
    <a class="logo" href="/">Kantu Market</a>
    <nav class="nav__links" aria-label="Principal">
      <a class="nav__link is-active" aria-current="page" href="/catalogo">Catálogo</a>
      <a class="nav__link" href="/pedidos">Mis pedidos</a>
      <a class="btn btn--outline" href="/carrito">Carrito (2)</a>
      <span class="badge badge--cliente">Cliente</span>
      <button class="btn btn--outline">Cerrar sesión</button>
    </nav>
  </div>
</header>
```

## Hero + búsqueda
```html
<section class="hero">
  <div class="container">
    <span class="hero__tag">Mercado digital boliviano</span>
    <h1>Explora lo mejor de nuestras tiendas</h1>
    <p>Textiles de alpaca, gastronomía tradicional y artesanías directo de productores bolivianos.</p>
    <form class="search" role="search">
      <input type="search" placeholder="Busca por producto, café, aguayo, cerámica…" aria-label="Buscar productos">
      <button class="btn btn--primary">Buscar</button>
    </form>
  </div>
</section>
```

## Filtros
```html
<section class="container">
  <div class="filters">
    <div class="filters__row">
      <button class="btn btn--ghost">Filtros avanzados</button>
      <span>25 productos encontrados</span>
    </div>
    <div class="filters__row" style="margin-top:12px">
      <span class="filters__label">Tienda</span>
      <button class="chip is-active">Todas las tiendas</button>
      <button class="chip">Moda Altoperuana</button>
      <button class="chip">Sabores de Bolivia</button>
    </div>
  </div>
</section>
```

## Tarjeta de producto
```html
<article class="product">
  <div class="product__media">
    <img src="..." alt="Quinua real pop tostada">
    <div class="product__tags">
      <span class="badge badge--neutral">Sabores de Bolivia</span>
      <span class="badge badge--offer">-15%</span>
    </div>
  </div>
  <div class="product__body">
    <span class="product__store">Snacks y granos</span>
    <h3 class="product__title">Quinua Real Pop Tostada</h3>
    <div class="stars" aria-label="4 de 5 estrellas">★★★★☆</div>
    <div class="product__price">Bs 25,00 <span class="product__old">Bs 29,00</span></div>
    <span class="product__stock">Disponible</span>
    <div class="product__actions">
      <button class="btn btn--primary btn--block">Agregar al carrito</button>
    </div>
  </div>
</article>
```
Stock bajo: `<span class="product__stock is-low">Quedan 3</span>`. Agotado: `is-out` + botón `disabled` con texto "Agotado".

## Login
```html
<main class="auth">
  <form class="auth__card">
    <h1 class="logo" style="font-size:1.75rem">Kantu Market</h1>
    <p class="auth__sub">Inicia sesión en tu cuenta</p>
    <div class="field">
      <label for="email">Correo electrónico</label>
      <input id="email" class="input" type="email" placeholder="tu@correo.com" autocomplete="email">
    </div>
    <div class="field">
      <label for="pass">Contraseña</label>
      <input id="pass" class="input" type="password" autocomplete="current-password">
      <span class="field__error">La contraseña es obligatoria.</span>
    </div>
    <button class="btn btn--primary btn--lg btn--block">Iniciar sesión</button>
  </form>
</main>
```

## KPIs (panel vendedor)
```html
<div class="kpi-grid">
  <div class="kpi kpi--money"><div class="kpi__label">Ingresos totales</div><div class="kpi__value">Bs 42.415,00</div></div>
  <div class="kpi kpi--pending"><div class="kpi__label">Pedidos pendientes</div><div class="kpi__value">2</div><div class="kpi__note is-warn">Requieren atención</div></div>
  <div class="kpi kpi--brand"><div class="kpi__label">Total pedidos</div><div class="kpi__value">53</div></div>
  <div class="kpi"><div class="kpi__label">Productos activos</div><div class="kpi__value">9 <small>/ 9</small></div></div>
  <div class="kpi kpi--money"><div class="kpi__label">Bajo stock</div><div class="kpi__value">0</div><div class="kpi__note">Inventario saludable</div></div>
</div>
```

## Gráfico de barras 7 días
Altura de `bar__fill` = `valor / máximo * 100%`. La barra del máximo lleva `is-peak`.
```html
<section class="panel">
  <h2>Productos vendidos (últimos 7 días)</h2>
  <div class="bars">
    <div class="bar"><div class="bar__track"><div class="bar__fill" style="height:6%"></div></div><span class="bar__val">4</span><span class="bar__day">30/09</span></div>
    <div class="bar"><div class="bar__track"><div class="bar__fill is-peak" style="height:100%"></div></div><span class="bar__val">70</span><span class="bar__day">05/10</span></div>
  </div>
</section>
```

## Panel admin
```html
<section class="container">
  <div class="panel">
    <span class="badge badge--admin">Panel de administración</span>
    <h1>Panel de control</h1>
    <div class="tiles">
      <a class="tile" href="/bitacora"><h3>Bitácora y auditoría</h3><p>Historial de accesos y cambios en la plataforma.</p></a>
      <a class="tile" href="/roles"><h3>Roles y permisos</h3><p>Define qué puede hacer cada rol y usuario.</p></a>
      <a class="tile" href="/backups"><h3>Copias de seguridad</h3><p>Crea y descarga respaldos de la base de datos.</p></a>
    </div>
  </div>
</section>
```

## Tabla de pedidos
```html
<div class="table-wrap">
  <table class="table">
    <thead><tr><th>Pedido</th><th>Cliente</th><th>Estado</th><th class="num">Total</th><th></th></tr></thead>
    <tbody>
      <tr><td>#1042</td><td>Lucía M.</td><td><span class="badge badge--warning">Pendiente</span></td><td class="num">Bs 320,00</td><td><button class="btn btn--ghost">Ver detalle</button></td></tr>
      <tr><td>#1041</td><td>Carlos R.</td><td><span class="badge badge--success">Entregado</span></td><td class="num">Bs 180,00</td><td><button class="btn btn--ghost">Ver detalle</button></td></tr>
    </tbody>
  </table>
</div>
```

## Carrito y checkout (recetas)
- Carrito: lista a la izquierda (imagen 80 px, título, selector de cantidad, precio, quitar), resumen sticky a la derecha en `panel` con subtotal, envío, total en `--fs-xl` peso 800 y un único botón `btn--primary btn--lg btn--block` "Continuar al pago".
- Checkout: 3 pasos (Datos, Envío, Pago) con indicador de progreso donde el paso actual es rojo, los completados verdes con check y los pendientes grises.
- Confirmación: icono check verde grande, "Pedido confirmado", número de pedido y botón "Ver mis pedidos".

## Estados
- Carga: `<div class="skeleton" style="height:180px">` en lugar de tarjetas.
- Vacío: `<div class="empty"><h3>Aún no tienes pedidos</h3><p>Cuando compres algo, aparecerá aquí.</p><a class="btn btn--primary" href="/catalogo">Ver catálogo</a></div>`
- Error: `<div class="alert alert--danger" role="alert">No pudimos cargar los productos. Intenta de nuevo.</div>`

## Bento Grid: panel de administración
Usa `.layout` + `.bento`. Cada módulo es una `.card` de 6 columnas (3 en 1440 px si hay cuatro). Aprovecha el ancho: evita columnas angostas aisladas.
```html
<div class="layout">
  <div class="page-head">
    <div><h1>Panel de control</h1><p>Estado de la plataforma, seguridad y accesos.</p></div>
    <span class="status">Sistema operativo</span>
  </div>
  <div class="bento">
    <div class="col-6"><div class="card">
      <div class="card__header"><h3 class="card__title">Copias de seguridad</h3></div>
      <div class="card__body"><p>Genera respaldos de la base de datos y descárgalos.</p>
        <a class="btn btn--primary" href="/backups">Gestionar copias</a></div>
    </div></div>
    <div class="col-6"><div class="card">
      <div class="card__header"><h3 class="card__title">Sitio administrativo Django</h3></div>
      <div class="card__body"><p>Edita registros de usuarios y tiendas.</p>
        <a class="btn btn--ghost" href="/admin/" target="_blank" rel="noopener">Abrir Django Admin</a></div>
    </div></div>
  </div>
</div>
```

## Bento Grid: panel del vendedor
KPIs en 4 tarjetas `col-3` (clicables si llevan a otra vista con `a.card`), gráfico en `col-8` y últimos pedidos o stock bajo en `col-4`.

## KPI con icono y tendencia
```html
<div class="kpi kpi--money">
  <div class="kpi__top">
    <div><div class="kpi__label">Ingresos totales</div><div class="kpi__value">Bs 42.415,00</div></div>
    <div class="kpi__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8c-1.7 0-3 .9-3 2s1.3 2 3 2 3 .9 3 2-1.3 2-3 2m0-8c1.1 0 2.1.4 2.6 1M12 8V7m0 1v8m0 0v1m0-1c-1.1 0-2.1-.4-2.6-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
  </div>
  <div class="kpi__foot"><span class="kpi__trend is-up">+14,2%</span> frente al mes anterior</div>
</div>
```
Muestra la tendencia solo si el dato existe en el backend; no la inventes.

## Badge con punto de estado
`<span class="badge badge--success"><span class="badge__dot"></span>Entregado</span>`
