# C3 — Adaptador snapshot experimental: extremo a extremo

No es integración de producción. No se modificó el prototipo ni ningún experimento
anterior. Solo se crean adaptador, tests, runner, dos resultados y este documento.
No se activan flags, no se cambia infraestructura y no se crean índices explícitos.

## Aislamiento y dos intentos conservados

Base final: `test_c3_adapter_d2d2f6a3991c4397b55059264c0a4835`.
La ausencia se comprobó antes de la primera escritura del runner. Destino directo
127.0.0.1:27018, PRIMARY app_finanzas_dev_rs, MongoDB 8.0.32. R6 propio sintético:
`b939b0c3-3183-47a9-b958-840249d36c42`. UUID físico transactions:
`3ea5230836064c05969219d53c0d7225`.

Primer intento: `test_c3_adapter_0e1b912d70144fdab6b8a0f367e89e3c`, igualmente
nuevo. El diagnóstico no llegó a completarse; el runner detuvo la ejecución antes
de realizar los cambios posteriores a T. No se reutilizó ni limpió esa base.
El primer artefacto conserva métricas/fallo de assertion, pero no el informe
interno fallido: esa limitación de trazabilidad se corrigió en el runner nuevo
para la ejecución final, sin modificar el artefacto anterior de este intento.

Diagnóstico del fallo: la ruta genérica `db.command` dentro de `pymongo.timeout`
inyecta maxTimeMS incluso para getMore. El driver instalado lo muestra en
Connection.apply_timeout/network.command. Se reprodujo offline la inyección;
MongoDB no acepta maxTimeMS en ese getMore no-awaitData. El adaptador nuevo pasó
a usar CommandCursor, cuya ruta GetMore aplica el timeout con cmd=None, sin
introducir ese campo. La repetición fue completa en otra base nueva.

No se consultaron datos de bases anteriores ni producción. La auditoría admite
únicamente esta base y admin para hello/buildInfo/listDatabases (solo nombres) y
cierre de sesiones. R6/current-user aquí es un fixture de consistencia; no prueba
la identidad de un entorno financiero real ni autentica usuarios.
Las bases se conservan; solo tienen `_id_` implícitos de MongoDB.

## Adaptador compatible sin cambiar el prototipo

MongoSnapshotReader implementa inventory, page y duplicates y se usa como contexto
alrededor de run_diagnosis. El contexto registra y cierra recursos, incluso cuando
el controlador abandona un generator de duplicados por fallo o presupuesto.
Puede cerrar también el cliente cuando own_client=True.

Cada solicitud valida T/binding/readConcern/deadline. Antes de abrir una lectura,
comprueba endpoint, PRIMARY/setName, UUID físico, R6 actual y R6 histórico a T.
Las lecturas de identidad actuales son controles administrativos separados; no
se confunden con las lecturas históricas de movimientos.

Find/aggregate iniciales se envían con snapshot+atClusterTime explícito. Se rechaza
un timestamp divergente si el servidor lo devuelve y cualquier respuesta parcial.
CommandCursor mantiene el contexto del cursor/sesión no causal para getMore;
no se solicita otro readConcern ni T al continuarlo. No se afirma que cada reply
getMore repita explícitamente T: la evidencia combina comando inicial, vínculo
inmutable del cursor y la garantía del driver. El adaptador nunca selecciona
silenciosamente un nuevo snapshot para una consulta posterior.

Las páginas usan filtros por partición, orden `_id`, proyección mínima y una fila
de anticipación para conocer agotamiento/presupuesto de bytes. Si se corta antes
por tamaño, la siguiente consulta a T empieza tras la última fila entregada; la
fila anticipada no se descarta del historial. Documento individual demasiado
ancho aborta. Inventario incompleto/oversize también aborta en lugar de truncarlo.

Duplicados usan un cursor ordenado lógico/físico a T, con lotes por documentos y
bytes y comparación del prototipo original. No hay writes, backfill o reparación
en el adaptador. Las claves iniciales de fixtures se crean únicamente por el
runner de preparación sintética, no por el diagnóstico.

## T y escenarios finales: 11/11

T obtenido de atClusterTime de un find snapshot inicial:
`Timestamp(1791923543,8)`.
Fixture de 2.001 documentos, tipos físicos mixtos y 1.000 pares con ID lógico
duplicado. Estados: ready=401; missing, stale_or_corrupt, unverifiable e incompatible
=400 cada uno. El run completo a T devuelve keys_ready_at_T=false y nunca certificado.

