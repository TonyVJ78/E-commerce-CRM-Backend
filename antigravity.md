# Antigravity Architecture & Memory: Kantu Market

Documento de memoria técnica central, reglas de arquitectura e invariantes de desarrollo para el ecosistema Kantu Market. Diseñado para servir de guía maestra y contexto ejecutable para asistentes de IA y desarrolladores.

---

## 1. Visión General del Proyecto
- **Naturaleza**: Plataforma SaaS B2B2C multitenant para comercio electrónico en Bolivia.
- **Propósito Core**: Centralizar la intermediación comercial permitiendo a múltiples micro/pequeñas empresas (tenants) autogestionar su catálogo, variantes, precios e inventario, mientras los clientes acceden a un catálogo público unificado con carrito multi-tienda y checkout transaccional. La administración dispone de control granular RBAC y auditoría forense integral.

---

## 2. Repositorios Oficiales (Fuente de la Verdad)
- **Frontend Web**: https://github.com/TonyVJ78/E-commerce-CRM-Fronted
- **Backend API**: https://github.com/TonyVJ78/E-commerce-CRM-Backend
- **App Móvil**: https://github.com/TonyVJ78/E-commerce-CRM-app-movil

---

## 3. Stack Tecnológico Estricto

### Backend (REST API Headless)
- **Runtime & Lenguaje**: Python 3.12
- **Framework Web**: Django 5.1.9 + Django REST Framework (DRF) 3.16.0
- **Autenticación**: `djangorestframework-simplejwt` 5.5.0 (`token_blacklist` habilitado)
- **Gestión de Entorno**: `django-environ` 0.12.0
- **Filtros Declarativos**: `django-filter` 24.3
- **CORS**: `django-cors-headers` 4.7.0
- **Driver BD**: `psycopg2-binary` 2.9.10 / `psycopg` 3.x
- **Gestión Multimedia**: Cloudinary SDK (`cloudinary` Python package)
- **Pasarela de Pagos**: Stripe Python SDK (`stripe` >= 11.0.0)

### Frontend (SPA Web)
- **Framework**: Angular 19.2.x (Arquitectura 100% Standalone Components)
- **Lenguaje**: TypeScript 5.6.x (Tipado estricto, sin `any` injustificado)
- **Programación Reactiva**: RxJS 7.x (`BehaviorSubject`, `Subject`, pipes funcionales)
- **Enrutamiento**: Angular Router con Lazy Loading (`loadComponent`) y Guards funcionales (`inject(AuthService)`)
- **Estilos**: Vanilla CSS con variables CSS custom (tema HSL, tipografía Inter de Google Fonts)
- **Pasarela de Pagos**: `@stripe/stripe-js` (Stripe Payment Element dentro de Drawer lateral)

### Base de Datos
- **Motor**: PostgreSQL 16 (Alpine en Docker local / Neon Cloud PostgreSQL Serverless en prod)
- **Extensiones y Características**: `PL/pgSQL` Triggers, `JSONField` nativo, `ArrayField` de Postgres, índices B-Tree compuestos.

### App Móvil
- **Framework**: Flutter 3.x / Dart 3.x (arquitectura orientada a servicios y gestión reactiva con `Provider`)
- **Pasarela de Pagos**: `flutter_stripe` (PaymentSheet nativo, `FlutterFragmentActivity`, `Theme.MaterialComponents`)
- **Persistencia Local**: `sqflite` (carrito y respaldo local transaccional)

### DevOps e Infraestructura
- **Local**: Docker 29.x + Docker Compose (servicios: `db`, `server`, `client`)
- **Producción**: Vercel Monorepo Serverless (WSGI handler para Django API + Static SPA routing para Angular)

---

## 4. Patrones Arquitectónicos y Reglas de Negocio

