# C3 — Validación MongoDB aislada del diseño de diagnóstico

Ejecución experimental del 13 de octubre de 2026. No integra ni activa diagnóstico
operativo, R4, escrituras de claves o lectores indexados. Ninguno de los 26 archivos
sin seguimiento preexistentes se modifica. No se consultan datos de bases anteriores.

## Destino e identidad

- URI sin credenciales: endpoint local 127.0.0.1:27018, directConnection.
- Contenedor existente running/healthy, puerto publicado solo en loopback.
- Replica set app_finanzas_dev_rs, PRIMARY, sesiones de 30 minutos, MongoDB 8.0.32.
- Base nueva: `test_c3_diagnosis_real_bb84944e2f57492191f0081ee055cf3f`.
- Ausencia comprobada antes de la primera escritura, nuevamente en el runner.
- UUID financiero sintético fijado: `ef787808-ba5d-459d-9a90-6931f2467b2b`.
- UUID físico transactions: `1ab51d32da584506a17ac13a3c75018d`.
- Metadata R6 propia y usuario efectivo default-user; comprobados durante recorridos.

El contexto R6 es deliberadamente **sintético**. No se leyó el contexto de ninguna
base existente ni se afirma autenticación o verificación de identidad productiva.
La autorización se limita a fixtures en la nueva base y lecturas administrativas
de identidad/nombres de bases. El auditor de comandos registra namespaces y
estadísticas, no contenido financiero. No detectó comandos a otra base de datos,
salvo admin para hello/buildInfo/listDatabases (nombres) y cierre de sesiones.
La auditoría es evidencia, no un control de acceso MongoDB independiente.

## Datos sintéticos y ausencia de índices explícitos

100.001 movimientos sintéticos: 16.667 int32, 16.667 Int64, 16.667 string,
33.334 Binary (subtipos 0/1) y 16.666 ObjectId. Cada par tiene el mismo ID lógico:
50.000 grupos duplicados esperados más una identidad única. Importes, fechas y
IDs son fixtures; no hay saldos ni pagos reales.

Colecciones adicionales: edge_cases (cinco estados), unsupported (bool/double),
live (intercalación de escrituras), resource_probe (30.000 documentos de ~4 KiB)
y moneyflow_metadata (R6 sintético).

**Cero llamadas de creación de índices explícitos.** Cada colección tiene únicamente
`_id_`, creado implícitamente por MongoDB al crear una colección normal. No se
provisionan índices de usuario, R4 o history_keys. La base permanece conservada;
no se elimina colección, base, volumen ni contenedor.

## Escenarios realmente ejecutados: 17/17

| Escenario | Resultado |
|---|---|
| Aislamiento, R6 y UUID | Pins y destino local verificados |
| Inventario BSON | Conteos exactos, 100.001 documentos |
| Recorrido por particiones | Digest BSON de IDs igual al recorrido global ordenado; cero omisiones/repeticiones en conjunto estable |
| 501 filas, páginas de 5 | 501 filas, 102 páginas no vacías |
| 2.001 filas, páginas de 100 | 2.001 filas, 22 páginas no vacías |
| 10.001 filas, páginas de 1.000 | 10.001 filas, 12 páginas no vacías |
| 50.001 filas, páginas de 1.000 | 50.001 filas, 52 páginas no vacías |
| Duplicados streaming | 50.000 grupos y 50.000 documentos adicionales |
| Explain de ordenación | COLLSCAN: 100.001 docs, 0 keys; usedDisk=false, spills=0 |
| Checkpoints HMAC | Alteración, otra generación/contexto, UUID incorrecto y secuencia antigua rechazados |
| Destino diferente | Bloqueado antes de enviar consulta |
| Cinco estados history_keys | missing/ready/stale_or_corrupt/unverifiable/incompatible; hash BSON antes/después idéntico |
| Tipos físicos no admitidos | bool y double bloquean, sin reparaciones |
| Inserción/edición intercaladas | Inserción anterior a checkpoint omitida y fila visitada editada; no certificación |
| Interrupción y recuperación | Mismo checkpoint y conjunto sucesor (33.333 filas), sin escrituras adicionales |
| Presupuesto cliente | Documento sintético supera presupuesto y bloquea sin reparación |
| Presupuesto servidor de sort | Error MongoDB 292 con allowDiskUse=false; no fallback ni índice |

El recorrido completo usa 102 páginas no vacías y 106 checkpoints/secuencia final
105, incluyendo constatación del agotamiento de las cuatro particiones. Clasifica
los 100.001 movimientos principales como missing, sin provisionarles claves.
Las páginas de benchmark se filtran además por serial; no son certificados del
ámbito completo ni resultados de una base de tamaño distinto.

