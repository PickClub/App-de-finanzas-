# C3 — Runner sintético de APPLY, bloqueado para MongoDB

Bloque 4F. Implementación offline y preparación del contrato de prueba. No se ha
conectado MongoDB, preparado una base ni ejecutado APPLY real. Esta autorización
para desarrollar NO es autorización para una conexión o escritura posterior.

## Bloqueo operativo explícito

request_mongodb_execution devuelve blocked/external_exclusion_unproven sin crear
clientes ni utilizar factories, aunque reciba una supuesta aprobación. La entrada
main tampoco contiene una ruta ejecutable MongoDB: argumentos distintos de
--offline-tests generan ese mismo bloqueo y código de salida 4.
ExternalExclusionVerifier.verify siempre rechaza. No hay parámetro para omitirlo,
modo force, aceptación de lease/lock ni conversión de una aprobación de fixture
sobre una base real. El runner no incorpora MongoClient ni comandos de preparación
real. No se añadió un verificador que devuelva true para facilitar una prueba.

La configuración local examinada publica MongoDB en loopback y declara un replica
set; no aporta por sí sola exclusión demostrable de todos los clientes externos.
No se consultó el servidor para afirmar su configuración efectiva. Un nombre
aleatorio, una marca, un lease administrativo, snapshots o la ausencia de cambios
observados NO prueban que otro escritor no pueda operar durante la ventana.
Por esa razón se aplica el fallback autorizado: bloqueo de ejecución real y ensayos
solo mediante objetos falsos. No se modificó infraestructura para eludir el bloqueo.

## Preparación independiente propuesta

Una futura autorización deberá delimitar explícitamente conexión, preparación y
APPLY, con destino local exacto 127.0.0.1:27018 y replica set app_finanzas_dev_rs.
Antes de cualquier escritura se deberá comprobar PRIMARY, versión compatible,
identidad física/contexto esperados y ausencia de test_c3_apply_<nonce> recién
generada. Si existe, detenerse; no reutilizar una base financiera o experimental.

Solo se prepararían transactions, history_apply_synthetic_journal y
moneyflow_metadata, con sus registros R6 y marca sintética. No crear índices
explícitos: únicamente los índices _id_ automáticos de colecciones nuevas.
La creación/autorización de esas colecciones administrativas necesita permiso
separado; el runner actual no ejecuta ninguna de ellas.

Los UUID físicos se obtendrían del servidor DESPUÉS de crear esas nuevas colecciones,
y se entregarían junto a R6/nonce a una aprobación independiente. No usar UUIDs
generados offline como UUID físicos de una colección real. new_preparation genera
solo identidades de fixtures; OfflineCatalog comprueba ausencia en un catálogo
falso, no en MongoDB. Ninguno es evidencia de aislamiento operativo.

PLAN privado: construirlo usando el lector snapshot registrado a un único T,
conservarlo en memoria del supervisor y aprobar su digest/contexto/run_id antes
 de entregar al adaptador. No exportarlo automáticamente ni reconstruirlo desde
un JSON agregado. La autorización de desarrollo, preparación sintética y APPLY
son decisiones independientes. No se introduce aquí persistencia de planes.

## Contrato de exclusión aún pendiente

El proveedor futuro debe verificar evidencia externa, vinculada a nonce, URI/base,
UUID de movimientos y bitácora, R6, usuario efectivo, run_id/digest, revisión,
versión/generación, scope, época y vencimiento de la ventana.

Necesita acreditar custodia de la base nueva, lista de procesos/clientes autorizados,
control de acceso al destino, escritores externos y DDL impedidos/controlados,
operaciones en vuelo conocidas y finalizadas, metadata estable y unicidad del
ámbito vigente. Su autoridad y mecanismo deben revisarse ANTES de implementar una
ruta MongoDB. No aceptar solo un booleano, una firma sobre una declaración sin
fundamento o una prueba de que no se observaron cambios. Una aplicación que no
conoce el nombre aleatorio de la base reduce riesgo accidental, pero no demuestra
exclusión de operadores administrativos.