### 4.1. Multitenancy y Aislamiento de Datos
- **Aislamiento a Nivel Lógico**: Cada tenant opera bajo la entidad `Tienda`. El campo `propietario` (FK a `Usuario`) rige la propiedad de los datos.
- **`OwnedStoreMixin` / Validación Estricta de Tenant**: Obligatorio en vistas de gestión comercial (catálogo, categorías, inventario, identidad). Resuelve y valida en cada request que la tienda pertenezca estrictamente al `request.user`.
- **Integridad Cruzada**: El trigger `trg_validar_item_carrito` impide la inserción de variantes de una tienda dentro del carrito de otra.

### 4.2. Lógica Transaccional Delegada a Base de Datos (Triggers PL/pgSQL)
La capa de aplicación (Django/Python) **NO debe duplicar ni sobrescribir** la lógica delegada a los 6 triggers de PostgreSQL:
1. **Control de Stock y Concurrencia (`trg_actualizar_stock_item_pedido`)**:
   - Bloqueo pesimista: `SELECT stock FROM variante WHERE id = NEW.variante_id FOR UPDATE;`.
   - Decrementa stock en `INSERT`, restaura en `DELETE` y aborta la transacción con excepción SQL si `stock < cantidad`.
2. **Cálculo Financiero (`trg_recalcular_total_pedido`)**:
   - Sincroniza `subtotal` y `total` en `pedido` automáticamente a partir de la suma de `cantidad * precio_unitario` en `item_pedido`.
3. **Trazabilidad de Estados (`trg_registrar_historial_estado_pedido`)**:
   - Inserta fila histórica en `historial_estado_pedido` ante cada mutación de `estado_actual` en `pedido`.
4. **Validación Multitenant en Carrito (`trg_validar_item_carrito`)**:
   - Exige `cantidad > 0`, valida existencia de variante, pertenencia a la tienda del carrito y estado activo (`activa=True`).
5. **Auditoría Automática de Tienda (`trg_auditar_cambios_tienda`)**:
   - Escribe en `log_auditoria` ante cambios de `nombre` o estado `activa` de la tienda.
6. **Timestamping (`trg_actualizar_timestamp_producto`)**:
   - Actualiza automáticamente el campo `actualizado` de `producto`.

### 4.3. Seguridad y Control de Acceso (RBAC Híbrido)
- **Esquema de Roles**: Roles semilla fijos (`administrador`, `empresa`, `cliente`) con `es_semilla=True` (inmutables y protegidos contra renombrado y borrado).
- **Matriz Granular de 36 Permisos (9 Módulos × 4 Acciones)**:
   - Módulos: `accesos`, `usuarios`, `bitacora`, `tiendas`, `catalogo`, `pedidos`, `crm`, `marketing`, `ia`.
   - Acciones: `ver` (GET), `crear` (POST), `editar` (PATCH/PUT), `eliminar` (DELETE).
   - `PermisoModulo('<modulo>')`: Resuelve dinámicamente la acción a partir del verbo HTTP.
   - Regla Anti-Autobloqueo: Ningún admin puede revocar los permisos `accesos.ver` y `accesos.editar` de su propio rol ni autodesactivar su cuenta.
- **Gestión de Tokens JWT**:
   - `access`: Vida útil de 30 minutos.
   - `refresh`: Vida útil de 24 horas con rotación (`ROTATE_REFRESH_TOKENS=True`) y blacklist en logout (`BLACKLIST_AFTER_ROTATION=True`).
   - `AuthInterceptor`: Maneja captura transparente de errores 401, solicita refresco ordenado y reintenta la petición.

### 4.4. Manejo de Multimedia con Rollback Compensatorio
- Validación en servidor de firmas de archivo (**magic bytes**: JPEG `\xff\xd8\xff`, PNG `\x89PNG`, WebP `RIFF...WEBP`) y tamaño ($\le$ 5MB).
- Flujo en transacción atómica:
  1. Carga imágenes a Cloudinary (`kantu/tiendas/<id>/productos` o `kantu/tiendas/<id>/logo`).
  2. `with transaction.atomic():` inserta o actualiza las entidades de base de datos.
  3. En caso de fallo de BD o validación cruzada posterior, el bloque `except` ejecuta rollback compensatorio invocando `delete_product_image()` o `delete_uploaded_logo()` en Cloudinary para no dejar archivos huérfanos.

