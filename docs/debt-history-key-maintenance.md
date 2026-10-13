# C3 — Claves en movimientos vinculados a pagos de deudas

Alcance: create_debt_payment (POST /api/debt-payments) y edit_payment_movement
(rama vinculada del PUT /api/transactions/{tid}). Solo se agregan metadatos al
movimiento financiero. El control existente MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED
permanece desactivado por defecto y reutiliza la generación explícita configurada.
No se modificó config.py ni se activó ningún archivo .env.

## Atomicidad y documentos originales

La creación mantiene el cálculo previo de pid/tid deterministas y fingerprint del
payload original, incluyendo date:null. La fecha efectiva se fija después, como
antes. Al insertar el movimiento definitivo se utiliza with_history_keys sobre
una copia; el mismo insert_one y session contienen movimiento y claves.
El recibo DebtPayment mantiene campos, ID, request_fingerprint y respuesta originales.
No recibe _history_keys ni se altera para provisionar metadatos.

En edición se lee el movimiento con INTERNAL_PROJ dentro de payment_transaction.
Las validaciones y transaction_edit_payload originales siguen precediendo la
derivación. Se combina old+payload después de fijar debt_id/date efectivos y se
añade history_update_fields al mismo $set del movimiento. El payload utilizado
para editar los cuatro campos permitidos del recibo NO incluye claves derivadas.
Se mantienen recompute_debt, recompute_account_balance y sus sesiones originales.

No hay transacciones anidadas, actualización posterior independiente ni cambios
en manejadores compartidos. Solo creación y edición del movimiento están
instrumentadas; payment_movement/remove_payment permanecen idénticos. DELETE
/api/debt-payments/{pid} y la rama de DELETE /api/transactions/{tid} eliminan las
claves con el documento, sin una escritura adicional. Continúa la protección R3
para movimientos utilizados como origen de plantillas.

Un cambio administrativo de nombre/notas/cuenta conserva las claves si las fuentes
fecha/importe/identidad no cambian. No se añade backfill al editar notas de un
movimiento heredado sin claves. Una edición explícita de fuentes puede generar
claves del nuevo estado. Fechas heredadas inválidas aceptadas por la validación
existente producen unverifiable sin nuevas prohibiciones financieras.

## Idempotencia, incertidumbre y eliminación

La misma clave y payload original recuperan el pago existente sin insertar movimiento
ni recalcular fechas/claves. Payload distinto produce el 409 existente. La huella
de intención NO se sustituye por la huella de fuentes de _history_keys.
Editar el pago mantiene su fingerprint de creación; el reintento de la intención
original continúa siguiendo el contrato existente, sin duplicar ni restablecer valores.

El tombstone del pago con fingerprint se conserva; un reintento tardío tras
anulación devuelve 409 y no recrea dinero. Pagos anteriores sin fingerprint
conservan su comportamiento de eliminación, sin migración ni reparación.
Una respuesta incierta continúa siendo 503, no prueba de rollback. Se reutiliza
la intención original. Los journals R4/R6 y sus contratos no se modificaron.

No se instrumentaron facturas, metas, recurrencias ni escritores R4. Los tipos
loan_given/loan_received continúan fuera del bloque ordinario anterior.
Las protecciones de saneamiento público existentes siguen ocultando _history*.

## Pruebas ejecutadas

15 pruebas nuevas en memoria: pago de deuda y cobro they_owe, claves ready,
edición fecha/importe, campos administrativos y omitted/null, idempotencia y
payload diferente, dos intenciones legítimas, misma intención concurrente,
unverifiable, control apagado/historial sin claves, rollback de creación/edición/
eliminación, tombstones/reintentos tardíos, protección de plantillas R3, PUT
repetido, commit incierto y reintento transitorio.

El driver de memoria no implementa reintentos automáticamente; una prueba suministra
ese comportamiento en su sesión sintética, manteniendo el manejador productivo intacto.
No considerar ese test evidencia de conflictos MongoDB reales.

17/17 pruebas MongoDB reales en la única base nueva de esta etapa:
`test_c3_debt_keys_57d600f91dff43969a2d21e4598e91e1`.
Se conserva, sin limpieza. Destino:
`mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true`.

Antes de crearla: URI estática, nombre nuevo, dirección efectiva, replica set,
PRIMARY, sesiones/protocolo y ausencia exacta comprobados. Colecciones por escenario
dentro de esa base. El auditor no registró otros destinos ni drop/createIndexes.
Los únicos índices son los _id que MongoDB crea normalmente para las colecciones
sintéticas. No se consultaron bases anteriores ni se provisionó identidad financiera.

Además de los casos comunes, MongoDB ejecutó conflictos reales entre ediciones,
anulaciones concurrentes y pérdida de confirmación de creación/eliminación. Se
observaron 1 y 3 intentos al editar: el driver relee el movimiento actualizado y
se verifican claves, importe/fecha del recibo, deuda y saldo finales.
La pérdida de confirmación se inyectó en el cliente DESPUÉS de un commit real;
no se apagó MongoDB ni se utilizaron failpoints o cambios de red.

Los casos de rollback comparan todos los documentos sintéticos antes/después;
no verifican únicamente HTTP. Se preservan fingerprints y se comprueba ausencia
de metadatos tanto en respuestas como en recibos almacenados.

Regresión completa ejecutada: 422 tests backend en memoria, 419 aprobados y
3 fallos históricos esperados C3/R9; 77 experimentales offline, 74 aprobados y
3 fallos esperados del parser P2. Los 13 scripts frontend, TypeScript y
git diff --check aprobaron. Ninguna regresión nueva. No se ejecutaron las suites
externas contra servidores configurados ni suites MongoDB anteriores con limpieza.

Comando memoria: `python3 -B -m unittest backend.tests.test_debt_history_keys`.
MongoDB opt-in: `MONEYFLOW_C3_DEBT_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_debt_history_keys_mongodb`.
Una ejecución futura crearía otra base nueva y requiere autorización posterior.
Nunca reutilizar o eliminar automáticamente esta base o las anteriores.

## Limitaciones

No hay cobertura total del historial: faltan otros escritores y un procedimiento
separado para datos históricos. Desactivar el control puede dejar claves obsoletas;
las lecturas optimizadas permanecen sin habilitarse. No se crea un nuevo sistema
de autenticación: default-user sigue siendo identidad efectiva single_user.
No se midió rendimiento masivo ni se probó recuperación física Samsung en esta etapa.
