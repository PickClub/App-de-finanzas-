# C3 — Prototipo mínimo de diagnóstico consistente: solo adaptadores falsos

Tres archivos nuevos, separados de producción y experimentos anteriores. No
conecta a MongoDB, no importa runners reales, no lee .env ni resultados de bases,
no persiste secrets/checkpoints/manifests y no implementa correcciones/backfill.
No se reutiliza como snapshot actual el T histórico de la validación anterior.

## Arquitectura de lectura

`run_diagnosis(reader, authorization, observation, T, limits, clock)` orquesta
operaciones experimentales de solo lectura. T debe ser BSON Timestamp. Request
inmutable incluye T, binding de destino/contexto/autorización, read_concern=snapshot,
límites y deadline monotónico. No existe código que acepte un fallback a majority,
local o una nueva T dentro del mismo run.

Reader es un Protocol con tres operaciones:

- inventory(request): respuesta exhaustiva con conteos por tipo BSON.
- page(request, partition, after): página por `_id` físico dentro de partición.
- duplicates(request): stream de respuestas ordenadas por ID lógico y `_id`.

Cada Response devuelve el T y binding que el adaptador acredita, documentos BSON
privados y agotamiento explícito. El controlador compara T/binding antes de consumir
cada lote. Diferencia, respuesta malformada, ausencia de progreso o datos posteriores
al agotamiento detienen el run. El adaptador falso conserva una copia BSON de un
fixture pequeño; su ordenación/materialización no es arquitectura escalable.

**No hay adaptador real.** Un adaptador MongoDB futuro debe comprobar/suministrar
la evidencia: comandos iniciales readConcern snapshot+atClusterTime, getMore en
su misma sesión con el cursor anclado a T, sesión no causal y pins R6/UUID.
MongoDB no necesariamente devuelve atClusterTime en cada getMore; la atestación
del adaptador debe derivarse del cursor/comando inicial y su vinculación comprobada,
no inventar una garantía porque Response.T tenga el valor esperado.

El adaptador debe administrar/limpiar sus cursores y sesiones, respetar timeouts
y cancelar solicitudes; el orquestador offline no posee recursos reales ni puede
interrumpir una llamada nativa bloqueada. El deadline se comprueba antes/después
de operaciones y pasos del stream; es cooperativo, no un watchdog físico.

## Pasos del run

1. Validar autorización diagnose y contexto R6 mediante el contrato puro existente.
2. Inventariar los tipos y total del ámbito completo en T.
3. Rechazar cualquier tipo no admitido, sin excluirlo silenciosamente.
4. Recorrer int32/Int64, string, Binary y ObjectId en ese orden; dentro de cada
   partición ordenar por `_id` y comprobar avance estrictamente creciente.
5. Verificar usuario/ID lógico, tipos físicos y claves mediante inspect_history_keys
   y derive_history_keys canónicos; conservar fuentes originales BSON.
6. Comparar conteos observados por tipo con inventario y límite de documentos.
7. Analizar duplicados en la misma vista T, con comparación literal adyacente de
   `(id lógico, _id físico)`. Mantener solo la identidad/grupo anteriores y contadores.
8. Exigir fin explícito de duplicados y el mismo total que el inventario.
9. Producir resultado agregado solamente después de completar todos los pasos.

IDs mixtos usan el subconjunto de orden BSON validado por experimentos anteriores.
Los wrappers Binary subtipo 0/bytes conservan codificación y tipos del contrato.
No hay query builder nuevo ni paginación numérica sobre datos funcionales.
La implementación MongoDB del stream duplicado/continuación queda pendiente; no
traducir su orden mixto a un `$gt` ingenuo entre tipos.

El contrato confía en un Reader correcto además de comprobar orden/conteos/T. Un
adaptador que mienta sobre documentos o T no queda autenticado por este modelo;
los conteos iguales solos no demuestran identidad de todos los documentos. Una
certificación real requiere evidencia de snapshot y scope, pins/DDL y manifest
independientes. No se afirma que este algoritmo detecte un proveedor malicioso.