### 4.5. Transaccionalidad y Pasarela de Pagos (CU-19)
- **Conversión de Moneda y Fidelidad Transaccional**: Stripe opera en centavos de USD calculados según la tasa configurable `STRIPE_USD_BOB_RATE` (por defecto `6.96`), pero la base de datos almacena los totales reales en Bolivianos (Bs.).
- **`refresh_from_db()` Obligatorio**: Al ejecutar el checkout (`POST /api/pedidos/carrito/checkout/`), tras insertar los `ItemPedido` bajo transacción atómica, el código de Django debe invocar `pedido.refresh_from_db()` para leer el `subtotal` y `total` recalculados por el trigger `trg_recalcular_total_pedido` antes de crear el registro de `Pago` y validar el monto debitado en Stripe.
- **Ciclo de Vida Limpio en Frontend Web (Angular 19)**:
  - Dado que Stripe Payment Element se renderiza dinámicamente dentro de un Drawer lateral, es mandatorio destruir la instancia (`paymentElement.unmount()`, `paymentElement.destroy()`, anulación de referencias y vaciado explícito del nodo del DOM `mountNode.innerHTML = ''`) en `ngOnDestroy()`, al cerrar el carrito o al completar la orden.
  - **Invariante de Montos**: Cualquier cambio en cantidades o ítems (`incrementar`, `decrementar`, `eliminar`, `vaciar`) ejecuta `resetPagoStripe()` de inmediato para evitar cobrar un `PaymentIntent` con un subtotal desactualizado.
- **Pasarela Nativa en App Móvil (Flutter)**:
  - Uso exclusivo del **PaymentSheet nativo** (`initPaymentSheet` + `presentPaymentSheet`), prohibiendo campos embebidos manuales que generen fallos con teclado o 3D Secure.
  - `MainActivity.kt` debe extender `FlutterFragmentActivity` y el tema debe heredar de `Theme.MaterialComponents.Light.NoActionBar`.
  - Captura robusta con `on StripeException catch (e)`: discriminar `FailureCode.Canceled` (cancelación amigable por el usuario) de tarjetas declinadas o fallos de red, previniendo crashes en la aplicación.

### 4.6. Telemetría y Resiliencia del Motor de IA (CU-14)
- **Regla Estricta de UX: "Fallback Silencioso"**: El motor de recomendaciones nunca debe ser un punto único de fallo. Si el algoritmo de IA experimenta latencia, fallo en scoring o el usuario no tiene historial, el backend captura la excepción y retorna un arreglo vacío `[]` con código `HTTP 200`. El widget en el frontend (`RecomendacionesComponent`) se oculta de forma limpia y transparente mediante `@if (productos.length > 0)`, sin mostrar alertas de error ni alterar el layout del catálogo.
- **Telemetría Asíncrona "Fire-and-Forget"**: El registro de señales de navegación (`POST /api/ia/eventos/` o `/api/ia/interacciones/` con eventos `VIEW`, `CLICK`, `SEARCH`, `CART`) opera en segundo plano sin esperar la respuesta HTTP ni bloquear la navegación del usuario ni el hilo principal de la interfaz. Los eventos idénticos se deduplican en una ventana de 30 segundos.
- **Acceso Abierto para Clientes**: Los endpoints de telemetría y recomendaciones exigen únicamente autenticación básica (`IsAuthenticated`), sin imponer permisos administrativos de la matriz RBAC (`ia.crear` / `ia.ver`).

### 4.7. Seguridad Multitenant Absoluta en Tiendas (CU-13)
- **Validación Cruzada a Doble Nivel**: Toda consulta o modificación a la configuración de una tienda (`/api/tiendas/<pk>/identidad/`, slug, color primario `#RRGGBB`, logotipo) exige validar estrictamente que `tienda.propietario == request.user` tanto en la capa de vista (`get_object()`, `perform_update()`) como en el serializador (`TiendaIdentidadSerializer`). Ningún tenant puede consultar ni alterar la identidad de otra tienda.
- **Validación Estricta de Color Hexadecimal**: Exige el formato exacto de 6 dígitos `#RRGGBB` (`Validators.pattern(/^#[0-9A-Fa-f]{6}$/)`).
- **Verificación Dinámica de Slug**: La disponibilidad del slug público se valida en tiempo real garantizando exclusión de colisiones con tiendas ajenas.

