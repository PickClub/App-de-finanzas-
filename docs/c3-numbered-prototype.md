# C3 3A-P — Prototipo aislado, NO activado en producción

Rama `conflict_280926_1750`; HEAD `1ca9972b748dee2ebf613fef1bea7b89e5537b4f`.
Servidor real observado: MongoDB 8.0.32, PRIMARY local `127.0.0.1:27018`,
replica set `app_finanzas_dev_rs`. No se leyeron `.env` ni credenciales.

## Aislamiento y ejecución

Cada ejecución genera un nombre UUID nuevo, verifica URI y PRIMARY, y consulta
`listDatabases` con filtro **exacto del nombre nuevo** antes de escribir. Si existe,
se detiene. Se crea un manifiesto de propiedad y únicamente colecciones sintéticas.
El código no contiene drop, limpieza, migración ni referencia a bases financieras.
La auditoría de comandos comprobó que solo se usaron las bases creadas en esta
tarea y comandos administrativos de conexión/sesión/verificación. No es un sandbox
de permisos del servidor; la garantía depende de la URI fija, el nombre generado,
el código inspeccionado y los destinos efectivamente auditados.

Bases creadas y **retenidas**, ninguna eliminada:

- `test_c3_numbered_prototype_6116046d052d4330af146118cf5d22c8`: benchmark principal.
- `test_c3_numbered_prototype_5a8245b6c206459a817e04c3eafa289c`: primera ejecución de límites, 13 casos.
- `test_c3_numbered_prototype_e5464b03fb8c439dbd66a4b895b8da5e`: segunda ejecución ampliada, 17 casos.

La segunda ejecución no reutilizó la primera base. No se accedió a development,
Samsung, Emergent ni bases anteriores de auditoría. Solo se creó un índice
experimental de selección en una colección de la primera base **creada aquí**.

## Arquitectura experimental

1. `$match` por usuario efectivo y filtros de cuenta/categoría/tipo, incluidas
   transferencias por ambos extremos.
2. Campos temporales calculados: regex ISO, conversión de segundos sin fracción a
   BSON Date, reconstrucción exacta de microsegundos como entero de 64 bits,
   conversión del importe a decimal y marca de validez. No modificar originales.
3. Verificación de candidatos inválidos, conteo completo y lectura de página son
   agregaciones distintas dentro de una transacción de **solo lectura**, con
   `readConcern: snapshot`. Así el conteo y los documentos corresponden al mismo
   snapshot de esa respuesta; la siguiente petición inicia otra vista viva.
4. Ventana temporal antes de ordenar/paginar. Órdenes recent/oldest por fecha e ID;
   high/low por importe, con fecha DESC e ID DESC para desempatar ambos.
5. Proyección compacta de claves antes de `$sort`; `$skip` y `$limit: 20`.
6. Recuperación por `_id` de los 20 documentos originales dentro del mismo snapshot.
   Los campos temporales no aparecen en los documentos recuperados.

No se ha implementado un endpoint, cursor nuevo ni contrato público definitivo.
Es una alternativa para evaluar páginas numeradas; preservar el cursor v1 existente
sería parte de una integración posterior. El parser y los ordenamientos son experimentales.
Las etapas son exclusivamente de lectura: no `$out`, `$merge` ni JavaScript servidor.
El generador, y solo él, inserta/edita datos sintéticos para preparar las pruebas.

## Datos y equivalencia

Colecciones de 501, 2.001, 10.001, 50.001 y 100.001 documentos (162.505 en total),
con usuarios sintéticos distintos, seis tipos, categorías, cuentas, offsets,
microsegundos, fechas sin zona y días sin hora, importes repetidos, cero/negativos
heredados y `null`. Cada documento de carga tiene 2.048 caracteres de notas para
observar el coste de ordenar documentos completos frente a claves compactas.
No existen saldos ni usuarios reales; las cuentas son identificadores ficticios.

El benchmark principal aprobó **128 comprobaciones**. Compara IDs ordenados,
conteo y última página con una referencia Python independiente, no solo códigos
de respuesta. Incluye cuatro órdenes, primera/segunda/intermedia/última página,
ventanas y filtros combinados, errores de página, historial inválido y cambios
entre consultas. Las comparaciones de referencia pueden cargar claves completas
en Python; están fuera de los tiempos y mediciones de memoria de las consultas.

La última suite de límites produjo **15 equivalencias y 2 discrepancias** entre
17 casos. Incluye transferencias entrantes/salientes y autorreferenciadas, usuario
distinto, destino de gasto ordinario, ventana vacía, fracciones de 9 dígitos
(truncadas a microsegundos igual que Python), época anterior a 1970, bisiestos,
hora DST repetida, floats cercanos y fechas inválidas.

Bloqueos confirmados de compatibilidad:

- `20261001T120000Z`: válido para el lector Python actual; rechazado por la regex experimental.
- `2026-10-01T12:00:00+01:02:03`: offset con segundos aceptado actualmente; rechazado por el prototipo.

No se ocultaron ni repararon esas discrepancias. Fechas inválidas como
`2026-02-29T12:00:00Z` fueron rechazadas correctamente; no se normalizaron a otro día.

## Latencia real medida