Si la infraestructura no puede aportar esta evidencia, APPLY sigue prohibido.
Las pruebas de interferencia tendrán actores artificiales identificados, ventanas
marcadas como inyección y expectativa de conflicto/bloqueo. No presentar esas
ventanas como prueba de exclusión continua real ni su éxito como permiso financiero.

## Modelo y pruebas disponibles

El archivo autorizado contiene modelos de Preparation y FixtureApproval, catálogo
falso, creación de cliente falso y PLAN mediante Reader BSON de tests. Los UUID de
fixtures y el timestamp son sintéticos. _FixtureVerifier verifica únicamente
writers/DDL/inflight y pins de ese OfflineCatalog exacto, con IDs lógicos acotados
por presupuestos del PLAN. No se puede usar como proveedor operativo.

run_fixture rechaza clientes ajenos a su clase de fixtures. FixtureApproval es
inmutable y vincula pins/digest/run_id, con mode=offline_fixture_only. No se genera
una aprobación automáticamente al crear identidades o construir PLAN. Las pruebas
la suministran explícitamente, como oráculo falso, NO como autenticación humana.

Se ensayan missing→ready, null, CAS fallido, fallo de recibo con rollback falso,
reintento transitorio, confirmación perdida y conciliación del recibo original,
propietario ajeno, contexto incorrecto, límites, colección vacía, limpieza,
protección de pins y rechazo de escritores/DDL/inflight desconocidos. Los ensayos
de falsos completan las 40 pruebas del modelo y 32 del adaptador sin alterarlos.

Cada fixture compara BSON de campos financieros antes/después, audita vocabulario
de comandos y namespaces, sesión común para movimiento/recibo mediante los tests
del adaptador y verifica cierre de recursos. Solo se devuelve estado/conteos/métricas
agregadas; no documentos, IDs individuales, fechas financieras, importes, UUIDs,
URI o secretos. Los reports conservan flags offline y real_writer_exclusion_demonstrated
es siempre false. Las inyecciones se identifican explícitamente.

Los límites del modelo/adaptador siguen siendo una intención por transacción,
5 segundos por transacción, 30 segundos globales y presupuestos BSON existentes.
No hay medición de rendimiento real ni garantía de RSS/retención MongoDB. Un cliente
real futuro necesitará timeouts de conexión/selección acotados además de CSOT.

Ejecutar exclusivamente offline:

```bash
python3 -B -m unittest backend.tests.history_apply_synthetic_runner -q
# Alternativa explícita; nunca conecta:
python3 -B -m backend.tests.history_apply_synthetic_runner --offline-tests
```

## Escenarios MongoDB futuros, no ejecutables todavía

1. Preparar una base NUEVA aprobada y obtener pins independientemente.
2. Verificar exclusión externa mediante proveedor aprobado; abortar si falta.
3. Aplicar missing→ready con tipos BSON mixtos y comparar fuentes exactas.
4. Rechazar null/bloques existentes, fuentes distintas y CAS sin coincidencias.
5. Ensayar fallo entre actualización y recibo para verificar rollback REAL conjunto.
6. Ensayar reintentos, commit incierto y conciliación sin otra intención o documento.
7. Verificar rechazo de otro propietario/reinicio y cambios de UUID/R6/PRIMARY.
8. Auditar comandos/sesiones, BSON antes/después, presupuestos, cierre e informes.

No hay recuperación automática, REVERT, VERIFY operativo ni activación de índices.
Conservar la futura base al finalizar. Los resultados no certificarán historial real.
El bloqueo solo puede revisarse bajo una NUEVA autorización explícita; esta entrega
no permite conexión alguna ni escrituras financieras reales.


## Perfil de laboratorio preparado offline

La preparación nueva sustituye el destino propuesto de desarrollo por un perfil
exclusivo: 127.0.0.1:27019 / moneyflow_c3_apply_test_rs /
test_c3_apply_7e62d1a31cc9, usuario MongoDB c3_apply con SCRAM-SHA-256 y usuario
financiero default-user. La excepción de nonce de 12 caracteres solo pertenece a
este perfil exacto; las simulaciones históricas conservan su contrato de 32.

