from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_actualizar_stock_item_pedido()
RETURNS TRIGGER AS $$
DECLARE
    v_stock_actual INT;
    v_variant RECORD;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT stock INTO v_stock_actual FROM variante WHERE id = NEW.variante_id FOR UPDATE;
        IF v_stock_actual < NEW.cantidad THEN
            RAISE EXCEPTION 'Stock insuficiente para la variante ID % (disponible: %, solicitado: %)',
                NEW.variante_id, v_stock_actual, NEW.cantidad;
        END IF;
        UPDATE variante SET stock = stock - NEW.cantidad WHERE id = NEW.variante_id;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.variante_id IS DISTINCT FROM NEW.variante_id THEN
            -- Acquire both row locks in one globally consistent order before changing either row.
            FOR v_variant IN
                SELECT id, stock FROM variante
                WHERE id IN (OLD.variante_id, NEW.variante_id)
                ORDER BY id
                FOR UPDATE
            LOOP
                IF v_variant.id = NEW.variante_id THEN
                    v_stock_actual := v_variant.stock;
                END IF;
            END LOOP;
            IF v_stock_actual < NEW.cantidad THEN
                RAISE EXCEPTION 'Stock insuficiente para la variante ID % (disponible: %, solicitado: %)',
                    NEW.variante_id, v_stock_actual, NEW.cantidad;
            END IF;
            UPDATE variante SET stock = stock + OLD.cantidad WHERE id = OLD.variante_id;
            UPDATE variante SET stock = stock - NEW.cantidad WHERE id = NEW.variante_id;
        ELSE
            SELECT stock INTO v_stock_actual FROM variante WHERE id = NEW.variante_id FOR UPDATE;
            IF (v_stock_actual + OLD.cantidad) < NEW.cantidad THEN
                RAISE EXCEPTION 'Stock insuficiente para la variante ID % (disponible: %, solicitado: %)',
                    NEW.variante_id, (v_stock_actual + OLD.cantidad), NEW.cantidad;
            END IF;
            UPDATE variante SET stock = stock + OLD.cantidad - NEW.cantidad WHERE id = NEW.variante_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE variante SET stock = stock + OLD.cantidad WHERE id = OLD.variante_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

# Restore the function installed by migration 0003, leaving its trigger intact.
REVERSE_SQL = """
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ('pedidos', '0005_seed_metodos_pago'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