## Claves e integridad financiera

Conteos missing, ready, stale_or_corrupt, unverifiable e incompatible, más fuentes
no verificables y duplicados. Una fila missing con fecha inválida se cuenta como
missing y como fuente no verificable. Nunca reparar, añadir ni actualizar claves.

Un recorrido puede ser `completo_a_T` y contener todos esos defectos. Indicador
`keys_ready_at_T` solo es true cuando toda la vista es ready, fuentes verificables
y no hay duplicados. No verifica saldos, recibos, vínculos de pagos ni legitimidad
de importes: `financial_correctness_asserted=false` siempre.

`certificate_issued=false` e `indexed_reads_allowed=false` siempre, incluso en
fixtures perfectos o vacíos. No habilita flags ni propone que el estado a T acredite
las filas posteriores o el historial financiero vigente.

## Presupuestos y fallos

Valores predeterminados:

| Presupuesto | Valor |
|---|---:|
| Documentos por respuesta | 100, máximo autorizado por modelo 1.000 |
| BSON por respuesta | 1 MiB, máximo 4 MiB |
| Documentos financieros del ámbito | 10.000 |
| BSON acumulado en todos los recorridos | 32 MiB |
| Respuestas/lotes | 10.000 |
| Tiempo cooperativo del run | 30 segundos |

Inventario también debe caber en una respuesta limitada; configurar presupuesto
suficiente para todos los tipos admitidos. Límite de documentos se comprueba antes
de recorrer y durante físico/duplicados. BSON se contabiliza en todos los pasos,
no solo en la página financiera. No medir RSS a partir de este presupuesto: el
adaptador/driver pueden tener buffers antes de entregar una respuesta rechazable.
No hay mediciones nuevas MongoDB, red ni memoria nativa.

Errores `CursorNotFound` 43 y ConnectionFailure -> `incompleto`, con código público
fijo y sin reintento/fallback automático. SnapshotTooOld 239 y SnapshotUnavailable
246 -> `abortado`. Errores de base desconocidos, T/contexto diferentes, inventario
inconsistente, presupuestos o BSON inválido también abortan. Ninguno declara un
resultado completo o claves sanas. No publicar mensajes brutos de excepciones ni
contenidos del adaptador; códigos no reconocidos se convierten en error genérico.

El prototipo no implementa checkpoint durable ni reanudación de progreso parcial.
Una futura sesión nueva solo podrá reabrir el mismo T bajo política protegida y
retención disponible; mientras tanto se reinicia el run explícitamente y no se
mezclan conteos de intentos. No añadir secretos HMAC en esta etapa.

## Pruebas offline y límites

`python3 -B -m unittest backend.experiments.test_c3_consistent_diagnosis_prototype -v`

28 pruebas con respuestas sintéticas: T uniforme, divergencia por cada recorrido,
binding cambiado, estados heredados, duplicados entre lotes, mezcla BSON, cursor/
snapshot/conexión perdidos, inventario y stream incompletos, BSON malformado,
autorización, límites de documentos/bytes/requests/deadline, sanitización de errores
y conservación de entradas. No ejecutan clientes ni consultan bases anteriores.

Pendiente para una futura prueba sintética autorizada: implementar solo Reader real
aislado; verificar atestaciones y timestamps/cursor, read-only efectivo, presupuesto
de red/memoria, cancelación/cleanup, no spill/no índices adicionales, T perdido,
DDL/contexto y scope. El prototipo es APTO como base de esa prueba, no como herramienta
operativa ni certificación. El experimento anterior no se repite en esta tarea.

Verificación de esta entrega: 28 pruebas nuevas aprobadas; 152 offline en conjunto
(28 + 24 consistencia + 23 diseño MongoDB + 39 diagnóstico offline + 38 contrato),
sin fallos. No se ejecutaron suites financieras generales, benchmarks ni MongoDB.
Sintaxis, operaciones restringidas y whitespace comprobados. Hashes de todos los
archivos anteriores conservados; solo se crean los tres archivos de esta etapa.
