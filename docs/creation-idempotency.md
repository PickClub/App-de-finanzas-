# R5 — idempotencia de creación de Presupuestos y Facturas

## Alcance original

R5 identificó la recreación de pagos anulados, la reutilización de claves con
contenido diferente al crear presupuestos/facturas y la falta de exclusión
concurrente comprobada en Presupuestos. R3 ya conserva los recibos de pagos
anulados; R5 mantiene esa protección sin modificar pagos, saldos ni R4.

## Solicitud original y recuperación

Con `Idempotency-Key`, ambos POST conservan `request_fingerprint`: SHA-256 del
`model_dump()` original, serializado con claves ordenadas y sin números no finitos.
Se calcula antes de validaciones que normalizan campos o generan fechas. Omitir
una fecha opcional conserva null en la huella; el instante generado solo se guarda
en el documento creado. Repetir la solicitud no vuelve a generar ese instante.
Omisión y null explícito de un campo con el mismo valor predeterminado del modelo
representan la misma solicitud de creación. No se normalizan representaciones
distintas de fechas para deducir intenciones iguales.

- Misma clave y huella: recuperar el documento existente, sin escrituras.
- Misma clave y otra huella: HTTP 409, sin modificar el documento.
- Registro antiguo sin huella, o varias coincidencias históricas: HTTP 409.
  No se deduce la solicitud original desde los campos actuales ni se migra nada.
- Una edición posterior conserva la huella original. La recuperación devuelve
  el documento vigente con el mismo ID; no restaura ni sobrescribe la edición.
- Sin clave se conserva la creación independiente y sus validaciones anteriores.

La huella, la clave y el `_id` MongoDB no aparecen en respuestas de creación,
recuperación, edición, listados o resúmenes afectados. No se almacenan credenciales.

## Exclusión concurrente

Los nuevos presupuestos con clave usan UUID v5 de
`default-user:budget:<clave>` como ID público y `_id` MongoDB. Facturas conserva
su namespace determinista anterior `default-user:bill:<clave>`. El índice nativo
único `_id_` de cada colección obliga a competir por el mismo documento incluso
si las solicitudes referencian categorías diferentes. No se crean índices nuevos.

Se utiliza `payment_transaction` sin modificarlo. Los conflictos transitorios y
duplicados reejecutan la operación con un snapshot actualizado: el ganador queda
almacenado y el otro intento recupera su resultado o rechaza otra huella con 409.
Las validaciones y coordinación referencial de R3 permanecen dentro de la sesión
para nuevas creaciones. Una recuperación verificada no vuelve a validar padres
ni crea relaciones; el guard de entidades gestionadas por R4 se conserva.

Un 503 de commit incierto no prueba rollback. El cliente debe conservar la misma
clave y solicitud. La recuperación tras un commit confirmado con respuesta
perdida no inserta ni genera otro documento. La modificación no introduce journal
frontend, endpoints nuevos, autenticación ni activación de R4.

## Compatibilidad y límites

Los IDs y claves históricos no se sustituyen. La consulta de claves de presupuesto
incluye documentos anteriores con IDs aleatorios y falla conservadoramente si no
puede verificar la intención. Los clientes que no envían clave no obtienen la
garantía de recuperación; se mantiene su contrato anterior.

La protección cubre documentos conservados. No añade retención de intenciones
de creación después de eliminar definitivamente un presupuesto o factura; ese
cambio de política no forma parte de esta corrección. Los recibos financieros
anulados siguen conservándose conforme a R3/R6. No se permite usar una clave nueva
para ocultar un resultado incierto. Un despliegue mixto con escritores anteriores
de Presupuestos no tiene esta garantía completa: todos los procesos escritores
deben ejecutar la corrección antes de considerarla disponible.

No se examinan ni reparan duplicados de bases existentes. La búsqueda histórica
por clave puede requerir una futura evaluación de rendimiento; R5 no provisiona
índices en bases persistentes. `default-user` es la identidad efectiva single_user,
no autenticación. R4 permanece desactivado y Emergent no se configura.

## Pruebas aisladas

```bash
python3 -B -m unittest backend.tests.test_creation_idempotency
MONEYFLOW_R5_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_creation_idempotency_mongodb
```

La suite MongoDB crea una base `test_r5_creation_<UUID>` nueva por caso y verifica
127.0.0.1:27018, replica set, PRIMARY, sesiones y base vacía antes de escribir.
El auditor admite solo esa base y admin; prohíbe crear índices y borrar bases,
colecciones o índices. Las bases nuevas se conservan. No carga `.env`, importa
el servidor completo, ejecuta startup ni utiliza `/api/seed`.

Las pruebas comprueban documentos, saldos y ausencia de movimientos adicionales,
no solo códigos HTTP. Cubren payload exacto/diferente, categorías, todos los campos,
fechas predeterminadas, ediciones, historial sin huella, claves históricas ambiguas,
recuperación sin nuevas validaciones referenciales, serialización pública,
concurrencia real, rollback posterior a la inserción y commit con respuesta perdida.
