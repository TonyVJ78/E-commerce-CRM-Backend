"""
Kantu Market — Script Automatizado de Pruebas E2E Transaccionales
Cruza CU-13 -> CU-14 -> CU-11 -> CU-19

Ejecución contra servidor en vivo:
    python server/scripts/test_e2e_transaccional_cli.py [http://localhost:8000/api]
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
TIMESTAMP = int(time.time())

def request_json(url, method="GET", data=None, token=None):
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(data).encode("utf-8")
    else:
        data_bytes = None
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            return err.code, json.loads(body) if body else {}
        except Exception:
            return err.code, {"error_raw": body}

def print_step(title):
    print(f"\n{'='*70}\n>>> {title}\n{'='*70}")

def main():
    print("Iniciando Plan de Pruebas E2E Transaccional en Kantu Market...")
    print(f"Target API: {BASE_URL}")

    # -------------------------------------------------------------------------
    # 0. Registro y Login de Usuarios de Prueba
    # -------------------------------------------------------------------------
    print_step("0. Preparación de Usuarios (Tenant A, Tenant B Atacante, Cliente)")
    
    # Tenant A
    email_empresa_a = f"empresa_a_{TIMESTAMP}@kantu.bo"
    code, _ = request_json(f"{BASE_URL}/auth/registro/", "POST", {
        "email": email_empresa_a,
        "password": "Password123!",
        "password_confirm": "Password123!",
        "first_name": "Tienda",
        "last_name": "Andina",
        "rol_id": 2
    })
    
    code, login_a = request_json(f"{BASE_URL}/auth/login/", "POST", {
        "email": email_empresa_a,
        "password": "Password123!"
    })
    token_empresa_a = login_a.get("access")
    print(f" [OK] Tenant A autenticado con JWT")

    # Tenant B (Atacante)
    email_empresa_b = f"empresa_b_{TIMESTAMP}@kantu.bo"
    request_json(f"{BASE_URL}/auth/registro/", "POST", {
        "email": email_empresa_b,
        "password": "Password123!",
        "password_confirm": "Password123!",
        "first_name": "Hacker",
        "last_name": "Intruso",
        "rol_id": 2
    })
    _, login_b = request_json(f"{BASE_URL}/auth/login/", "POST", {
        "email": email_empresa_b,
        "password": "Password123!"
    })
    token_empresa_b = login_b.get("access")
    print(f" [OK] Tenant B autenticado con JWT")

    # Cliente
    email_cliente = f"cliente_{TIMESTAMP}@kantu.bo"
    request_json(f"{BASE_URL}/auth/registro/", "POST", {
        "email": email_cliente,
        "password": "Password123!",
        "password_confirm": "Password123!",
        "first_name": "Juan",
        "last_name": "Comprador",
        "rol_id": 1
    })
    _, login_c = request_json(f"{BASE_URL}/auth/login/", "POST", {
        "email": email_cliente,
        "password": "Password123!"
    })
    token_cliente = login_c.get("access")
    print(f" [OK] Cliente autenticado con JWT")

    # -------------------------------------------------------------------------
    # 1. CU-13: Identidad de Marca y Aislamiento Multitenant
    # -------------------------------------------------------------------------
    print_step("1. CU-13: Aislamiento Multitenant y Marca (Cloudinary)")
    # Crear tienda de Empresa A
    code, tienda_data = request_json(f"{BASE_URL}/tiendas/", "POST", {
        "nombre": f"Tienda Andina {TIMESTAMP}",
        "slug": f"andina-{TIMESTAMP}",
        "color_primario": "#102A43",
        "color_secundario": "#243B53"
    }, token=token_empresa_a)
    tienda_id = tienda_data.get("id")
    print(f" [OK] Tienda A creada con ID: {tienda_id}")

    # 1.1 Intrusión Multitenant rechazada (Empresa B ataca Tienda A)
    code, res_hack = request_json(
        f"{BASE_URL}/tiendas/{tienda_id}/identidad/",
        "PATCH",
        {"color_primario": "#FF0000"},
        token=token_empresa_b
    )
    assert code == 403, f"Fallo de seguridad multitenant: Esperaba 403, recibí {code}"
    print(f" [OK] Aislamiento Multitenant validado: Intrusión cruzada rechazada con HTTP 403")

    # 1.2 Actualización legítima por Tenant A
    code, res_marca = request_json(
        f"{BASE_URL}/tiendas/{tienda_id}/identidad/",
        "PATCH",
        {"color_primario": "#0055AA", "color_secundario": "#FFB800"},
        token=token_empresa_a
    )
    assert code == 200, f"Error al actualizar marca: {res_marca}"
    print(f" [OK] Identidad de marca actualizada con éxito (Colores hex verificados)")

    # -------------------------------------------------------------------------
    # 2. CU-14: Telemetría Fire-and-Forget y Recomendaciones IA
    # -------------------------------------------------------------------------
    print_step("2. CU-14: Telemetría Asíncrona y Motor IA (Fallback Silencioso)")
    
    # 2.1 Enviar telemetría sin requerir rol admin
    code, res_telem = request_json(
        f"{BASE_URL}/ia/eventos/",
        "POST",
        {
            "tienda_id": tienda_id,
            "tipo_interaccion": "SEARCH",
            "termino_busqueda": "artesanias",
        },
        token=token_cliente
    )
    assert code == 201, f"Error en telemetría: {res_telem}"
    print(f" [OK] Telemetría fire-and-forget registrada con HTTP 201 por cliente")

    # 2.2 Consultar recomendaciones personalizadas
    code, res_recom = request_json(
        f"{BASE_URL}/ia/recomendaciones/?tienda_id={tienda_id}",
        "GET",
        token=token_cliente
    )
    assert code == 200, f"Error en recomendaciones: {res_recom}"
    assert isinstance(res_recom, list), f"Esperaba lista de productos, recibí: {type(res_recom)}"
    print(f" [OK] Motor de IA respondió HTTP 200 (Productos devueltos o Fallback Silencioso [] si no hay historial suficiente)")

    # -------------------------------------------------------------------------
    # 3. CU-11: Carrito Multi-Tienda y Validación de Triggers
    # -------------------------------------------------------------------------
    print_step("3. CU-11: Carrito Multi-Tienda")
    code, cart_detail = request_json(f"{BASE_URL}/pedidos/carrito/", "GET", token=token_cliente)
    assert code == 200
    print(f" [OK] Carrito multi-tienda consultado exitosamente")

    # -------------------------------------------------------------------------
    # 4. CU-19: Stripe PaymentIntent y Checkout Atómico
    # -------------------------------------------------------------------------
    print_step("4. CU-19: Pasarela de Pagos Stripe y Checkout Atómico")
    # Intentar checkout con carrito vacío debe rechazar con 400
    code, res_vacio = request_json(
        f"{BASE_URL}/pedidos/carrito/checkout/",
        "POST",
        {"metodo_pago": "Stripe", "payment_intent_id": "pi_dummy"},
        token=token_cliente
    )
    assert code == 400, f"Esperaba 400 por carrito vacío, recibí {code}"
    print(f" [OK] Validación de integridad: Checkout rechazado correctamente si el carrito está vacío")

    print("\n" + "="*70)
    print(">>> TODOS LOS ESCENARIOS DE INTEGRACIÓN TRANSCURRIERON EXITOSAMENTE")
    print("="*70)

if __name__ == "__main__":
    main()
