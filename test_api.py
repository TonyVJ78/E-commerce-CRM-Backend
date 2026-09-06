import json
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000/api"
UNIQUE_ID = int(time.time())

def make_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(data).encode("utf-8")
    else:
        data_bytes = None
    
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return response.status, json.loads(res_body) if res_body else {}
    except urllib.error.HTTPError as e:
        res_body = e.read().decode("utf-8")
        return e.code, json.loads(res_body) if res_body else {}

print("=== 1. Prueba de validación de contraseñas complejas en Registro ===")
# 1.1 Falla por longitud (< 8)
status, res = make_request(
    f"{BASE_URL}/auth/registro/",
    method="POST",
    data={"email": f"fail1_{UNIQUE_ID}@kantu.bo", "password": "Ab1!", "password_confirm": "Ab1!", "first_name": "A", "last_name": "B"}
)
assert status == 400 and "password" in res, f"Debió fallar por longitud: {res}"
print("[OK] Rechazada contrasena corta (<8 chars)")

# 1.2 Falla por falta de número
status, res = make_request(
    f"{BASE_URL}/auth/registro/",
    method="POST",
    data={"email": f"fail2_{UNIQUE_ID}@kantu.bo", "password": "Password!", "password_confirm": "Password!", "first_name": "A", "last_name": "B"}
)
assert status == 400 and "password" in res, f"Debió fallar por falta de número: {res}"
print("[OK] Rechazada contrasena sin numeros")

# 1.3 Falla por falta de carácter especial
status, res = make_request(
    f"{BASE_URL}/auth/registro/",
    method="POST",
    data={"email": f"fail3_{UNIQUE_ID}@kantu.bo", "password": "Password123", "password_confirm": "Password123", "first_name": "A", "last_name": "B"}
)
assert status == 400 and "password" in res, f"Debió fallar por falta de símbolo: {res}"
print("[OK] Rechazada contrasena sin caracter especial")

# 1.4 Acepta contraseña válida con letra, número y símbolo especial
empresa_email = f"empresa_{UNIQUE_ID}@kantu.bo"
status, res = make_request(
    f"{BASE_URL}/auth/registro/",
    method="POST",
    data={"email": empresa_email, "password": "Password123!", "password_confirm": "Password123!", "first_name": "Mario", "last_name": "Condori", "rol_id": 2}
)
assert status == 201, f"Registro válido falló: {res}"
print(f"[OK] Registro exitoso de usuario Empresa ({empresa_email})")

# 1.5 Registro de cliente
cliente_email = f"cliente_{UNIQUE_ID}@kantu.bo"
status, res = make_request(
    f"{BASE_URL}/auth/registro/",
    method="POST",
    data={"email": cliente_email, "password": "Password123!", "password_confirm": "Password123!", "first_name": "Lucia", "last_name": "Vargas", "rol_id": 3}
)
assert status == 201, f"Registro válido de cliente falló: {res}"
print(f"[OK] Registro exitoso de usuario Cliente ({cliente_email})")

print("\n=== 2. Login y obtención de tokens ===")
# Login Empresa
status, res_empresa = make_request(f"{BASE_URL}/auth/login/", method="POST", data={"email": empresa_email, "password": "Password123!"})
assert status == 200 and res_empresa["usuario"]["rol"] == "empresa"
token_empresa = res_empresa["access"]
print(f"[OK] Login Empresa OK (Rol: {res_empresa['usuario']['rol']})")

# Login Cliente
status, res_cliente = make_request(f"{BASE_URL}/auth/login/", method="POST", data={"email": cliente_email, "password": "Password123!"})
assert status == 200 and res_cliente["usuario"]["rol"] == "cliente"
token_cliente = res_cliente["access"]
print(f"[OK] Login Cliente OK (Rol: {res_cliente['usuario']['rol']})")

print("\n=== 3. Protección de endpoint Tiendas según Rol ===")
# 3.1 Cliente intenta crear tienda -> DEBE SER RECHAZADO con 403 Forbidden
status, res = make_request(
    f"{BASE_URL}/tiendas/",
    method="POST",
    data={"nombre": "Tienda Ilegal de Cliente", "color_primario": "#C8102E"},
    headers={"Authorization": f"Bearer {token_cliente}"}
)
assert status == 403, f"Cliente debió recibir 403 Forbidden, pero obtuvo {status}: {res}"
print(f"[OK] Cliente bloqueado con 403 Forbidden: {res.get('detail')}")

