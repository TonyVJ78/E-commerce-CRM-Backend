import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';
import { GestionProductosComponent } from './gestion-productos.component';
import { ProductoService } from '../../../core/services/producto.service';
import { TiendaService } from '../../../core/services/tienda.service';
import { CarritoService } from '../../../core/services/carrito.service';

describe('GestionProductosComponent stock management', () => {
  let fixture: ComponentFixture<GestionProductosComponent>;
  let component: GestionProductosComponent;
  let producto: jasmine.SpyObj<ProductoService>;
  beforeEach(async () => {
    producto = jasmine.createSpyObj('ProductoService', ['listar', 'ajustarStock', 'listarMovimientosStock']);
    producto.listar.and.returnValue(of([]));
    producto.listarMovimientosStock.and.returnValue(of([]));
    producto.ajustarStock.and.returnValue(of({ id: 1, variante: 4, previous_stock: 2, delta: 1, resulting_stock: 3, actor: 7, reason: 'Conteo', created_at: '' }));
    await TestBed.configureTestingModule({ imports: [GestionProductosComponent], providers: [
      { provide: ProductoService, useValue: producto },
      { provide: TiendaService, useValue: { listar: () => of([]) } },
      { provide: CarritoService, useValue: { checkoutCompleted$: of() } }
    ] }).compileComponents();
    fixture = TestBed.createComponent(GestionProductosComponent);
    component = fixture.componentInstance;
  });
  it('rejects invalid, zero, and negative-result adjustments', () => {
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }] });
    component.seleccionarVariante(4);
    component.deltaStock = -3; component.motivoStock = 'Conteo';
    expect(component.ajusteStockValido).toBeFalse();
    component.deltaStock = 0;
    expect(component.ajusteStockValido).toBeFalse();
    expect(producto.ajustarStock).not.toHaveBeenCalled();
  });
  it('guards duplicate submits and modal/variant changes until the submitted adjustment settles', () => {
    const response = new Subject<any>();
    producto.ajustarStock.and.returnValue(response);
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }, { id: 5, sku: 'B', nombre: 'B', precio: 1, precio_oferta: null, stock: 8, stock_minimo: 0, atributos: {}, activa: true }] });
    component.seleccionarVariante(4); component.deltaStock = 1; component.motivoStock = 'Conteo';
    component.guardarAjusteStock();
    component.guardarAjusteStock();
    component.seleccionarVariante(5);
    component.cerrarInventario();
    component.abrirInventario({ id: 9, tienda: 2, nombre: 'Otro', slug: 'otro', variantes: [] });
    expect(producto.ajustarStock).toHaveBeenCalledTimes(1);
    expect(component.varianteInventarioId).toBe(4);
    expect(component.productoInventario?.id).toBe(1);
    response.next({}); response.complete();
  });

  it('ignores stale history responses after switching variants, closing, or reopening', () => {
    const first = new Subject<any[]>();
    const second = new Subject<any[]>();
    producto.listarMovimientosStock.and.returnValues(first, second);
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }, { id: 5, sku: 'B', nombre: 'B', precio: 1, precio_oferta: null, stock: 8, stock_minimo: 0, atributos: {}, activa: true }] });
    component.seleccionarVariante(4); component.seleccionarVariante(5);
    first.next([{ id: 1 } as any]);
    expect(component.movimientosStock).toEqual([]);
    second.next([{ id: 2 } as any]);
    expect(component.movimientosStock[0].id).toBe(2);
    const stale = new Subject<any[]>();
    producto.listarMovimientosStock.and.returnValue(stale);
    component.seleccionarVariante(4); component.cerrarInventario();
    component.abrirInventario({ id: 9, tienda: 2, nombre: 'Otro', slug: 'otro', variantes: [{ id: 4, sku: 'C', nombre: 'C', precio: 1, precio_oferta: null, stock: 1, stock_minimo: 0, atributos: {}, activa: true }] });
    stale.next([{ id: 3 } as any]);
    expect(component.movimientosStock).toEqual([]);
  });

  it('updates the submitted product and reloads history on success without changing another active context', () => {
    const save = new Subject<any>();
    const history = new Subject<any[]>();
    producto.ajustarStock.and.returnValue(save);
    producto.listarMovimientosStock.and.returnValue(history);
    producto.listar.and.returnValue(new Subject<any[]>());
    component.productos = [{ id: 1, tienda: 2, nombre: 'P', slug: 'p', stock: 2, variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }] }];
    component.abrirInventario(component.productos[0]); component.seleccionarVariante(4);
    component.deltaStock = 1; component.motivoStock = 'Conteo'; component.guardarAjusteStock();
    component.cerrarInventario();
    save.next({}); save.complete();
    expect(component.productos[0].variantes?.[0].stock).toBe(3);
    expect(component.productos[0].stock).toBe(3);
    expect(component.productoInventario).toBeNull();
    expect(producto.listarMovimientosStock).toHaveBeenCalledTimes(1);
  });

  it('refreshes the selected variant history after a successful adjustment', () => {
    const save = new Subject<any>();
    const histories: Subject<any[]>[] = [new Subject<any[]>(), new Subject<any[]>()];
    producto.ajustarStock.and.returnValue(save);
    producto.listar.and.returnValue(new Subject<any[]>());
    producto.listarMovimientosStock.and.returnValues(...histories);
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }] });
    component.seleccionarVariante(4);
    histories[0].next([]);
    component.deltaStock = 1; component.motivoStock = 'Conteo'; component.guardarAjusteStock();
    save.next({}); save.complete();
    expect(producto.listarMovimientosStock).toHaveBeenCalledTimes(2);
    const movement = { id: 99, variante: 4, previous_stock: 3, delta: 1, resulting_stock: 4, actor: 7, reason: 'Conteo', created_at: '' };
    histories[1].next([movement]);
    expect(component.movimientosStock).toEqual([movement]);
  });

  it('does not send stock through product PATCH and preserves server errors', () => {
    expect(component.editForm.contains('stock')).toBeFalse();
    producto.ajustarStock.and.returnValue(throwError(() => ({ status: 400, error: { detail: 'Stock insuficiente' } })));
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 2, stock_minimo: 0, atributos: {}, activa: true }] });
    component.seleccionarVariante(4); component.deltaStock = -1; component.motivoStock = 'Conteo';
    component.guardarAjusteStock();
    expect(producto.ajustarStock).toHaveBeenCalledWith(2, 4, { delta: -1, reason: 'Conteo', tipo_ajuste: 'CORRECCION' });
    expect(component.errorStock).toBe('Stock insuficiente');
  });

  it('supports absolute stock mode calculation and quick reasons', () => {
    component.abrirInventario({ id: 1, tienda: 2, nombre: 'P', slug: 'p', variantes: [{ id: 4, sku: 'A', nombre: 'A', precio: 1, precio_oferta: null, stock: 10, stock_minimo: 5, atributos: {}, activa: true }] });
    component.seleccionarVariante(4);
    component.modoAjuste = 'absoluto';
    component.nuevoStockAbsoluto = 25;
    component.seleccionarMotivoFrecuente(component.motivosFrecuentes[0]);

    expect(component.deltaCalculado).toBe(15);
    expect(component.stockProyectado).toBe(25);
    expect(component.ajusteStockValido).toBeTrue();
    expect(component.tipoAjuste).toBe('INGRESO');

    component.guardarAjusteStock();
    expect(producto.ajustarStock).toHaveBeenCalledWith(2, 4, {
      nuevo_stock: 25,
      reason: component.motivosFrecuentes[0].motivo,
      tipo_ajuste: 'INGRESO'
    });
  });
});
