# Generated migration for PostgreSQL triggers in Kantu Market

from django.db import migrations


SQL_TRIGGERS = """
-- ============================================================================
-- TRIGGER 1: Actualización automática de stock en item_pedido
-- Descuenta stock al insertar item_pedido, restaura stock al eliminarlo,
-- y ajusta stock en modificaciones. Lanza error si no hay stock suficiente.
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_actualizar_stock_item_pedido()
RETURNS TRIGGER AS $$
DECLARE
    v_stock_actual INT;
BEGIN
    IF (TG_OP = 'INSERT') THEN
        SELECT stock INTO v_stock_actual FROM variante WHERE id = NEW.variante_id FOR UPDATE;
        IF v_stock_actual < NEW.cantidad THEN
            RAISE EXCEPTION 'Stock insuficiente para la variante ID % (disponible: %, solicitado: %)', 
                NEW.variante_id, v_stock_actual, NEW.cantidad;
        END IF;
        
        UPDATE variante SET stock = stock - NEW.cantidad WHERE id = NEW.variante_id;
        RETURN NEW;
        
    ELSIF (TG_OP = 'UPDATE') THEN
        SELECT stock INTO v_stock_actual FROM variante WHERE id = NEW.variante_id FOR UPDATE;
        IF (v_stock_actual + OLD.cantidad) < NEW.cantidad THEN
            RAISE EXCEPTION 'Stock insuficiente para la variante ID % (disponible: %, solicitado: %)', 
                NEW.variante_id, (v_stock_actual + OLD.cantidad), NEW.cantidad;
        END IF;
        
        UPDATE variante SET stock = stock + OLD.cantidad - NEW.cantidad WHERE id = NEW.variante_id;
        RETURN NEW;
        
    ELSIF (TG_OP = 'DELETE') THEN
        UPDATE variante SET stock = stock + OLD.cantidad WHERE id = OLD.variante_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_actualizar_stock_item_pedido ON item_pedido;
CREATE TRIGGER trg_actualizar_stock_item_pedido
AFTER INSERT OR UPDATE OR DELETE ON item_pedido
FOR EACH ROW
EXECUTE FUNCTION fn_actualizar_stock_item_pedido();


-- ============================================================================
-- TRIGGER 2: Recálculo automático de subtotal y total en pedido
-- Mantiene sincronizado el total y subtotal del pedido según sus items.
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_recalcular_total_pedido()
RETURNS TRIGGER AS $$
DECLARE
    v_pedido_id BIGINT;
    v_total NUMERIC(10,2);
BEGIN
    IF (TG_OP = 'DELETE') THEN
        v_pedido_id := OLD.pedido_id;
    ELSE
        v_pedido_id := NEW.pedido_id;
    END IF;

    SELECT COALESCE(SUM(cantidad * precio_unitario), 0)
    INTO v_total
    FROM item_pedido
    WHERE pedido_id = v_pedido_id;

    UPDATE pedido
    SET subtotal = v_total,
        total = v_total
    WHERE id = v_pedido_id;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_recalcular_total_pedido ON item_pedido;
CREATE TRIGGER trg_recalcular_total_pedido
AFTER INSERT OR UPDATE OR DELETE ON item_pedido
FOR EACH ROW
EXECUTE FUNCTION fn_recalcular_total_pedido();


-- ============================================================================
-- TRIGGER 3: Trazabilidad de estados del pedido
-- Registra automáticamente en historial_estado_pedido ante cualquier cambio.
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_registrar_historial_estado_pedido()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO historial_estado_pedido (tienda_id, pedido_id, estado, fecha)
        VALUES (NEW.tienda_id, NEW.id, NEW.estado_actual, NOW());
        RETURN NEW;
    ELSIF (TG_OP = 'UPDATE') THEN
        IF OLD.estado_actual IS DISTINCT FROM NEW.estado_actual THEN
            INSERT INTO historial_estado_pedido (tienda_id, pedido_id, estado, fecha)
            VALUES (NEW.tienda_id, NEW.id, NEW.estado_actual, NOW());
        END IF;
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_registrar_historial_estado_pedido ON pedido;
CREATE TRIGGER trg_registrar_historial_estado_pedido
AFTER INSERT OR UPDATE OF estado_actual ON pedido
FOR EACH ROW
EXECUTE FUNCTION fn_registrar_historial_estado_pedido();


-- ============================================================================
-- TRIGGER 4: Validación de consistencia y multitenancy en item_carrito
-- Valida cantidad > 0, existencia y que la variante pertenezca a la tienda del carrito.
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_validar_item_carrito()
RETURNS TRIGGER AS $$
DECLARE
    v_tienda_producto BIGINT;
    v_stock INT;
    v_activo BOOLEAN;
BEGIN
    IF NEW.cantidad <= 0 THEN
        RAISE EXCEPTION 'La cantidad del item del carrito debe ser mayor a 0';
    END IF;

    SELECT p.tienda_id, v.stock, v.activa
    INTO v_tienda_producto, v_stock, v_activo
    FROM variante v
    JOIN producto p ON p.id = v.producto_id
    WHERE v.id = NEW.variante_id;

    IF v_tienda_producto IS NULL THEN
        RAISE EXCEPTION 'La variante ID % no existe', NEW.variante_id;
    END IF;

    IF v_tienda_producto <> NEW.tienda_id THEN
        RAISE EXCEPTION 'La variante ID % no pertenece a la tienda ID %', NEW.variante_id, NEW.tienda_id;
    END IF;

    IF NOT v_activo THEN
        RAISE EXCEPTION 'La variante seleccionada no está activa';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validar_item_carrito ON item_carrito;
CREATE TRIGGER trg_validar_item_carrito
BEFORE INSERT OR UPDATE ON item_carrito
FOR EACH ROW
EXECUTE FUNCTION fn_validar_item_carrito();


-- ============================================================================
-- TRIGGER 5: Actualización automática de timestamp en producto
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_actualizar_timestamp_producto()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_actualizar_timestamp_producto ON producto;
CREATE TRIGGER trg_actualizar_timestamp_producto
BEFORE UPDATE ON producto
FOR EACH ROW
EXECUTE FUNCTION fn_actualizar_timestamp_producto();


-- ============================================================================
-- TRIGGER 6: Auditoría automática de cambios de estado en tienda (CU07)
-- ============================================================================
CREATE OR REPLACE FUNCTION fn_auditar_cambios_tienda()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        IF (OLD.nombre IS DISTINCT FROM NEW.nombre) OR (OLD.activa IS DISTINCT FROM NEW.activa) THEN
            INSERT INTO log_auditoria (
                tabla_afectada,
                registro_id,
                accion,
                datos_anteriores,
                datos_nuevos,
                fecha,
                usuario_id
            ) VALUES (
                'tienda',
                NEW.id,
                'ACTUALIZAR',
                json_build_object('nombre', OLD.nombre, 'activa', OLD.activa),
                json_build_object('nombre', NEW.nombre, 'activa', NEW.activa),
                NOW(),
                NEW.propietario_id
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditar_cambios_tienda ON tienda;
CREATE TRIGGER trg_auditar_cambios_tienda
AFTER UPDATE ON tienda
FOR EACH ROW
EXECUTE FUNCTION fn_auditar_cambios_tienda();
"""