# 3.2 Empresa crea tienda -> DEBE SER PERMITIDO con 201 Created
status, res = make_request(
    f"{BASE_URL}/tiendas/",
    method="POST",
    data={"nombre": f"Tienda Autorizada {UNIQUE_ID}", "color_primario": "#27AE60"},
    headers={"Authorization": f"Bearer {token_empresa}"}
)
assert status == 201, f"Empresa debió poder crear tienda: {res}"
print(f"[OK] Empresa creo tienda exitosamente (Slug: {res['slug']})")

print("\n=== 4. Prueba de Recuperación de Contraseña ===")
# 4.1 Solicitar recuperación para un correo existente
status, res = make_request(
    f"{BASE_URL}/auth/password-reset/",
    method="POST",
    data={"email": cliente_email}
)
assert status == 200 and "mensaje" in res, f"Solicitud de reseteo debió ser 200: {res}"
print(f"[OK] Solicitud de recuperación procesada correctamente para {cliente_email}")

# 4.2 Solicitar recuperación con email inválido (debe dar 400)
status, res = make_request(
    f"{BASE_URL}/auth/password-reset/",
    method="POST",
    data={"email": "email_no_valido"}
)
assert status == 400 and "email" in res, f"Solicitud con email inválido debió ser 400: {res}"
print("[OK] Email con formato incorrecto rechazado con 400")

# 4.3 Solicitar confirmación con token/uid inválidos (debe dar 400)
status, res = make_request(
    f"{BASE_URL}/auth/password-reset-confirm/",
    method="POST",
    data={
        "uid": "invalid-uid",
        "token": "invalid-token",
        "new_password": "NewPassword123!",
        "new_password_confirm": "NewPassword123!"
    }
)
assert status == 400, f"Token inválido debió ser 400: {res}"
print("[OK] Intento de reseteo con token/uid inválido rechazado con 400")

print("\n=== 5. CU07 — Bitácora y auditoría (solo administrador) ===")
# 5.1 Login del administrador semilla
status, res_admin = make_request(f"{BASE_URL}/auth/login/", method="POST", data={"email": "admin@kantu.bo", "password": "Password123!"})
assert status == 200 and res_admin["usuario"]["rol"] == "administrador", f"Login admin semilla falló: {res_admin}"
token_admin = res_admin["access"]
refresh_admin = res_admin["refresh"]
print("[OK] Login administrador semilla OK")

# 5.2 Un cliente NO puede consultar la bitácora -> 403
status, res = make_request(f"{BASE_URL}/auditoria/bitacora/", headers={"Authorization": f"Bearer {token_cliente}"})
assert status == 403, f"Cliente debió recibir 403 al consultar bitácora, obtuvo {status}: {res}"
print("[OK] Cliente bloqueado con 403 en /auditoria/bitacora/")

# 5.3 El administrador consulta la bitácora de accesos (respuesta paginada)
status, res = make_request(f"{BASE_URL}/auditoria/bitacora/", headers={"Authorization": f"Bearer {token_admin}"})
assert status == 200 and "results" in res and "count" in res, f"Bitácora debió responder paginada: {res}"
assert res["count"] >= 3, f"Debería haber registros de login previos en la bitácora: {res['count']}"
print(f"[OK] Administrador consulta bitácora de accesos (count={res['count']})")

# 5.4 Filtro por usuario
status, res = make_request(f"{BASE_URL}/auditoria/bitacora/?usuario={cliente_email}", headers={"Authorization": f"Bearer {token_admin}"})
assert status == 200 and res["count"] >= 1, f"Filtro por usuario debió devolver registros: {res}"
assert all(r["usuario_email"] == cliente_email for r in res["results"]), f"El filtro por usuario no aisló correctamente: {res}"
print("[OK] Filtro ?usuario= aísla los accesos del usuario indicado")

# 5.5 El logout deja rastro en el log de auditoría (accion=CERRAR_SESION)
status, res = make_request(f"{BASE_URL}/auth/logout/", method="POST", data={"refresh": refresh_admin}, headers={"Authorization": f"Bearer {token_admin}"})
assert status == 200, f"Logout admin debió ser 200: {res}"
status, res_admin = make_request(f"{BASE_URL}/auth/login/", method="POST", data={"email": "admin@kantu.bo", "password": "Password123!"})
token_admin = res_admin["access"]
status, res = make_request(f"{BASE_URL}/auditoria/logs/?accion=CERRAR_SESION", headers={"Authorization": f"Bearer {token_admin}"})
assert status == 200 and res["count"] >= 1, f"El logout debió registrarse en log_auditoria: {res}"
print(f"[OK] El cierre de sesión queda registrado en /auditoria/logs/ (count={res['count']})")

