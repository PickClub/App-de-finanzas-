# R3 — Integridad referencial

## Garantías y alcance

Las rutas que crean o cambian referencias validan los padres y participan en una
transacción MongoDB. Los padres que anteriormente solo se leían reciben un
incremento efectivo de `_reference_revision`. La eliminación de ese documento
entra en conflicto con la creación del enlace; el manejador existente reintenta
la transacción completa y vuelve a validar. Una consulta previa por sí sola no
protege contra inserciones concurrentes bajo aislamiento snapshot.

Los movimientos ordinarios y pagos de deudas ya escriben cuentas y deudas en sus
recálculos: se aprovecha esa coordinación y no se añade un bloqueo redundante.
Las categorías de movimientos sí necesitan el incremento. Se conserva
`_payment_revision` de R2 para serializar pagos y ediciones de facturas.

No se han modificado los manejadores transaccionales compartidos, las fórmulas de
saldos ni el registro financiero de pagos de deudas. No existe una alternativa de
escrituras parciales cuando MongoDB no admite transacciones. Las creaciones de
configuraciones con referencias (facturas, deudas, plantillas, presupuestos,
metas y categorías con padres) también requieren ahora transacciones. Un MongoDB
standalone no satisface este requisito; debe utilizarse un replica set o un
cluster compatible, igual que para las operaciones financieras existentes.

`_reference_revision` no se devuelve en respuestas públicas, incluidas lecturas,
ediciones y respuestas recuperadas por idempotencia. No se provisionan metadatos
de R6, se cambian identificadores de entorno ni se realizan migraciones.

## Rechazos y conservación de datos

- DELETE de cuentas: HTTP 409 si hay movimientos, transferencias, deudas, pagos
  activos, facturas, recurrencias, registros recurrentes, metas, aportes activos
  o plantillas que las referencian.
- DELETE de categorías: HTTP 409 si existen movimientos, presupuestos, deudas,
  facturas, recurrencias, registros recurrentes activos, plantillas o
  subcategorías que deben conservar la referencia.
- Una referencia nueva inexistente o perteneciente a otro usuario devuelve
  HTTP 422, conservando los códigos de las validaciones anteriores cuando ya
  existían. Una referencia heredada inexistente puede conservarse al editar
  otros campos; no se corrige automáticamente. Las referencias opcionales
  omitidas se conservan literalmente en facturas, recurrencias y metas: incluido
  `""`, null y la ausencia de una clave histórica. Un null enviado explícitamente
  conserva la semántica de eliminación ya permitida por cada contrato. Enviar
  el mismo valor heredado tampoco provoca su normalización automática.
- Anulación o desvinculación con vínculos incoherentes: HTTP 409, sin cambios.
  Se verifican los dos sentidos del enlace, el movimiento, importe, cuenta y
  `bill_id`, también desde las rutas recurrentes cuando el registro es compartido
  con un pago de factura. Los importes numéricos equivalentes (entero, float,
  cadena decimal o Decimal128) se comparan por su valor decimal finito exacto,
  sin redondear ni introducir tolerancias que oculten una discrepancia. Los
  identificadores permanecen exactos: no se adivinan vínculos por el importe.
  En los campos opcionales del registro recurrente, `""`, null o una clave ausente
  representan la misma ausencia de referencia según su creación existente. Esa
  equivalencia se usa únicamente para verificar el vínculo; no se reescriben los
  valores almacenados. La cuenta del pago de factura y los identificadores
  efectivos del pago, movimiento y factura continúan comparándose exactamente.
- Anular un pago usado como movimiento de origen de una plantilla: HTTP 409.
- PUT y DELETE de movimientos consultan también referencias inversas activas
  por `transaction_id` en pagos de facturas, registros recurrentes, aportes y
  pagos de deudas, dentro de la misma transacción. Una referencia activa impide
  tratar el movimiento como ordinario aunque haya perdido su identificador
  inverso: HTTP 409 sin cambios persistentes. La ruta específica de un pago de
  deuda conserva su vínculo válido y rechaza referencias activas adicionales.
  Los recibos históricos con `deleted: true` no bloquean movimientos ordinarios
  legítimos ni se eliminan o reparan automáticamente.
- DELETE de metas verifica importe decimal exacto, identificadores, vínculos
  inversos y dirección de cada transferencia. La cuenta del aporte debe ser
  el origen en un depósito y el destino en un retiro. No se compara con la
  cuenta actual de la meta, que puede haber cambiado después del aporte.
  Una discrepancia devuelve HTTP 409 y revierte cualquier coordinación interna;
  no altera aportes, transferencias, saldos ni enlaces. Las transferencias
  legítimas se conservan al eliminar la meta, igual que antes.
- Reintentar con la clave de un pago o registro anulado: HTTP 409. Nunca se
  recrea ni se interpreta como un pago nuevo. Los fingerprints se conservan.
- Conflictos agotados o resultados de commit inciertos mantienen el tratamiento
  de R1/R2/R6: no se informa éxito ni se repite una creación indiscriminadamente.

