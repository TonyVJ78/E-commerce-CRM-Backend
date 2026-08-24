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

print("\n[OK] TODOS LOS NUEVOS REQUISITOS Y AJUSTES DE COMPORTAMIENTO VERIFICADOS AL 100%!")