SQL_REVERSE = """
DROP TRIGGER IF EXISTS trg_actualizar_stock_item_pedido ON item_pedido;
DROP FUNCTION IF EXISTS fn_actualizar_stock_item_pedido();

DROP TRIGGER IF EXISTS trg_recalcular_total_pedido ON item_pedido;
DROP FUNCTION IF EXISTS fn_recalcular_total_pedido();

DROP TRIGGER IF EXISTS trg_registrar_historial_estado_pedido ON pedido;
DROP FUNCTION IF EXISTS fn_registrar_historial_estado_pedido();

DROP TRIGGER IF EXISTS trg_validar_item_carrito ON item_carrito;
DROP FUNCTION IF EXISTS fn_validar_item_carrito();

DROP TRIGGER IF EXISTS trg_actualizar_timestamp_producto ON producto;
DROP FUNCTION IF EXISTS fn_actualizar_timestamp_producto();

DROP TRIGGER IF EXISTS trg_auditar_cambios_tienda ON tienda;
DROP FUNCTION IF EXISTS fn_auditar_cambios_tienda();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0002_alter_itemcarrito_variante_alter_itempedido_variante'),
        ('catalogo', '0005_remove_atributo_tienda_and_more'),
        ('tiendas', '0004_direcciontienda_usuariotienda'),
        ('usuarios', '0006_matriz_permisos'),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_TRIGGERS,
            reverse_sql=SQL_REVERSE,
        ),
    ]