Eliminar una factura conserva sus gastos y el saldo, retira los pagos del
seguimiento activo y desvincula los registros recurrentes del pago de factura.
Eliminar una recurrencia conserva gastos y pagos de factura, elimina sus enlaces
recurrentes y limpia los enlaces inversos de facturas y pagos. Eliminar un
registro compartido con una factura desvincula el seguimiento recurrente sin
anular el gasto de la factura.

Los pagos, registros recurrentes y aportes retirados permanecen como documentos
históricos con `deleted: true`; no cuentan como referencias activas ni en
totales, calendarios o historiales activos. No se borran en cascada gastos ni
transferencias. La anulación explícita de un pago o de un registro que creó un
gasto conserva su comportamiento anterior de retirar ese movimiento y recalcular
el saldo, después de verificar sus enlaces.

`series_id` es una identidad de agrupación: no requiere que exista la factura
original. El siguiente período real se conserva al eliminar el anterior. Al
crear un período nuevo se verifican sus referencias: una configuración heredada
inexistente no se copia a un nuevo documento; se rechaza y revierte la operación
completa. La configuración debe revisarse antes de volver a intentarlo.

Un pago de una factura `once`, o un pago parcial que no cree otro período, no se
bloquea por una referencia heredada inexistente a una recurrencia que no se vaya
a utilizar ni copiar. No se repara ese campo ni se crea un registro recurrente.
La factura sigue coordinada por R2 y el movimiento conserva las validaciones de
sus referencias efectivas. Una recurrencia existente utilizada como padre de un
registro compartido se coordina dentro de la misma transacción. La validación
estricta al crear un período nuevo continúa vigente y hace rollback completo.

## Pruebas y aislamiento

Las pruebas cargan por AST las rutas reales, sin importar el arranque de FastAPI,
dotenv ni clientes de producción. Las pruebas en memoria cubren regresiones,
referencias heredadas, null, enlaces inversos, anulaciones y serialización.

```bash
python3 -B -m unittest discover -s backend/tests -p 'test_*.py'
MONEYFLOW_R3_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_reference_mongodb
MONEYFLOW_R1_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_ordinary_mongodb
MONEYFLOW_R2_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_bill_mongodb
```

Cada prueba real R3 genera una base `test_r3_validation_<uuid>` nueva y verifica
loopback `127.0.0.1:27018`, replica set, PRIMARY, sesiones y ausencia de
colecciones antes de escribir. El registro de comandos comprueba que solo se
utiliza esa base y admin. Las bases R3 se conservan; no se consultan ni limpian
bases anteriores, desarrollo, Samsung ni Emergent. R1 limpia exclusivamente sus
bases nuevas, verificando su nombre y conexión.

Los escenarios reales incluyen carreras de creación/eliminación en ambos
órdenes; expense/mark/link; cuentas, categorías, facturas, deudas, plantillas,
metas y presupuestos; conflictos MongoDB comprobados; desvinculación concurrente;
rollback; respuesta perdida; commit incierto; claves iguales y distintas;
períodos mensuales y vínculos recurrentes. El caso de dos pagos legítimos de
100 y 150 mantiene cuenta 750, deuda 250 y exactamente dos pagos.

Las regresiones de la revisión final cubren pagos con referencias heredadas no
utilizadas; rechazo al copiarlas a un período nuevo; discrepancias en importe,
cuenta y factura sin ninguna modificación; representaciones numéricas equivalentes;
y conservación literal de referencias omitidas o explícitas en facturas,
recurrencias y metas. Los casos fueron reproducidos antes de corregirse y se
ejecutan tanto en memoria como en bases MongoDB nuevas y aisladas.

Se añaden ocho regresiones permanentes para PUT/DELETE con vínculos inversos
incompletos de facturas, recurrencias y metas, y para las dos discrepancias de
cuenta/dirección de aportes. Comprueban HTTP 409 y la igualdad de todas las
colecciones antes y después del rechazo, no solo el código HTTP. También cubren
recibos inactivos, referencias de deuda, transferencias históricas después de
cambiar la cuenta de una meta, importes e identificadores incoherentes y enlaces
inversos adicionales. Las carreras reales de vinculación recurrente contra
PUT/DELETE ordinarios fuerzan ambos órdenes: se verifica el WriteConflict,
la relectura y el estado financiero final sin referencias huérfanas. No se
modifican los manejadores transaccionales para estas comprobaciones.

El archivo histórico `test_moneyflow_api.py` requiere un servidor externo e
incluye seed y escrituras: no debe ejecutarse contra entornos existentes para
validar R3. Las pruebas de seguridad de seed únicamente verifican su rechazo en
memoria, con un doble que prohíbe cualquier acceso a MongoDB.

## Limitaciones

R3 no repara automáticamente corrupción previa ni puede impedir escrituras
directas ajenas a estas rutas. Las operaciones rechazadas por enlaces incoherentes
requieren una conciliación autorizada. La coordinación puede aumentar los
conflictos al editar referencias sobre padres compartidos; los rechazos seguros
no equivalen a pagos confirmados. No se ha activado ni modificado Emergent.