La concurrencia se reproduce mediante **intercalación real de operaciones** entre
lecturas, no mediante dos threads simultáneos. La interrupción se inyecta después
de obtener el checkpoint; no se corta físicamente la red ni se reinicia MongoDB.
Los checks HMAC se realizan en el cliente sobre el UUID/contexto real de esta base;
no existe verificador HMAC del servidor ni nuevo endpoint público.

## Mediciones reales y límites

Una ejecución por caso, cache/host compartidos, tracemalloc activo y guard de
PRIMARY/R6/UUID por cada página. No son p50/p95 ni garantías de producción.

| Filas visitadas | Límite por página | Tiempo total cliente | Pico incremental Python tracemalloc |
|---|---:|---:|---:|
| 501 | 5 | 481,818 ms | 103.577 bytes |
| 2.001 | 100 | 347,202 ms | 395.098 bytes |
| 10.001 | 1.000 | 827,853 ms | 3.360.818 bytes |
| 50.001 | 1.000 | 3.586,179 ms | 3.652.609 bytes |
| 100.001, diagnóstico/clasificación | 1.000 | 7.169,425 ms | 3.684.063 bytes |
| 100.001, duplicados | batchSize 1.000 | 2.440,079 ms | 1.019.859 bytes |

El pico RSS acumulado de vida del proceso reporta 679.600 KiB. **No es memoria
incremental del diagnóstico ni puede atribuirse a una consulta concreta**: incluye
la vida/inicialización del proceso y preparación/otros pasos. Tracemalloc tampoco
incluye toda la memoria nativa del driver/servidor. No se midió RSS dedicado de
MongoDB. Una medición aislada por proceso y monitorización de servidor siguen
pendientes antes de afirmar límites reales de memoria.

BSON máximo de lote procesado observado: 169.000 bytes. Respuestas BSON del driver:
find 174.151 bytes, getMore 87.498 bytes, aggregate 87.486 bytes. Son tamaños BSON
codificados del reply observado, no bytes reales de transporte/comprensión. No se
probó aquí un documento financiero cercano a 16 MiB ni se afirma que batchSize
imponga un presupuesto duro de bytes al buffer del driver.

Explain de duplicados: 165 ms registrados en executionStats y estimación de datos
ordenados 34.117.028 bytes. La medición cliente 2.440 ms incluye transferencia,
decodificación, comparación y tracing. La estimación de sort no es RSS real.
No hay ordenamiento en disco para el caso positivo.

El recurso negativo ordena documentos con padding (~123 MB fuente) sin limit/top-k.
Devuelve error 292 en 19,505 ms al superar presupuesto interno de sort. Es una
prueba satisfactoria de **rechazo**, no de capacidad para ordenar ese historial.
No se habilita spill ni se crea el índice sugerido para hacerla pasar.

## Riesgos antes de leer datos reales

- Falta de ordenación indexada por ID lógico: el server mantiene estado proporcional
  al conjunto a ordenar y puede rechazar historiales grandes.
- Los tipos admitidos son un subconjunto; inventario con otros tipos bloquea.
- Vista viva no certificable: cambios anteriores al checkpoint se pueden omitir.
- HMAC/registro siguen siendo memoria de proceso. Reinicio requiere diagnóstico
  completo; no existe almacenamiento protegido ni prueba operacional de escritores.
- Falta medir memoria por proceso, buffers grandes, cancelación/timeouts prolongados,
  permisos read-only independientes y latencias repetidas sobre distintas cargas.
- No se prueba una caída física de red/PRIMARY, sustitución real de colección o
  acceso real denegado; esos casos permanecen como pruebas futuras autorizadas.
- R6 sintético no autoriza tocar una base real. default-user no es autenticación.

Veredicto: **APTO para avanzar al siguiente diseño**, manteniendo estas restricciones.
**No apto como autorización de diagnóstico de datos reales ni de activación.**
Cualquier índice, spill, acceso a datos reales o persistencia del checkpoint necesita
una autorización adicional. No se propone reparar el historial automáticamente.

## Artefactos y verificación

Runner nuevo: `backend/experiments/c3_diagnosis_mongodb_validation.py`.
Evidencia agregada nueva:
`backend/experiments/results/test_c3_diagnosis_real_bb84944e2f57492191f0081ee055cf3f.json`.
Este documento es nuevo. Los 26 archivos anteriores se conservan; no reejecutar el
runner sobre esta base: su comprobación de ausencia bloquea cualquier reutilización.

Regresiones offline ejecutadas ahora: 100/100 (23 diseño, 39 diagnóstico, 38 contrato).
No se presenta evidencia previa como ejecución MongoDB nueva. No hubo staging,
commit, push, cambio funcional, .env, compose, índices explícitos o activación.
