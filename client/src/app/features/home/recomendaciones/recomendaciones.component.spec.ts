import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ProductoCatalogo } from '../../../core/models/catalogo.model';
import { RecomendacionService } from '../../../core/services/recomendacion.service';
import { RecomendacionesComponent } from './recomendaciones.component';

describe('RecomendacionesComponent CU-14', () => {
  let fixture: ComponentFixture<RecomendacionesComponent>;
  let component: RecomendacionesComponent;
  let service: jasmine.SpyObj<RecomendacionService>;

  const product: ProductoCatalogo = {
    id: 10,
    nombre: 'Zapatilla',
    slug: 'zapatilla',
    descripcion: 'Deportiva',
    imagenes: [],
    imagen_principal: '',
    variantes: [],
    precio_base: '120.00',
    tienda_id: 4,
    tienda_nombre: 'Tienda Uno',
    categoria_nombre: 'Calzado'
  };

  beforeEach(async () => {
    service = jasmine.createSpyObj<RecomendacionService>('RecomendacionService', [
      'obtenerRecomendaciones',
      'registrarInteraccion'
    ]);
    service.obtenerRecomendaciones.and.returnValue(of([product]));
    service.registrarInteraccion.and.returnValue(of(null));

    await TestBed.configureTestingModule({
      imports: [RecomendacionesComponent],
      providers: [{provide: RecomendacionService, useValue: service}]
    }).compileComponents();

    fixture = TestBed.createComponent(RecomendacionesComponent);
    component = fixture.componentInstance;
    component.tiendaId = 4;
  });

  it('carga y muestra resultados de la tienda correcta', () => {
    component.ngOnChanges({tiendaId: {} as never});
    fixture.detectChanges();
    expect(service.obtenerRecomendaciones).toHaveBeenCalledOnceWith(4, 8);
    expect(fixture.nativeElement.textContent).toContain('Zapatilla');
  });

  it('muestra estado vacío', () => {
    service.obtenerRecomendaciones.and.returnValue(of([]));
    component.cargar();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Aún no hay productos');
  });

  it('muestra error controlado', () => {
    service.obtenerRecomendaciones.and.returnValue(throwError(() => new Error('fallo')));
    component.cargar();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No pudimos cargar');
  });

  it('registra CLICK y emite el producto seleccionado', () => {
    spyOn(component.productoSeleccionado, 'emit');
    component.seleccionar(product);
    expect(service.registrarInteraccion).toHaveBeenCalledWith({
      tienda_id: 4,
      producto_id: 10,
      tipo_interaccion: 'CLICK'
    });
    expect(component.productoSeleccionado.emit).toHaveBeenCalledWith(product);
  });
});
