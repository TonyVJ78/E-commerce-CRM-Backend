import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Tienda, TiendaIdentidad, TiendaService } from '../../../core/services/tienda.service';
import { IdentidadMarcaComponent } from './identidad-marca.component';

describe('IdentidadMarcaComponent', () => {
  let fixture: ComponentFixture<IdentidadMarcaComponent>;
  let component: IdentidadMarcaComponent;
  let service: jasmine.SpyObj<TiendaService>;

  const stores: Tienda[] = [
    {id: 1, propietario: 10, nombre: 'Tienda A', slug: 'tienda-a', activa: true},
    {id: 2, propietario: 10, nombre: 'Tienda B', slug: 'tienda-b', activa: true}
  ];
  const identity: TiendaIdentidad = {
    id: 1,
    nombre: 'Tienda A',
    slug: 'tienda-a',
    logo_url: '',
    color_primario: '#C8102E'
  };

  beforeEach(async () => {
    service = jasmine.createSpyObj<TiendaService>('TiendaService', [
      'listar',
      'obtenerIdentidad',
      'actualizarIdentidad',
      'verificarSlug'
    ]);
    service.listar.and.returnValue(of(stores));
    service.obtenerIdentidad.and.returnValue(of(identity));
    service.verificarSlug.and.returnValue(of({slug: 'tienda-a', disponible: true}));
    service.actualizarIdentidad.and.returnValue(of(identity));

    await TestBed.configureTestingModule({
      imports: [IdentidadMarcaComponent],
      providers: [{provide: TiendaService, useValue: service}]
    }).compileComponents();

    fixture = TestBed.createComponent(IdentidadMarcaComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('no presupone una tienda cuando la empresa tiene varias', () => {
    expect(component.tiendas.length).toBe(2);
    expect(component.selectedStoreId).toBeNull();
    expect(service.obtenerIdentidad).not.toHaveBeenCalled();
  });

  it('carga la identidad de la tienda elegida', () => {
    component.selectStore(1);

    expect(service.obtenerIdentidad).toHaveBeenCalledOnceWith(1);
    expect(component.identityForm.getRawValue()).toEqual({
      slug: 'tienda-a',
      color_primario: '#C8102E'
    });
  });

  it('guarda por servicio y muestra confirmación', () => {
    component.selectStore(1);
    component.identityForm.setValue({slug: 'tienda-a', color_primario: '#C8102E'});
    component.save();

    expect(service.actualizarIdentidad).toHaveBeenCalledWith(
      1,
      {slug: 'tienda-a', color_primario: '#C8102E'},
      undefined
    );
    expect(component.successMessage).toContain('guardó correctamente');
  });
});