lab_connection_spec valida opciones sin construir clientes. main y
request_mongodb_execution mantienen el bloqueo external_exclusion_unproven incluso
con perfil y credenciales válidos. No existe ruta de preparación o escritura real
ni aceptación de c3_admin, c3_recovery, bootstrap, otro puerto/base/replica set.

Pasos futuros sujetos a autorización independiente:

1. Corregir los permisos de lectura hacia moneyflow_metadata, sin conceder DDL
   o administración a c3_apply. Preparar con c3_admin, nunca con APPLY.
2. Acreditar ausencia de la base exacta; crear únicamente transactions,
   history_apply_synthetic_journal y moneyflow_metadata con fixtures artificiales.
3. Generar R6 sintético válido; obtener UUID físicos reales de las tres
   colecciones y aprobar los pins por un proceso independiente. No reutilizar
   UUID inventados por new_preparation ni reconstruir PLAN desde JSON público.
4. Usar LabSnapshotReader para PLAN privado a un único T; conservarlo en memoria,
   aprobar run_id/digest/alcance y revisión de código.
5. Validar un proveedor externo de exclusión continua de escritores y DDL,
   custodia administrativa, procesos autorizados y operaciones en vuelo.
6. Solo tras autorización separada de ejecución, ensayar atomicidad, CAS,
   rollback, idempotencia, commit incierto y limpieza.

No se implementa el proveedor de exclusión ni un bypass. La observación de
currentOp, un booleano de aprobación, un lease y el nombre aleatorio no prueban
exclusión continua. Administradores y propietario del host son autoridades que
deben quedar explícitamente dentro del modelo de confianza.

Presupuestos conservados: 30 s globales, 5 s por transacción, una intención por
transacción, 10.000 documentos, 1 MiB y 32 MiB según el modelo existente.
Una simulación satisfactoria no demuestra atomicidad MongoDB, certificación
financiera, cobertura histórica ni autorización para lecturas indexadas.

Pruebas offline del perfil, adaptador y bloqueo:

```bash
python3 -B -m unittest backend.tests.test_history_apply_lab backend.tests.test_history_apply_mongodb_adapter backend.tests.history_apply_synthetic_runner backend.tests.test_history_apply -q
```


## Ruta explícita de PLAN observador, validada solo offline

El siguiente paso autorizado puede usar LabObserverTarget y
build_observer_plan con c3_observer, sin credenciales administrativas ni APPLY.
No se usa lab_client_options de escritura ni se cambian identidades para
autoaprobar pins. El llamador deberá crear explícitamente el cliente con destino
127.0.0.1:27019, SCRAM-SHA-256, timeouts acotados y retries desactivados. No hay
CLI ni conexión automática, y no se ejecutó MongoDB durante esta implementación.

Los tres UUID candidatos y R6 se entregan como entradas independientes; no se
descubren para autoaprobarlos. El lector compara el catálogo y el contexto, y
construye un PLAN privado vinculado al perfil observador y al único T adquirido.
Todas las operaciones del recorrido usan una sola sesión; no hay persistencia
de PLAN, intenciones ni checkpoints. El informe mantiene read_only=true,
pins_approved=false, apply_authorized=false e indexed_reads_allowed=false.

Las pruebas falsas cubren sesión/T únicos, cuentas/roles incorrectos, pins/R6,
colección vacía, duplicados, límites, pérdida de snapshot/cursor, limpieza, errores
saneados y rechazo del PLAN por el adaptador APPLY. El bloqueo
external_exclusion_unproven continúa intacto incluso con evidencia observadora.
Ninguna prueba offline autoriza aplicar claves o certifica datos financieros.

Antes de ejecutar el PLAN real se requiere autorización de lectura separada y
revalidación de laboratorio, pins y huellas; conservar la bitácora vacía.
La continuidad de escritores, la retención de T y las garantías del driver real
no se deducen de estas simulaciones.
