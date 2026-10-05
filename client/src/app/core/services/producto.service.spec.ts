import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ProductoService } from './producto.service';
import { environment } from '../../../environments/environment';

describe('ProductoService stock movements', () => {
  let service: ProductoService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ProductoService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('uses the selected variant route and posts the signed adjustment and reason', () => {
    service.ajustarStock(8, 41, { delta: -2, reason: 'Conteo' }).subscribe();
    const req = http.expectOne(`${environment.apiUrl}/tiendas/8/variantes/41/stock/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ delta: -2, reason: 'Conteo' });
    req.flush({ id: 1, variante: 41, previous_stock: 3, delta: -2, resulting_stock: 1, actor: 9, reason: 'Conteo', created_at: '' });
  });
  it('loads movement history for the selected variant', () => {
    service.listarMovimientosStock(8, 41).subscribe();
    const req = http.expectOne(`${environment.apiUrl}/tiendas/8/variantes/41/stock/`);
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });
});
