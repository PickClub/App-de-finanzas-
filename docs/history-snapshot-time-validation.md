# C3 — Validación sintética de snapshot común T, MongoDB 8.0

Experimento aislado del 13 de octubre de 2026. No activa producción ni certifica
historial real. No se lee ninguna base preexistente: solo nombres para comprobar
ausencia y las lecturas administrativas de identidad/parámetros autorizadas.

## Bases conservadas y seguridad

Ejecución final:
`test_c3_snapshot_9e26a10fa77a4d24985a5c963b1bba1f`.
Ausencia comprobada inmediatamente antes de la primera escritura. Endpoint directo
127.0.0.1:27018, contenedor existente healthy, PRIMARY app_finanzas_dev_rs,
MongoDB 8.0.32. Metadata R6 sintética con pin
`bdf679b9-ff50-46b6-a698-d7f2ca1c93d4` y UUID físico transactions
`a4d5725fa0404054a6956948284ae9b1`.
R6 fue leído/validado en el instante T y también contra el destino vigente.
default-user es identidad efectiva del fixture, no autenticación real.

Primera base, también nueva y conservada:
`test_c3_snapshot_5025e56b1bd1482d9e4a0ee7937e510b`.
El runner obtuvo T pero falló al enviar maxTimeMS a getMore no-awaitData (BadValue 2).
No llegó a mutar documentos después de T. Se corrigió solo el runner nuevo; la
segunda ejecución utilizó otra base comprobada ausente, sin reutilizar la fallida.
MongoDB documenta maxTimeMS en el comando inicial para estos cursores:
[Referencia getMore 8.0](https://www.mongodb.com/docs/v8.0/reference/command/getmore/).

Las dos bases se conservan, sin borrar nada. Solo existen índices `_id_` implícitos;
no hay createIndex, cambios de infraestructura/retención o transacciones financieras.
El auditor registró únicamente comandos en la base nueva y admin para identidad,
parámetros y cierre de sesiones; cero namespaces de bases ajenas. Es auditoría
cliente, no un mecanismo independiente de autorización read-only del servidor.

## Obtención y reutilización de T

Tras insertar fixtures con writeConcern majority se hizo find con
`readConcern:{level:'snapshot'}` en sesión no causal. Se tomó **atClusterTime de
la respuesta del servidor**, sin inferirlo de operationTime o reloj del cliente.
La respuesta fue `Timestamp(1791921682,13)`. Se cerró el cursor inicial.

Cada nuevo find/aggregate histórico envió explícitamente
`readConcern:{level:'snapshot',atClusterTime:T}` en una nueva sesión no causal;
getMore continuó en la misma sesión de su cursor. No se especificó otro readConcern
al getMore. Inventario, particiones, conteo de duplicados y metadata R6 usaron T.
[Contrato snapshot MongoDB 8.0](https://www.mongodb.com/docs/v8.0/reference/read-concern-snapshot/).

## Datos y resultados: 14/14 escenarios finales

6.001 documentos con int32 (1.001), Int64 (1.000), string (1.000), Binary subtipos
0/1 (2.000) y ObjectId (1.000). Todos son sintéticos y tienen fecha/importe/IDs
ficticios. Claves: 1.201 ready y 1.200 de cada missing, stale_or_corrupt,
unverifiable e incompatible. Hay 3.000 pares con ID lógico duplicado.

| Escenario | Evidencia real |
|---|---|
| Base/identidad | Ausencia, loopback, PRIMARY, R6 y UUID verificados |
| T servidor | atClusterTime explícito retornado |
| Recorrido inicial | 6.001 documentos, 151 páginas de hasta 40 |
| Inventario a T | Todos los tipos y conteos concordantes |
| Duplicados a T | 3.000 grupos, 3.000 documentos adicionales |
| Cambios posteriores | Dos inserciones, edición de importe y eliminación, solo sintéticas |
| Segundo recorrido a T | 6.001 documentos, 7 páginas de hasta 1.000; mismo digest BSON completo y estados |
| Comparación viva | 6.002 documentos, 2.999 grupos duplicados |
| Cursor interrumpido | killCursors real; getMore falló con CursorNotFound 43 |
| Nueva sesión | Consulta sucesora con mismo T recuperó partición numérica completa, 2.001 filas |
| Nuevo MongoClient | Mismo T siguió viendo el documento eliminado |
| T no disponible | Timestamp(1,1) devolvió SnapshotTooOld 239; no resultado certificable |
| T válido al finalizar | Continuaba disponible tras 3,471 segundos |
| R6 a T y actual | Coincidencia verificada; UUID vigente conservado |

Después de T se insertaron un `_id` numérico anterior y un ObjectId posterior;
ninguno apareció en los históricos. El importe editado siguió con su valor original
a T; el documento eliminado permaneció visible en el histórico. El digest BSON
completo de los dos recorridos históricos fue
`1647ced69cd5e3836aa65e9cc05bbb003a9255c9910d6cce8bc3fe1c47d2f65a`.
Los duplicados se volvieron a comprobar a T y mantuvieron el resultado original.

Las escrituras se intercalaron entre lecturas: no se afirma un stress test de
threads simultáneos. Se creó un cliente nuevo, no se mató físicamente el proceso
ni se reinició MongoDB. No se implementó HMAC durable ni nuevo adapter público.

## Recursos y retención

| Recorrido | Tiempo cliente | Pico Python trazado | RSS antes → después |
|---|---:|---:|---:|
| Inicial, páginas 40 | 1.477,147 ms | 188.250 bytes | 66.392.064 → 66.457.600 bytes |
| Histórico tras mutaciones, páginas 1.000 | 1.275,286 ms | 3.472.400 bytes | 66.457.600 → 73.420.800 bytes |
| Duplicados al mismo T | 396,252 ms | 25.307 bytes | 73.420.800 → 73.420.800 bytes |

Son ejecuciones únicas, con tracing y múltiples verificaciones/round trips;
no percentiles ni límites garantizados. batchSize de red fue 7 para probar getMore,
lo que generó 3.603 comandos getMore en la ejecución total, incluido el negativo.
Respuesta BSON máxima: find 2.583 bytes, getMore 511.541 bytes, aggregate 8.802 bytes.
El getMore máximo incluye la comparación viva del driver con su batch por defecto;
no equivale al tamaño máximo de lote del recorrido histórico. Bytes BSON codificados
no son bytes de transporte ni toda la memoria del driver/servidor.

Parámetros leídos, nunca modificados: minSnapshotHistoryWindowInSeconds=300,
transactionLifetimeLimitSeconds=60, sesiones 30 minutos. El experimento no utilizó
transacciones read-only largas. No se midió RSS del servidor ni estimación de
memoria del sort a T: esas mediciones requieren una fase adicional. Todas las
agregaciones relevantes llevaron allowDiskUse=false; no se habilitó spill.

**Retención observada:** T fue legible tras 3,471 segundos. Se observó el rechazo
real de un timestamp histórico no disponible, no la expiración natural del T
seleccionado. No se puede afirmar retención efectiva de 300 segundos, reanudación
tras minutos/horas o supervivencia a elecciones/reinicio. No se ejerció presión
para forzar expiración ni se cambiaron parámetros.

## Aborto y límites de certificación

El primer error del runner abortó sin emitir certificado; la evidencia fallida
se conserva. SnapshotTooOld se trató como resultado negativo esperado y no como
rollback/dato vacío. No se mezcló la lectura viva con los conteos históricos ni
se sustituyó T para continuar el mismo diagnóstico.

La vista histórica es consistente en este caso, pero tiene defectos deliberados:
missing/stale/unverifiable/incompatible y duplicados. No certifica salud del
historial ni habilita lectores indexados. Una firma de checkpoint nunca obliga
al servidor a mantener el snapshot disponible.

Riesgos pendientes: expiración natural de T, reanudación tras caída física de
proceso, elecciones/fallos de servidor, DDL/UUID sustituido, rendimiento en historiales
mayores, buffers BSON grandes, protección de manifests/secretos y controles de acceso.
Necesitan otras bases nuevas y autorizaciones explícitas; no inferir garantías
universales de estas 6.001 filas ni de la prueba anterior de 100.001 filas viva.

Veredicto: **APTO para diseñar el diagnóstico consistente basado en T**, condicionado
al aborto conservador cuando T no sea legible. **No es autorización de certificación
sobre datos reales ni implementación de producción.**

## Artefactos nuevos

- `backend/experiments/c3_snapshot_time_validation.py`: runner corregido, que exige
  base ausente; no reejecutarlo sobre las bases ya utilizadas.
- `backend/experiments/test_c3_snapshot_validation_evidence.py`: ocho verificaciones
  offline de evidencia, incluyendo límites y conservación del intento fallido.
- Dos JSON agregados nuevos en experiments/results, uno por ejecución.
- Este documento.

No se modificó ningún experimento/archivo preexistente según comparación SHA-256.
No hubo staging, commit, push, cambio funcional, .env o activaciones.
