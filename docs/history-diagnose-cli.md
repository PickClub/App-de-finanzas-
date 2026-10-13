# C3 — Diagnóstico administrativo de claves históricas

CLI explícita, sin endpoint HTTP, conexiones al importar, carga de `.env`, escrituras,
backfill, reparación, índices, certificados ni activación de flags. Esta etapa se
valida únicamente offline: no autoriza ejecutarla contra MongoDB ni datos reales.
El adaptador operativo nuevo no importa módulos experimentales; los 45 archivos
experimentales se conservan como evidencia independiente.

## Ejecución futura, bajo autorización separada

Desde la raíz del repositorio, con el Python que tenga las dependencias existentes:

```bash
python3 -B -m backend.history_diagnose_cli \
  --uri 'mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true' \
  --database '<base-aprobada>' --collection transactions \
  --expected-collection-uuid '<uuid-fisico-aprobado>' \
  --expected-environment-id '<uuid-R6-aprobado>' \
  --expected-user default-user --version 1 --generation '<generacion-aprobada>' \
  --approve-diagnose
```

URI exacta, sin credenciales, únicamente loopback 127.0.0.1:27018 y replica set
app_finanzas_dev_rs. Se rechazan admin/local/config, otros destinos, colecciones,
usuarios, versiones y argumentos desconocidos antes de crear el cliente. UUID
físico, R6 y generación deben aprobarse independientemente: no copiar lo observado
para autoaprobarlo. No se crean metadatos R6 ausentes. No se consultan otras bases.
El operador debe controlar DDL y permisos de lectura durante la ejecución.
La validación cliente no sustituye controles de acceso independientes en MongoDB.

La identidad efectiva significa el valor `default-user` que el servidor actual
utiliza en el modelo single_user. Se impone como ámbito de consultas y se valida
en cada documento. No es autenticación multiusuario: una cabecera, R6 o este
argumento no prueban identidad humana ni autorización de acceso.

## Vista única y alcance

Se comprueban endpoint, PRIMARY, sesiones, MongoDB 8.0.x, UUID de transactions y R6
actual. Un find snapshot de la metadata R6 selecciona T; debe devolver un BSON
Timestamp explícito del servidor y un único registro R6 válido. Sin T no se sigue.
Los recorridos de inventario, particiones y duplicados usan snapshot con
atClusterTime=T. Cada operación comprueba UUID/R6 actuales y R6 histórico a T.
Se repite la comprobación antes de declarar completitud.

Los getMore usan CommandCursor del driver y su sesión explícita; heredan el cursor
snapshot. No inyectar readConcern nuevo ni maxTimeMS no permitido en getMore.
Un CommandListener inspecciona namespace, respuestas parciales y T reportado en
getMore, sin retener documentos; cualquier anomalía impide declarar completitud.
Los comandos iniciales tienen maxTimeMS de hasta 10 segundos, además del deadline
CSOT restante. Ante T divergente, respuesta parcial, pérdida de cursor, red o
snapshot, no seleccionar otro T silenciosamente.

Tipos físicos admitidos: int32 e Int64 en una partición numérica común, string,
Binary y ObjectId. Se conserva el tipo BSON al avanzar por `_id`; binario subtipo
0 decodificado como bytes se vuelve a representar como Binary subtipo 0.
Tipos no admitidos bloquean; no se omiten documentos. Colación simple explícita.
El ID lógico debe ser una cadena válida del mismo usuario efectivo.

Se clasifican missing, ready, stale_or_corrupt, unverifiable e incompatible mediante
history_keys.py. El parser de transaction_history.py conserva offsets, ISO básico,
semanas ISO, microsegundos y la convención UTC heredada, sin cambiar fuentes.
Derivación e inspección no modifican movimientos ni journals. Una fuente no
verificable se cuenta incluso si falta el bloque privado.

Duplicados se detectan sobre todo el ámbito con un flujo ordenado por ID lógico
y `_id` físico, conservando únicamente el grupo contiguo. Diferentes fechas no
permiten reutilizar un ID. Se concilian inventario, documentos y filas del flujo
de duplicados; cualquier falta de cobertura o progreso aborta.

## Límites y limpieza

Presupuestos fijos iniciales: 100 documentos y 1 MiB por respuesta procesada,
10.000 documentos por ámbito, 32 MiB acumulados de BSON procesado, 10.000 respuestas
y 30 segundos de trabajo incluyendo preflight. No hay argumento para aumentarlos.
Superarlos aborta; nunca convierte una exploración truncada en resultado completo.
El BSON contabilizado incluye los recorridos adicionales, no solo movimientos.

allowDiskUse=false; no se permite sort spill. La ordenación de duplicados puede
superar recursos del servidor sin índices: fallo seguro, nunca creación automática
de índices. Un futuro índice o cambio de presupuesto requiere autorización aparte.

Cursores y sesiones se registran y cierran en finally. Cada liberación y el cierre
final tienen un presupuesto adicional de hasta dos segundos mediante CSOT; se
intentan también si falla la operación anterior. Un error de limpieza invalida el
éxito y se informa sin texto del driver. No se envía killCursors a un namespace
distinto del aprobado, aunque lo mencione una respuesta inválida.

CSOT limita operaciones del driver, no impone una cota física absoluta a RSS ni
al tiempo del proceso. Buffers BSON se reciben/decodifican antes de comprobar su
presupuesto. Una terminación forzada o red caída no garantiza liberación inmediata
en el servidor; los cursores pueden depender de su expiración. Esto debe validarse
en una prueba sintética independiente antes de uso operativo.

## Informe y códigos

JSON único a stdout, sin documentos, IDs individuales, fechas de movimientos,
importes, URI, credenciales o excepciones completas. Incluye estado, T como
`{time, increment}`, versión/generación, destino vinculado por hash no secreto,
conteos, duplicados, fuente no verificable y métricas de procesamiento/limpieza.
No registra checkpoints persistentes ni crea archivos de resultados. Proteger
cualquier informe que el operador redirija y conservarlo fuera de Git.

| Código | Estado |
|---:|---|
| 0 | completo_a_T, sin bloqueos detectados; incluye ámbito vacío verificado |
| 2 | completo_a_T, con claves incompatibles/ausentes/obsoletas/no verificables o duplicados |
| 3 | incompleto por conexión/cursor o fallo de limpieza |
| 4 | abortado por destino, snapshot, argumentos, identidad, protocolo, cancelación o recursos |

Siempre: financial_correctness_asserted=false, certificate_issued=false,
indexed_reads_allowed=false. Una colección vacía solo se declara completa tras
verificar identidad, snapshot, inventario vacío, particiones y duplicados vacíos.
Un error con respuesta vacía nunca es éxito.

No hay reanudación persistente: después de interrupción, comenzar desde cero en
una nueva ejecución. T no garantiza retención futura ni datos posteriores a T.
UUID/R6 verificados no prueban ausencia de un cambio DDL no observado; excluirlo
operacionalmente. El diagnóstico no certifica saldos ni integridad financiera.
Bloque 4 exige nueva aprobación, ámbito y evidencia vigente; este informe no
autoriza apply/revert, provisión ni lecturas optimizadas automáticamente.

## Validación offline

```bash
python3 -B -m unittest backend.tests.test_history_diagnostics backend.tests.test_history_diagnose_cli -v
```

Pruebas con BSON artificial, relojes, driver y sesiones falsos. No ejecutan la CLI
contra MongoDB. La prueba de importación bloquea MongoClient y comprueba ausencia
de imports experimentales. Los ensayos reales previos del adaptador experimental
no cuentan como ejecución real de estos módulos operativos nuevos.
