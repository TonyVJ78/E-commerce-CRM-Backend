import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { TiendaService } from './tienda.service';

describe('TiendaService CU-13', () => {
  let service: TiendaService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(TiendaService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('consulta la identidad de la tienda seleccionada', () => {
    service.obtenerIdentidad(7).subscribe(identity => expect(identity.id).toBe(7));

    const request = http.expectOne(req => req.url.endsWith('/tiendas/7/identidad/'));
    expect(request.request.method).toBe('GET');
    request.flush({
      id: 7,
      nombre: 'Tienda 7',
      slug: 'tienda-7',
      logo_url: '',
      color_primario: '#C8102E'
    });
  });

  it('envía slug y color sin exigir un logo', () => {
    service.actualizarIdentidad(7, {
      slug: 'nuevo-slug',
      color_primario: '#112233'
    }).subscribe();

    const request = http.expectOne(req => req.url.endsWith('/tiendas/7/identidad/'));
    expect(request.request.method).toBe('PATCH');
    const body = request.request.body as FormData;
    expect(body.get('slug')).toBe('nuevo-slug');
    expect(body.get('color_primario')).toBe('#112233');
    expect(body.has('logo')).toBeFalse();
    request.flush({
      id: 7,
      nombre: 'Tienda 7',
      slug: 'nuevo-slug',
      logo_url: '',
      color_primario: '#112233'
    });
  });

  it('consulta disponibilidad excluyendo la tienda actual en backend', () => {
    service.verificarSlug(7, 'mi-tienda').subscribe(result => {
      expect(result.disponible).toBeTrue();
    });

    const request = http.expectOne(req =>
      req.url.endsWith('/tiendas/7/identidad/slug-disponible/') &&
      req.params.get('slug') === 'mi-tienda'
    );
    expect(request.request.method).toBe('GET');
    request.flush({slug: 'mi-tienda', disponible: true});
  });
});
