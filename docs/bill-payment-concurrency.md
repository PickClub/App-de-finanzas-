# R2: sobrepagos concurrentes de facturas

Los pagos parciales de una factura compartían lecturas de `bill_payments`, pero
podían escribir movimientos y cuentas diferentes sin modificar la factura.
Dos snapshots podían validar $70 cada uno sobre $100 y confirmar $140. Una
reducción concurrente de $100 a $50 también podía confirmar junto con un pago
de $70. Las transacciones preservaban cada operación, pero no esta regla conjunta.

`pay_bill` y `update_bill` ahora coordinan sus transacciones mediante una escritura
efectiva sobre el mismo documento de factura, antes de consultar el total pagado.
`_bill_for_write` incrementa `_payment_revision` con `find_one_and_update` dentro
de la sesión. Un conflicto hace que el manejador existente vuelva a validar el
pendiente en otra transacción. No se usan bloqueos de interfaz ni de un solo proceso.

La revisión se inicializa al incrementar un documento que no la tiene. No hay
migración masiva ni reparación automática de sobrepagos antiguos. El incremento
tiene rollback junto con las demás escrituras; no modifica el importe ni la fecha
de la factura. Se oculta en detalle, listado, edición y recuperación idempotente de
creación; no forma parte del contrato público.

La consulta idempotente del pago sigue precediendo a la coordinación: misma clave
y payload recuperan el pago, sin otra revisión ni movimiento. Payload diferente
con la misma clave conserva HTTP 409. Se mantienen el manejador transaccional,
los movimientos, recálculos de cuentas, vínculos recurrentes y generación única
del siguiente período dentro de la transacción, sin alternativa de escrituras parciales.

## Pruebas aisladas

```bash
python3 -B -m unittest backend.tests.test_bill_validation
MONEYFLOW_R2_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_bill_mongodb
```

La suite en memoria comprueba validación, idempotencia, commit incierto, ausencia
del campo interno y rollback en cada escritura. La suite real verifica el destino
loopback y replica set antes de escribir, crea exclusivamente una base nueva
`test_r2_validation_<uuid>` y usa datos sintéticos. No importa el servidor completo,
no carga `.env`, no ejecuta seed y no accede ni limpia bases existentes. Conserva
su propia base de pruebas; su limpieza se gestiona por separado.

Las solicitudes se sincronizan antes de adquirir la coordinación, no después:
esperar a dos solicitudes mientras una ya tiene el bloqueo impediría avanzar.
Se comprueban cuentas iguales/distintas, parciales, igualdad exacta, sobrepago,
claves iguales/distintas, ambos órdenes de una edición, vínculos recurrentes,
facturas mensuales, fallos intermedios, conflictos transitorios y commit incierto.

## Pendiente separado: recuperación de pagos de facturas

La pantalla de facturas conserva su clave solo durante el montaje y reconstruye
la fecha del pago de hoy al reintentar. Tras perder una respuesta, eso puede
provocar HTTP 409 por payload diferente. Tras desmontar puede crear otra clave;
si queda pendiente suficiente, el backend no puede distinguir ese duplicado de
un segundo pago legítimo. R2 impide superar el importe, pero no resuelve esa
recuperación de intención. Requiere análisis y autorización propios; no se cambia
el frontend ni se modifica R6 de pagos de deudas.

No se cambia la configuración de Emergent. La solución conserva el requisito de
transacciones MongoDB existente y añade contención solo entre pagos/ediciones de
la misma factura. Los clientes pueden recibir un rechazo al revalidar después de
un conflicto; las claves y payload originales deben conservarse al reintentar.
