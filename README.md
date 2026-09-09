# Kantu Market

Plataforma SaaS multitenant para gestion de comercio electronico en Bolivia, con catalogo publico general, carrito de compras multi-tienda, gestion de inventario por empresa y administracion centralizada.

## Arquitectura del Proyecto

```text
kantu-market/
├── client/          - Frontend Angular 19
├── server/          - Backend Django 5.1 REST Framework
├── docker-compose.yml
├── .env.example
├── vercel.json
└── README.md
```

## Requisitos Previos

- Docker (v20+)
- Docker Compose (v2+)

## Puesta en Marcha con Docker Compose

1. Configurar variables de entorno:
   Copiar `.env.example` a `.env` si se requiere personalizar credenciales:
   ```bash
   cp .env.example .env
   ```

2. Iniciar servicios:
   ```bash
   docker compose up --build
   ```

3. Puertos y accesos:
   - Frontend (Angular): http://localhost:4200
   - Backend API (Django): http://localhost:8000/api/
   - Panel Administrador Django: http://localhost:8000/admin/

## Credenciales de Prueba

Todas las cuentas de prueba utilizan la contrasenia: `Password123!`

| Rol | Correo | Acceso / Caso de uso |
|---|---|---|
| Administrador | admin@kantu.bo | Panel de control, auditoria y accesos |
| Empresa | empresa1@kantu.bo | Tienda 'Textiles Los Andes', gestion de productos e imagenes |
| Empresa | empresa2@kantu.bo | Tienda 'Sabores de Bolivia' |
| Cliente | cliente1@kantu.bo | Catalogo general y carrito de compras |
| Cliente | cliente2@kantu.bo | Catalogo general y carrito de compras |

## Endpoints Principales de la API

| Metodo | Endpoint | Descripcion | Autenticacion |
|---|---|---|---|
| POST | /api/auth/registro/ | Registro de nuevos usuarios | No |
| POST | /api/auth/login/ | Inicio de sesion y emision de tokens JWT | No |
| POST | /api/auth/logout/ | Cierre de sesion e invalidacion de token | Si |
| GET | /api/catalogo/productos/ | Catalogo publico con filtros por tienda, categoria y busqueda | No |
| GET | /api/catalogo/categorias/ | Categorias activas para navegacion | No |
| GET | /api/pedidos/carrito/ | Consulta de carritos activos por tienda | Si (Cliente) |
| POST | /api/pedidos/carrito/items/ | Agregar producto al carrito | Si (Cliente) |
| PATCH | /api/pedidos/carrito/items/{id}/ | Actualizar cantidad de producto | Si (Cliente) |
| DELETE | /api/pedidos/carrito/items/{id}/ | Eliminar producto del carrito | Si (Cliente) |
| GET | /api/tiendas/{id}/productos/ | Gestion de inventario de la tienda | Si (Empresa) |
| PATCH | /api/tiendas/{id}/productos/{id}/ | Modificar datos, stock, precio e imagen | Si (Empresa) |

## Licencia

Proyecto academico. Todos los derechos reservados.
