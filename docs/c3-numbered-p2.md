# C3 3A-P2 — Experimento, no integración

Producción intacta. Rama `conflict_280926_1750`, HEAD
`1ca9972b748dee2ebf613fef1bea7b89e5537b4f`. Los siete archivos de P1
se conservaron byte por byte; no se reutilizaron sus bases.

## Destinos y evidencia

MongoDB local 8.0.32 en `127.0.0.1:27018`, PRIMARY de `app_finanzas_dev_rs`.
Se utilizó URI fija sin secretos, sin leer `.env`. Antes de crear cada base:
verificación de host/replica set/PRIMARY y `listDatabases` filtrado por el nombre
UUID exacto. Auditoría de comandos: cero destinos inesperados y cero eliminaciones.

Tres bases P2 nuevas, **retenidas sin limpieza**:

- `test_c3_numbered_p2_5e7a4bfb7c054a959c4c40f95b238aa0`: benchmark.
- `test_c3_numbered_p2_b4004c11779f4f47bfb167dcefc18c15`: primera prueba adversarial/mantenimiento.
- `test_c3_numbered_p2_b570630b64834f51b4ecbe1b6af75011`: prueba ampliada con filtros.

Los índices y claves materializadas se crearon únicamente en estas bases nuevas,
para simular un diseño futuro. No se aplicó un cambio de esquema o backfill real.

Informes JSON originales: `backend/experiments/results/test_c3_numbered_p2_*.json`.
La documentación distingue la ejecución principal y la repetición ampliada;
no suma comprobaciones repetidas como cobertura nueva.

## Estrategias

| Estrategia | Lectura | Coste y mantenimiento |
|---|---|---|
| Control P2 | Validación, conteo y orden en tres agregaciones | Parser nuevo repetido tres veces; sin claves persistidas |
| Un recorrido | Normalización, sort global fuera de facet, ramas de invalidación/conteo/página | Evita tres recorridos; normaliza N y ordena el conjunto; puede derramar a disco |
| Claves indexadas | Entero UTC de microsegundos y Decimal128 calculados con Python, tres índices de orden | Necesita mantener claves y versiones atómicamente; no autorizado en producción |
| Híbrida | Saltos numerados por ruta global; navegación secuencial con condición estricta de clave y top‑20 dentro de facet | Mantiene todas las funciones; ahorra memoria en avance secuencial, pero el conteo/normalización siguen recorriendo N |

Órdenes: recent/oldest por fecha e ID; high/low por importe con fecha DESC e ID
DESC en empates. 20 resultados por página; filtros antes de selección. Cuenta incluye
ambos extremos únicamente para transferencias. Ventana temporal semiabierta sobre
la clave normalizada. Conteo y documentos usan la misma transacción read-only snapshot.
Las solicitudes posteriores siguen siendo una vista viva.

La ruta híbrida usa una clave experimental en memoria, **no el cursor público v1**.
No demuestra integración de los cursores existentes ni habilita un contrato nuevo.
El sort global se sitúa fuera de facet para permitir spills; el top‑20 secuencial
dentro de facet permanece pequeño. No se ejecutan `$out`, `$merge` ni JavaScript.

## Compatibilidad

Los dos defectos de P1 quedaron corregidos en el experimento y verificados en MongoDB:

- `20261001T120000Z` y fracciones de microsegundos en formato básico.
- Offsets `+01:02:03`, `-01:02:03` y offsets con fracciones de segundo.

Se reconstruye la fecha como segundos BSON y se suma la fracción de microsegundos,
restando el offset como duración exacta. No se modifica la cadena original.
Se comprobaron epoch negativa, nueve dígitos fraccionarios truncados como Python,
bisiestos, offsets/minutos históricos y hora repetida DST.

La ejecución principal aprobó **140 comparaciones** de páginas/totales y 12 casos
temporales; la última prueba adversarial aprobó **15 de 18** casos. Los tres fallos:

1. `2026-1001T120000Z`: Python rechaza el formato mixto; la regex P2 lo admite.
2. `2026-10-01T12:0000Z`: mismo problema con separadores de hora.
3. `2026-W40-4T12:00:00Z`: Python admite ISO de semana; P2 lo rechaza.

Estos defectos siguen visibles, con tres expected failures offline y resultados
reales registrados. No se afirma compatibilidad completa con `datetime.fromisoformat`.
La corrección futura exige gramática estricta/equivalente, o una política explícita
para formatos no verificables. No reparar ni reinterpretar historial automáticamente.

## Latencia real

Tres repeticiones tras calentamiento, sin HTTP/Expo ni aislamiento de CPU; medianas
entre cuatro órdenes. Los tiempos incluyen snapshot, consulta(s), recuperación de
documentos por ID y cierre. Son 140 combinaciones y 420 consultas cronometradas,
además de calentamiento, controles y explain. La base principal conserva 501, 2.001,
10.001, 50.001 y 100.001 documentos sintéticos en colecciones diferentes.

| Documentos | Un recorrido, primera / última | Claves indexadas, primera / última | Híbrida, segunda |
|---:|---:|---:|---:|
| 501 | 11,9–12,9 / 12,0–12,5 ms | 3,4–4,0 / 5,0–6,4 ms | 12,2–13,1 ms |
| 2.001 | 32,6–34,0 / 31,6–34,0 ms | 3,9–4,9 / 10,9–12,3 ms | 32,8–33,5 ms |
| 10.001 | 149,7–155,3 / 145,6–159,0 ms | 4,5–5,4 / 40,0–52,9 ms | 143,9–150,9 ms |
| 50.001 | 766,4–842,3 / 774,5–845,7 ms | 8,0–8,7 / 67,9–133,1 ms | 760,4–799,7 ms |
| 100.001 | 1.790,3–1.946,5 / 1.811,5–1.944,2 ms | 11,7–13,0 / 139,7–245,8 ms | 1.510,1–1.536,7 ms |

