# C3 — PLAN administrativo de solo lectura

Bloque 4C. Entrada independiente: `python3 -B -m backend.history_plan_cli`.
La CLI de diagnóstico registrada no cambia. No hay endpoint público, escritura,
APPLY, VERIFY, REVERT, bitácora, almacenamiento de planes ni archivos privados
emitidos automáticamente. Importar el módulo no crea conexiones ni abre archivos.

## Autorización y argumentos

Todos los argumentos son obligatorios:

- `--uri`: exactamente el destino local autorizado por Target,
  `mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true`.
- `--database`, `--collection`: destino aprobado; colección `transactions`.
- `--expected-collection-uuid`: UUID físico aprobado independientemente.
- `--expected-environment-id`: UUID R6 esperado aprobado independientemente.
- `--expected-user`: identidad efectiva `default-user`.
- `--version`, `--generation`: versión canónica y generación esperada.
- `--run-id`: UUID v4 canónico de la ejecución.
- `--approve-plan`: autorización explícita para lectura del ámbito completo.

No existen argumentos para subconjuntos, páginas sueltas, límites ampliados,
credenciales, reparación o salida de planes privados. No se carga `.env`.
Los UUID esperados no se obtienen del servidor para autoaprobar el destino.
`default-user` delimita el modelo single_user existente: NO es autenticación
humana, autorización multiusuario ni reemplazo de controles de acceso.

Esta etapa prueba la interfaz con adaptadores falsos. No autoriza ejecutar el
comando contra MongoDB real o datos financieros. Una validación sintética exige
aprobación separada, base nueva y comprobación previa de aislamiento.

## Reutilización y consistencia

Se reutilizan `MongoSnapshotReader`, `SnapshotAudit` y `build_plan`, sin duplicar
el parser, el recorrido tipado, la inspección canónica ni los controles R6.
El lector valida loopback, PRIMARY, replica set, MongoDB 8.0, UUID de colección e
identidad R6 actual. Selecciona T mediante lectura snapshot de metadata; vuelve a
comprobar identidad actual y a T antes de cada recorrido y al finalizar.
Inventario, documentos y duplicados usan exactamente el mismo BSON Timestamp T.
Las respuestas parciales, el cambio de namespace/contexto/T, pérdida de progreso
y diferencias de conteos invalidan la completitud. No hay reintentos automáticos
para sustituir T, fallback majority ni diagnóstico vivo alternativo.

El alcance siempre es todo el usuario efectivo autorizado. Las particiones físicas
admiten int32/Int64, string, Binary y ObjectId; otros tipos abortan. Los duplicados
lógicos se detectan globalmente, entre lotes y fechas. El lector usa solamente
comandos de lectura y cierre de cursores, sin disk spill ni índices nuevos.

## Candidatos, estados y códigos

Solo la ausencia real de `_history_keys` con derivación canónica ready produce
intención privada, conservando BSON físico tipado y fingerprint. Un bloque ready
correcto no se modifica. null, incompatible, stale_or_corrupt, unverifiable,
fuentes no verificables o duplicados bloquean el ámbito completo y descartan
las intenciones. Se conserva el contrato original del importe, incluido el fallback
canónico de orden para ausente/null; esto NO valida ni repara datos financieros.

| Estado público | Código | Significado |
|---|---:|---|
| complete_without_candidates | 0 | Cobertura completa a T, sin candidatos ni bloqueos |
| complete_with_candidates | 0 | Cobertura completa a T, candidatos privados solo en memoria |
| blocked | 2 | Cobertura completa a T con inconsistencias; cero intenciones emitidas |
| incomplete | 3 | Desconexión, pérdida de cursor o fallo de limpieza |
| aborted | 4 | Identidad, snapshot, límites, argumentos o protocolo inválidos |

El digest canónico se calcula sobre el PLAN interno (cuyo estado completo es
`complete`); las dos variantes públicas solo distinguen la cantidad de candidatos.
Es determinista con iguales contexto, ejecución, T y fuentes. No es firma ni
permiso, y el informe agregado no permite reconstruir las intenciones.
Un fallo de limpieza invalida completitud, elegibilidad y digest, con cero candidatos.
El plan interno no se devuelve, no se persiste y deja de estar retenido al salir.

Siempre son false: `apply_authorized`, `revert_authorized`,
`financial_correctness_asserted`, `certificate_issued`, `indexed_reads_allowed`.
Ningún código de salida autoriza APPLY, índices o lecturas optimizadas.

## Informes agregados

Se imprime un único JSON con run_id, hash no secreto de destino, T, versión,
generación, alcance, conteos, candidatos, duplicados, estado, digest, error fijo y
métricas agregadas del adaptador (sesiones, comandos, cierres, mayor respuesta BSON,
duración total). No hay documentos, IDs individuales, importes, fechas de
movimientos, URI, fingerprints individuales, propuestas BSON ni excepciones crudas.

Ejemplos de campos principales (el JSON real incluye el resto de campos y flags):

```json
{"state":"complete_without_candidates","complete_at_T":true,"candidate_count":0,"counts":{"missing":0,"ready":0,"stale_or_corrupt":0,"unverifiable":0,"incompatible":0}}
{"state":"complete_with_candidates","complete_at_T":true,"candidate_count":2,"counts":{"missing":2,"ready":0,"stale_or_corrupt":0,"unverifiable":0,"incompatible":0}}
{"state":"blocked","complete_at_T":true,"candidate_count":0,"duplicate_groups":1}
{"state":"incomplete","complete_at_T":false,"candidate_count":0,"error":"connection_failure"}
{"state":"aborted","complete_at_T":false,"candidate_count":0,"error":"snapshot_time_mismatch"}
```

## Límites y limpieza

Máximos: 100 documentos/1 MiB por lote, 10.000 movimientos, 32 MiB de BSON
procesado y plan, 10.000 respuestas y 30 segundos, incluyendo adquisición de T,
recorrido y digest. Exceso implica aborto, nunca truncamiento exitoso.
Se reutilizan maxTimeMS/CSOT del lector, sin añadir maxTimeMS incompatible a getMore.
La limpieza en finally intenta cerrar cursores, sesiones y cliente con el presupuesto
acotado de 2 segundos del adaptador. La duración reportada incluye limpieza.
Los bytes BSON no equivalen a RSS ni a memoria del servidor; no hay medición real
MongoDB en esta etapa. El sort global de duplicados puede alcanzar límites sin
índices: en tal caso se aborta, sin habilitar disk spill.

## Pruebas y límites de la evidencia

```bash
python3 -B -m unittest backend.tests.test_history_plan_cli backend.tests.test_history_provisioning backend.tests.test_history_diagnostics backend.tests.test_history_diagnose_cli -q
```

Los adaptadores falsos ensayan el lector registrado, comandos snapshot y limpieza;
no prueban retención real de snapshots ni rendimiento del servidor. Una colección
vacía solo es completa tras inventario, recorrido, duplicados e identidad final.
El resultado acredita cobertura de claves a T dentro de las garantías ensayadas,
no corrección financiera ni vigencia posterior a T. DDL, escritores externos,
expiración de snapshots y concurrencia requieren validación sintética posterior.
No se activan R4, escritura de claves ni lecturas indexadas.
