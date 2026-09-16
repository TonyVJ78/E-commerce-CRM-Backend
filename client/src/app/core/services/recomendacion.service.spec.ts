import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { RecomendacionService } from './recomendacion.service';

describe('RecomendacionService CU-14', () => {
  let service: RecomendacionService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(RecomendacionService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('consulta recomendaciones de la tienda y envía limit', () => {
    service.obtenerRecomendaciones(7, 6).subscribe(products => expect(products).toEqual([]));
    const request = http.expectOne(req =>
      req.url.endsWith('/recomendaciones/tiendas/7/') && req.params.get('limit') === '6'
    );
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('registra una interacción sin enviar cliente_id', () => {
    service.registrarInteraccion({
      tienda_id: 7,
      producto_id: 12,
      tipo_interaccion: 'CLICK'
    }).subscribe();
    const request = http.expectOne(req => req.url.endsWith('/recomendaciones/interacciones/'));
    expect(request.request.method).toBe('POST');
    expect(request.request.body.cliente_id).toBeUndefined();
    request.flush({
      id: 1,
      tienda_id: 7,
      producto_id: 12,
      tipo_interaccion: 'CLICK',
      fecha: new Date().toISOString()
    });
  });

  it('deduplica eventos idénticos inmediatos', () => {
    const interaction = {tienda_id: 7, producto_id: 12, tipo_interaccion: 'VIEW' as const};
    service.registrarInteraccion(interaction).subscribe();
    http.expectOne(req => req.url.endsWith('/recomendaciones/interacciones/')).flush({
      id: 1, ...interaction, fecha: new Date().toISOString()
    });
    service.registrarInteraccion(interaction).subscribe(result => expect(result).toBeNull());
    http.expectNone(req => req.url.endsWith('/recomendaciones/interacciones/'));
  });
});