Últimas páginas: 24, 95, 471, 2.353 y 4.706, respectivamente (se excluye el otro
usuario sintético). El control P2 de 100.001 documentos dio 4.046–4.221 ms.
No comparar esa cifra directamente con los 2,6 s de P1: cambió el parser y el conjunto
incluye los formatos nuevos. La comparación válida es entre estrategias del mismo P2.

### Separación de costes: límites de la medición

Controles independientes de 100.001 documentos, medianas observadas:

- Filtrado más conteo simple: 8,547 ms.
- Filtrado, normalización y conteo: 1.292,005 ms.
- Filtrado, normalización, sort y conteo: 1.702,141 ms.
- Filtrado, normalización, sort y selección de última página: 1.457,001 ms.

Son consultas completas de control, **no tiempos exclusivos de cada operador**.
No se restan y publican diferencias como CPU real de normalización/sort/skip.
El optimizador y el ruido pueden modificar/eliminar trabajo. Explain proporciona
`executionTimeMillisEstimate` por stage, tampoco una atribución independiente exacta.
No se obtuvo un perfil fiable de tiempo exclusivo de cada fase o RAM RSS del servidor.
Las métricas disponibles se conservan en JSON sin inventar las que faltan.

## Memoria, disco y metodología

Picos de asignaciones Python por consulta: 37.224–229.132 bytes (tracemalloc).
No incluyen buffers nativos, RSS, oracle ni memoria MongoDB. La referencia ordena
claves completas fuera de las ventanas cronometradas; eso no es la arquitectura cliente.

Sort global P2 de 100.001 documentos: tamaño estimado de datos 146.129.556 bytes,
`usedDisk=true`, 2 spills, 4.561.707 bytes de almacenamiento de spills. No es un pico
medido de RAM. Se excluyen notas de la proyección inicial, pero P2 retiene temporales
del parser durante el sort: compactarlos es una optimización aún no medida aquí.

El explain de top‑20 informó ~31.630 bytes y cero spills. **Limitación de instrumentación:**
el benchmark original generó ese explain de recent con el ancla final de low, no con
el ancla correcta de la segunda página recent. Sirve para observar el mecanismo top‑20,
no para atribuir coste a esa página concreta. Los tiempos y comparaciones híbridos sí
usan el ancla correcta de cada orden. Se corrigió el generador para futuras ejecuciones,
sin reescribir informes ni volver a consultar la base retenida.

No se midió caché fría, p95, saturación concurrente ni historiales mayores de 100.001.
No hay garantía de memoria constante, disco ilimitado o latencia constante.

## Mantenimiento e índices futuros

Tres índices experimentales: usuario+fecha+ID (también sirve en sentido inverso),
usuario+importe DESC+fecha DESC+ID DESC, y usuario+importe ASC+fecha DESC+ID DESC.
El build conjunto sobre 100.001 documentos tardó 754 ms en la ejecución principal.

Última prueba de mantenimiento, lotes de 500 documentos, tres muestras tras calentamiento:

- Sin índices de orden: mediana de inserción 6,664 ms.
- Con tres índices de orden: 9,656 ms.
- Preparar los documentos/claves en Python: aproximadamente 2,9–3,7 ms por lote.

Es inserción sintética local, no costo de transacciones MoneyFlow ni estimación de carga
real. Las estadísticas de tamaño de índices se leyeron inmediatamente tras insertar;
no representan tamaño estabilizado tras checkpoints/compactación.

Claves materializadas exigirían actualizaciones atómicas al editar fecha/importe,
consistencia con referencias históricas, validación de versiones y una política
para datos antiguos. No existe autorización para backfill, esquema o integración.
El conteo exacto sigue teniendo coste proporcional al conjunto, aunque recorra índices.
Los filtros combinados pueden exigir otros índices; no se infiere que los tres cubran
todas las consultas. La alternativa de un recorrido no exige mantenimiento de claves,
pero paga conversión y sort en cada solicitud.

## Vista viva y recomendación

Inserción entre páginas: conteo 94.118 → 94.119 y una fila repetida por desplazamiento.
Editar la fecha cambió la primera página. Snapshot asegura coherencia dentro de una
respuesta; no congela el historial entre peticiones. No se ejecutaron operaciones
financieras reales ni tests de escritores de producción.

**NO APTO para integrar en producción todavía.** Los dos formatos de P1 funcionan,
pero permanecen tres incompatibilidades confirmadas. La estrategia indexada es
prometedora para conservar saltos, última página y orden por importe; necesita
aprobación de mantenimiento/esquema e historial previo. La híbrida conserva funciones
y limita el top‑20, pero no elimina el coste del conteo/normalización completa.

Siguiente decisión: completar equivalencia estricta del parser experimental antes de
integrar; evaluar compactación medida y, por separado, aprobar o descartar claves
persistidas futuras. No comenzar producción, activar R4 o migrar historial por este informe.

Archivos nuevos P2: dos scripts de experimento, un test offline, tres informes JSON
de esta ejecución y este documento. Comandos opt-in crearían **otra base nueva**;
no ejecutarlos de nuevo sin autorización. Todos los destinos actuales quedan retenidos.