Tres repeticiones por combinación, después de una consulta de calentamiento.
Medianas en milisegundos, rangos entre los cuatro órdenes. Incluyen validación,
conteo, selección, recuperación de documentos y cierre de la transacción.
No son tiempos de HTTP, Expo ni Samsung. No hubo aislamiento de CPU ni prueba
de carga concurrente sostenida; no representan p95 ni caché fría.

| Documentos insertados | Coincidentes del usuario | Última página | Primera página | Última página |
|---:|---:|---:|---:|---:|
| 501 | 471 | 24 | 19,5–20,9 ms | 19,0–20,0 ms |
| 2.001 | 1.883 | 95 | 56,8–56,9 ms | 56,0–57,6 ms |
| 10.001 | 9.412 | 471 | 259,0–262,3 ms | 264,0–269,6 ms |
| 50.001 | 47.059 | 2.353 | 1.241,5–1.260,2 ms | 1.306,9–1.336,5 ms |
| 100.001 | 94.118 | 4.706 | 2.456,6–2.497,4 ms | 2.583,6–2.651,0 ms |

Se midieron 80 combinaciones y 240 consultas cronometradas, además de calentamiento,
comprobaciones, explain y consultas de casos límite. El coste crece principalmente
con el conjunto filtrado; la profundidad aumenta el tamaño de top-k y la selección.
La base no se limpió. La prueba de inserción añadió un documento; la prueba de edición
cambió la fecha de un documento sintético después de los benchmarks.

## Memoria y disco

`tracemalloc` observó picos por consulta de aproximadamente **38–193 KiB** en el cliente
Python. No mide buffers nativos, RSS total, ni memoria del servidor. El oracle de
referencia no está incluido. Por tanto, no es una prueba de memoria total constante.

`explain executionStats`, última página, orden recent:

| Documentos | Claves compactas, tamaño estimado | Documentos completos, tamaño estimado | Spills completos | Disco ocupado por spills |
|---:|---:|---:|---:|---:|
| 50.001 | 25.741.273 bytes, sin disco | 171.460.746 bytes | 2 | 8.639.504 bytes |
| 100.001 | 51.482.546 bytes, sin disco | 342.921.484 bytes | 4 | 17.287.605 bytes |

Son métricas del sorter reportadas por MongoDB, **no RSS ni pico exacto de RAM**.
El tamaño crece con la página. El límite de memoria del motor y `allowDiskUse=True`
permiten derramar el ordenamiento, pero consumen disco/IO y no garantizan latencia.
No se observaron spills de claves compactas hasta 100.001 documentos: no demuestra
que no los haya con un historial mayor. No se modificaron parámetros del servidor.
El sort se ejecuta fuera de `$facet`, evitando depender de límites de memoria de ese stage.

## Índice experimental y concurrencia

Para una consulta combinada sobre 100.001 documentos:

- Antes del índice: COLLSCAN, 100.001 documentos examinados, 71 ms de explain.
- Tras `(user_id, category_id, type)`, **solo en la base nueva**: IXSCAN, 7.843
  documentos y 7.845 claves examinados, 27 ms de explain.

Esto mide la selección de una consulta, no la latencia end-to-end de todos los órdenes.
Los campos calculados no aprovechan ese índice para ordenar. Índices de cuenta y
categoría pueden reducir candidatos; orden indexado por fecha exacta normalizada
requeriría una decisión de esquema separada. No se recomienda backfill automático.

Inserción entre dos solicitudes: se observó una fila repetida por desplazamiento
de offset y el conteo pasó de 94.118 a 94.119. Una edición cambió la primera página.
Esto confirma vista viva, no un historial inmóvil a través de la navegación. No se
probaron escritores financieros reales, concurrencia sostenida ni commits inciertos:
el prototipo no realiza operaciones financieras.

## Archivos y reproducción

- `backend/experiments/c3_numbered_mongodb.py`: agregación y benchmark aislado.
- `backend/experiments/c3_numbered_edges.py`: pruebas reales de equivalencia adicionales.
- `backend/experiments/test_c3_numbered_prototype.py`: 7 comprobaciones offline.
- `backend/experiments/results/*.json`: tres informes sintéticos con medidas y auditoría.

Los comandos con `--execute` crean otra base **nueva** y la conservan, no reutilizan
las anteriores. No volver a ejecutarlos sin autorización para esa operación.

```sh
python3 -B -m unittest backend.experiments.test_c3_numbered_prototype -v
# Con autorización de nuevas bases:
python3 -B -m backend.experiments.c3_numbered_mongodb --execute
python3 -B -m backend.experiments.c3_numbered_edges --execute
```

## Veredicto

**NO APTO para producción todavía.** La arquitectura demostró páginas numeradas,
conteos y ordenamiento exacto en el subconjunto probado, con memoria acotada en el
cliente. No conserva todos los formatos heredados actuales y a 100.001 documentos
las consultas completas superan 2,4 segundos aun después de calentamiento.

Antes de integrar: resolver equivalencia completa de formatos o aprobar explícitamente
una política de historial no verificable; establecer presupuesto de latencia, memoria,
disco y tiempo máximo; probar mayores cargas y simultaneidad; validar el ensamblaje con
cursores v1. Nada de ello autoriza migraciones, cambios de producción o activación R4.