| Escenario | Resultado |
|---|---|
| Aislamiento y T servidor | Base ausente, pins locales y snapshot seleccionado |
| Diagnóstico completo | completo_a_T, 2.001 filas y 1.000 grupos duplicados |
| Escrituras posteriores | Dos inserts, un update y un delete sintéticos; mismo diagnóstico a T, vivo=2.002 |
| Cursor eliminado | killCursors real: incompleto/cursor_lost, sin éxito |
| Snapshot no disponible | T antiguo: abortado/snapshot_unavailable, sin éxito |
| Red inyectada | ConnectionFailure artificial: incompleto, limpieza de cursor |
| Límite de documentos | abortado/document_budget_exceeded |
| Límite BSON por respuesta | abortado/batch_budget_exceeded |
| Límite BSON acumulado | abortado/total_budget_exceeded |
| Deadline | abortado/deadline_exceeded, sin abrir sesiones |
| Páginas mayores | 1.000 por respuesta, mismos conteos y duplicados a T |

Auditoría de comandos: **81 lecturas iniciales de diagnóstico**, cero sin el T
esperado; cero getMore con maxTimeMS. Los únicos otros anchors corresponden al
probe negativo explícito de snapshot antiguo. Cero comandos a bases ajenas.
No hubo spill: find/aggregate del diagnóstico fijan allowDiskUse=false.

Cada run termina sin handles activos, sessions_opened=sessions_closed y
cleanup_errors=0. La primera ejecución fallida también cerró sus dos sesiones.
No se modifica payment_transaction ni se introduce transacción anidada.

## Costes observados

| Run completo | Tiempo cliente | Pico Python trazado | Sesiones | getMore |
|---|---:|---:|---:|---:|
| Inicial, respuestas 50 | 1.659,013 ms | 291.821 bytes | 44 | 102 |
| Tras escrituras, respuestas 100 | 1.553,508 ms | 473.034 bytes | 24 | 122 |
| Respuestas 1.000 | 1.469,948 ms | 2.017.190 bytes | 6 | 122 |

RSS actual antes/después: inicial 66.744.320→66.949.120 bytes; segundo
66.994.176→67.080.192; respuestas mayores 67.932.160→68.993.024.
Son runs únicos en el mismo proceso/host, con tracing y guards por petición;
no p95 ni extrapolación a historiales grandes. No se midió RSS del servidor.

Reply BSON máximo observado: find=9.936 bytes, getMore=9.958, aggregate=2.970.
No son bytes de transporte ni garantía de memoria nativa. El driver recibe y
decodifica antes de que se aplique presupuesto de Response; un BSON grande puede
superar ese presupuesto en el buffer previo. Los límites verificados corresponden
al procesamiento/resultado, no un límite físico absoluto de RSS.

CSOT acota operaciones del driver y el deadline del controlador se valida entre
pasos. Puede haber latencia de cancelación/cleanup; no se afirma precisión de
reloj absoluta. Las pruebas de snapshot antiguo y red no son una caducidad natural
del T elegido ni caída física de red/PRIMARY. No se reconfiguró MongoDB.

## Límites pendientes y veredicto

APTO para el siguiente diseño/prueba controlada de C3, sin autorización de uso
operativo o datos reales. Aún faltan: fixtures BSON grandes, cargas altas y memoria
nativa/servidor, expiración natural, caída de proceso/elecciones, sustitución de
colección y permisos read-only independientes. La auditoría cliente no reemplaza
controles de acceso. HMAC durable/manifests y certificación siguen pendientes.

Un recorrido completo a T puede contener defectos y no prueba corrección financiera.
Este fixture deliberadamente contiene claves defectuosas y duplicados. El adaptador
no remedia nada ni habilita lecturas indexadas. T histórico tampoco acredita filas
posteriores. No es un producto publicado ni un endpoint público.

## Archivos nuevos

- backend/experiments/c3_snapshot_mongodb_reader.py
- backend/experiments/test_c3_snapshot_mongodb_reader.py
- backend/experiments/c3_adapter_end_to_end_validation.py
- backend/experiments/results/test_c3_adapter_0e1b912d70144fdab6b8a0f367e89e3c.json
- backend/experiments/results/test_c3_adapter_d2d2f6a3991c4397b55059264c0a4835.json
- docs/history-snapshot-reader-validation.md

No reejecutar el runner contra esas bases: exige ausencia y no hace limpieza.
Los tests de adaptador son offline y usan dobles de client/cursor. Incluyen la
reproducción del comportamiento CSOT del driver instalado, sin ninguna conexión.

Verificación offline final: 163/163 pruebas aprobadas (11 del adaptador, 28 del
prototipo, 24 política de consistencia, 23 diseño, 39 diagnóstico offline y 38
contrato administrativo). No se presentan los 14/14 del experimento anterior como
nueva ejecución. Sintaxis y whitespace comprobados. Hashes de todos los archivos
anteriores intactos. Sin staging, commit, push ni modificaciones funcionales.