# 5.6 La creación de tienda (CRUD) queda auditada
status, res = make_request(f"{BASE_URL}/auditoria/logs/?tabla=tienda&accion=CREAR", headers={"Authorization": f"Bearer {token_admin}"})
assert status == 200 and res["count"] >= 1, f"La creación de tienda debió auditarse: {res}"
print(f"[OK] La creación de tienda queda auditada en /auditoria/logs/ (count={res['count']})")

print("\n=== 6. CU07 — Gestionar roles y permisos (solo administrador) ===")
auth_admin = {"Authorization": f"Bearer {token_admin}"}

# 6.1 Un cliente NO puede gestionar accesos -> 403
status, res = make_request(f"{BASE_URL}/roles/", headers={"Authorization": f"Bearer {token_cliente}"})
assert status == 403, f"Cliente debió recibir 403 en /roles/, obtuvo {status}: {res}"
print("[OK] Cliente bloqueado con 403 en /roles/")

# 6.2 El catálogo de permisos está sembrado como matriz módulo × acción
status, res = make_request(f"{BASE_URL}/permisos/", headers=auth_admin)
assert status == 200 and isinstance(res, list) and len(res) >= 36, f"El catálogo debió tener >= 36 filas (9 módulos × 4 acciones): {res}"
permisos_por_codigo = {p["codigo"]: p["id"] for p in res}
for cod in ("accesos.ver", "accesos.crear", "accesos.editar", "accesos.eliminar", "usuarios.editar", "bitacora.ver"):
    assert cod in permisos_por_codigo, f"Falta el permiso '{cod}': {sorted(permisos_por_codigo)}"
assert all(p["modulo"] and p["accion"] for p in res), "Cada permiso debe exponer modulo y accion"
print(f"[OK] Matriz de permisos sembrada ({len(res)} permisos)")

# 6.3 Los roles semilla vienen con su mapeo de permisos y marcados como del sistema
status, res = make_request(f"{BASE_URL}/roles/", headers=auth_admin)
assert status == 200, f"Admin debió listar roles: {res}"
rol_admin = next((r for r in res if r["nombre"] == "administrador"), None)
assert rol_admin and rol_admin["es_semilla"] is True, f"El rol administrador debió marcarse es_semilla: {res}"
assert any(p["codigo"] == "accesos.editar" for p in rol_admin["permisos"]), "El rol administrador debió tener 'accesos.editar'"
print("[OK] Roles semilla con permisos asignados y es_semilla=True")

# 6.4 Crear un rol nuevo
nombre_rol = f"soporte_{UNIQUE_ID}"
status, res = make_request(f"{BASE_URL}/roles/", method="POST", data={"nombre": nombre_rol}, headers=auth_admin)
assert status == 201, f"Crear rol debió ser 201: {status} {res}"
rol_nuevo_id = res["id"]
print(f"[OK] Rol '{nombre_rol}' creado (id={rol_nuevo_id})")

# 6.5 Asignar permisos al rol nuevo (reemplaza el set completo)
solo_ver = sorted(permisos_por_codigo[c] for c in ("accesos.ver", "usuarios.ver"))
status, res = make_request(
    f"{BASE_URL}/roles/{rol_nuevo_id}/permisos/",
    method="PUT",
    data={"permisos": solo_ver},
    headers=auth_admin,
)
assert status == 200 and sorted(res["asignados"]) == solo_ver, f"PUT permisos no asignó el set esperado: {res}"
status, res = make_request(f"{BASE_URL}/roles/{rol_nuevo_id}/permisos/", headers=auth_admin)
assert status == 200 and sorted(res["asignados"]) == solo_ver, f"GET permisos no refleja la asignación: {res}"
print("[OK] Asignación/consulta de permisos de un rol")

