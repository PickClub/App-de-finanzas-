# C3 — Claves privadas en el núcleo preparado R4

## Integración limitada

`register_shared_payment` recibe el parámetro interno opcional
`history_settings=None`. Si no se proporciona o el control está desactivado,
conserva el comportamiento anterior. `dispatch_shared_payment` reenvía la
configuración que ya recibió; no carga configuración ni activa controles.

Cuando `history_keys_write_enabled` está habilitado en pruebas y tiene una
generación válida, el núcleo llama al módulo compartido `with_history_keys`
después de construir el documento final del movimiento. Ese documento y sus
claves se escriben en el mismo `transactions.insert_one(..., session=session)`.
La cápsula original, payload, fecha, importe, IDs, fingerprint y recibos no
cambian. Los recibos complementarios y journals no reciben `_history_keys`.
No hay escrituras adicionales ni transacciones anidadas.

`change_shared_payment` y `register_shared_tracking` permanecen sin cambios.
Anular elimina el movimiento con sus claves y devuelve dinero una vez.
Retirar/restaurar seguimiento cambia solo enlaces y conserva claves y fuentes.
`mark` no crea movimientos ni claves. El saneamiento recursivo público existente
sigue ocultando `_history*`. No se activa R4 ni escritura/lectura indexada.

## Verificación

12 pruebas nuevas en memoria aprobadas: ambos orígenes de pago, claves en el
movimiento y no recibos, control desactivado o no suministrado, repetición y
conflicto de payload, pagos parciales independientes iguales, misma intención
concurrente, sobrepago rechazado sin escrituras, anulación/devolución única,
retirada/restauración y reintento administrativo, mark seguido de pago real,
rollback después de todas las inserciones, confirmación incierta y recuperación,
unverifiable y saneamiento público. El adaptador público también comprueba
propagación del control y bloqueo cuando R4 queda desactivado.

Los índices y la topología usados en memoria son dobles sintéticos; no demuestran
unicidad ni conflictos MongoDB reales. Se corrigieron dos errores de preparación
de estas pruebas (duplicación de campos de configuración e importe administrativo
de link distinto al movimiento original), sin modificar reglas financieras.
La confirmación incierta es una inyección del doble en memoria, no una prueba
nueva contra el servidor MongoDB.

## MongoDB: validación completada en entorno sintético

El servicio MongoDB local fue recuperado y se verificó PRIMARY del replica set
`app_finanzas_dev_rs`, sesiones y soporte transaccional en `127.0.0.1:27018`.
La corrección local del healthcheck no forma parte de este bloque ni de sus
archivos; no se modifica Compose para esta integración.

Con autorización específica se amplió el arnés para ejecutar las operaciones
financieras en una base sintética nueva, previa verificación de su inexistencia.
La ejecución final aprobó **15/15 escenarios MongoDB** en:
`test_c3_shared_keys_294a52c683e446d08a01548d6ee0cc70`.
La base se conserva; no se consultaron ni modificaron bases anteriores.

Se crearon exclusivamente dos definiciones de índices únicos R4:

- `shared_period_unique`: `(user_id, recurring_id, original_due_date)`.
- `shared_bill_unique`: `(user_id, bill_id)`.

Hubo 28 instancias de esos índices: dos por cada escenario positivo, en
colecciones aisladas dentro de la base nueva. El escenario negativo quedó sin
ellos y verificó rechazo 503 sin escrituras. Los índices `_id_` de colecciones y
del journal administrativo son automáticos; no se crearon otros índices explícitos.
La auditoría de comandos verificó que los accesos de datos e índices quedaron
limitados a la base sintética autorizada, sin drop, migraciones ni seeds.

La primera ejecución de esta validación falló en el adaptador público porque
el envoltorio de pruebas interpretaba `database.client` como una colección.
Se añadió únicamente esa propiedad al envoltorio, sin modificar código
funcional. Su base también se conserva:
`test_c3_shared_keys_ccd4d988450241f98fdebcb38f8c776b`.
Después se repitió la suite en la nueva base final; no se reutilizó la primera.

La ejecución final cubrió inserción conjunta de movimiento y claves desde
Facturas y Recurrencias, ausencia de claves en recibos/journals, control
habilitado/deshabilitado, idempotencia y payload incompatible, pagos parciales
independientes, concurrencia real con relectura, rollback, anulación y devolución
única, retirada y restauración administrativa sin otro movimiento, mark sin
dinero, saneamiento público y bloqueo al desactivar R4. También comprobó rollback
tras escribir el journal de restauración y conservación de su intención original.

La pérdida de confirmación se inyectó en el cliente después de un **commit
real**, tanto en creación como en anulación. Los reintentos recuperaron el
resultado original sin duplicar movimientos ni devoluciones. No se simuló
una caída física de red ni un failpoint del servidor.

## Pendientes y límites

Estas pruebas no activan R4 en la aplicación. R4, escritura de claves por defecto
y lecturas indexadas permanecen desactivados. Una futura activación exige el
contexto R6, PRIMARY y transacciones, los índices íntegros R4 y el journal
administrativo, además de las verificaciones de historial y capacidades ya
establecidas. Los índices de esta validación no provisionan bases habituales.

La prueba unverifiable inyecta solo una incapacidad del parser derivado; las
validaciones financieras de fechas permanecen intactas. No se migra o repara
historial. No se garantiza cobertura de movimientos históricos ni se activa la
lectura indexada. No hubo prueba física Samsung.