---

## 5. Estructura del Ecosistema

```text
       ┌────────────────────────┐         ┌────────────────────────┐
       │      Frontend Web      │         │       App Móvil        │
       │   (Angular 19 SPA)     │         │    (Flutter 3.x)       │
       └───────────┬────────────┘         └───────────┬────────────┘
                   │  HTTP REST / Bearer JWT          │  HTTP REST / Bearer JWT
                   └─────────────────┬────────────────┘
                                     ▼
                   ┌──────────────────────────────────┐
                   │           Backend API            │
                   │  (Django 5.1 + Django REST 3.16) │
                   └────────┬─────────────────┬───────┘
                            │                 │
                            ▼                 ▼
          ┌──────────────────────────┐   ┌─────────────────────────┐
          │     Cloudinary CDN       │   │    PostgreSQL 16        │
          │  (Imágenes y Assets)     │   │  (40 Tablas + Triggers) │
          └──────────────────────────┘   └─────────────────────────┘
```

### Convenciones de Estructura
- **`server/apps/<modulo>/`**: Cada aplicación encapsula sus `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `services.py` y `permissions.py`.
- **`client/src/app/core/`**: Singletons, interceptores, guards e interfaces de datos transversales.
- **`client/src/app/features/<dominio>/`**: Componentes standalone por caso de uso, con carga perezosa (`loadComponent`).
- **`client/src/app/shared/`**: Componentes visuales reutilizables sin acoplamiento a lógica de dominio (ej. `NavbarComponent`).

---

## 6. Directrices de Desarrollo (Reglas Inquebrantables)

1. **Angular Standalone Obligatorio**: Queda terminantemente prohibido el uso de `NgModule`. Todo nuevo componente, directiva o pipe debe declararse `standalone: true` e inyectar dependencias con `inject()`.
2. **Tipado Estricto**: Prohibido usar `any` en modelos, respuestas de servicios o métodos TypeScript sin justificación técnica documentada. Crear interfaces en `core/models/`.
3. **No Duplicar Lógica de Triggers**: Bajo ninguna circunstancia se debe calcular en Python o TypeScript el `total`/`subtotal` de un pedido, ni descontar `variante.stock` mediante código de aplicación; estas tareas son responsabilidad exclusiva de los triggers PL/pgSQL.
4. **Respetar Aislamiento Multitenant**: Ninguna consulta de escritura o lectura de catálogo, pedidos o identidad de tienda debe ejecutarse sin filtrar por `tienda_id` o verificar la propiedad mediante `tienda.propietario == request.user` / `OwnedStoreMixin`.
5. **Auditoría Sistemática**: Toda operación CUD (Crear, Actualizar, Eliminar) en endpoints sensibles debe registrarse en `log_auditoria` utilizando los mixins o helpers de `audit.py`.
6. **Manejo de Errores Limpio**: El frontend debe parsear errores del backend extrayendo cadenas claras (`err.error?.error` o `err.error?.detail`), evitando desplegar `[object Object]` al usuario y traduciendo errores HTTP 403 a advertencias claras de seguridad multitenant.
7. **Borrado Lógico en Catálogo**: Los productos no se eliminan físicamente (`hard delete`); se desactivan vía `activo = False` para preservar la integridad de transacciones históricas.
8. **Resiliencia de Componentes Opcionales**: Las funcionalidades auxiliares como IA, recomendaciones y telemetría deben operar con degradación elegante ("fallback silencioso"): ante fallos, se devuelven colecciones vacías `[]` y la interfaz se oculta limpiamente sin interrumpir las operaciones core del usuario.