# 6.5b Un rol "solo ver" puede consultar pero NO crear/editar/eliminar
status, res = make_request(f"{BASE_URL}/usuarios/?buscar={cliente_email}", headers=auth_admin)
cliente_id_tmp = next(u["id"] for u in res["results"] if u["email"] == cliente_email)
make_request(f"{BASE_URL}/usuarios/{cliente_id_tmp}/", method="PATCH", data={"rol_id": rol_nuevo_id}, headers=auth_admin)
_, res_login = make_request(f"{BASE_URL}/auth/login/", method="POST", data={"email": cliente_email, "password": "Password123!"})
auth_lector = {"Authorization": f"Bearer {res_login['access']}"}
status, _ = make_request(f"{BASE_URL}/roles/", headers=auth_lector)
assert status == 200, f"'solo ver' debió poder GET /roles/: {status}"
status, _ = make_request(f"{BASE_URL}/roles/", method="POST", data={"nombre": f"x_{UNIQUE_ID}"}, headers=auth_lector)
assert status == 403, f"'solo ver' NO debió poder crear roles: {status}"
status, _ = make_request(f"{BASE_URL}/roles/{rol_nuevo_id}/", method="DELETE", headers=auth_lector)
assert status == 403, f"'solo ver' NO debió poder eliminar roles: {status}"
status, _ = make_request(f"{BASE_URL}/usuarios/{cliente_id_tmp}/", method="PATCH", data={"activo": True}, headers=auth_lector)
assert status == 403, f"'solo ver' NO tiene usuarios.editar: {status}"
make_request(f"{BASE_URL}/usuarios/{cliente_id_tmp}/", method="PATCH", data={"rol_id": 3}, headers=auth_admin)
print("[OK] Rol 'solo ver': GET permitido, POST/PATCH/DELETE rechazados con 403")

# 6.6 Los roles del sistema no se pueden eliminar ni renombrar
status, res = make_request(f"{BASE_URL}/roles/{rol_admin['id']}/", method="DELETE", headers=auth_admin)
assert status == 400, f"Eliminar rol semilla debió ser 400, obtuvo {status}: {res}"
status, res = make_request(f"{BASE_URL}/roles/{rol_admin['id']}/", method="PATCH", data={"nombre": "otro"}, headers=auth_admin)
assert status == 400, f"Renombrar rol semilla debió ser 400, obtuvo {status}: {res}"
print("[OK] Roles semilla protegidos contra borrado y renombrado")

# 6.7 Listar usuarios (paginado) y filtrar por email
status, res = make_request(f"{BASE_URL}/usuarios/?buscar={cliente_email}", headers=auth_admin)
assert status == 200 and "results" in res and res["count"] >= 1, f"El listado de usuarios debió responder paginado: {res}"
cliente_id = next((u["id"] for u in res["results"] if u["email"] == cliente_email), None)
assert cliente_id, f"No se encontró al cliente en el listado: {res}"
print(f"[OK] Listado de usuarios con filtro ?buscar= (count={res['count']})")

# 6.8 Asignar el rol nuevo al usuario y luego restaurarlo
status, res = make_request(f"{BASE_URL}/usuarios/{cliente_id}/", method="PATCH", data={"rol_id": rol_nuevo_id}, headers=auth_admin)
assert status == 200 and res["rol"]["nombre"] == nombre_rol, f"El PATCH de rol de usuario falló: {res}"
status, res = make_request(f"{BASE_URL}/usuarios/{cliente_id}/", method="PATCH", data={"rol_id": 3}, headers=auth_admin)
assert status == 200, f"Restaurar el rol del usuario falló: {res}"
print("[OK] Asignación de rol a un usuario")

# 6.9 Los cambios de accesos quedan auditados
status, res = make_request(f"{BASE_URL}/auditoria/logs/?tabla=rol_permiso", headers=auth_admin)
assert status == 200 and res["count"] >= 1, f"Los cambios de permisos de rol debieron auditarse: {res}"
print(f"[OK] Los cambios de accesos quedan auditados en /auditoria/logs/ (count={res['count']})")

# 6.10 El endpoint de bitácora se controla ahora con el permiso 'bitacora.ver'
status, res = make_request(f"{BASE_URL}/auditoria/bitacora/", headers=auth_admin)
assert status == 200, f"El administrador debió acceder a la bitácora vía 'bitacora.ver': {status}"
print("[OK] Control de acceso por permiso: /auditoria/bitacora/ usa 'bitacora.ver'")

# 6.11 Limpieza: eliminar el rol de prueba
status, res = make_request(f"{BASE_URL}/roles/{rol_nuevo_id}/", method="DELETE", headers=auth_admin)
assert status == 204, f"Eliminar el rol de prueba debió ser 204: {status} {res}"
print("[OK] Rol de prueba eliminado")

print("\n[OK] TODOS LOS REQUISITOS Y FLUJOS VERIFICADOS AL 100%!")
