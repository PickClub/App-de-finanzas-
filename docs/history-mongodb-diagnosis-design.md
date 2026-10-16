# C3 — Preparación de diagnóstico MongoDB, sin conexión

Etapa de investigación y algoritmos OFFLINE. Se conserva el prototipo anterior y
el contrato administrativo. No contiene adaptador MongoDB, conexiones, escrituras,
apply/revert, registros persistentes ni activaciones. No modifica producción.

## Evidencia documental y problema confirmado de diseño

MongoDB ordena tipos BSON globalmente, pero sus predicados de consulta comparan
normalmente dentro del tipo del operando; los números se consideran equivalentes
para comparación. Por ello `_id > checkpoint` por sí solo no representa todos
los sucesores de un cursor ordenado de tipos mixtos. Un checkpoint numérico puede
excluir strings/Binary/ObjectId posteriores. La documentación también fija orden
Binary por longitud, subtipo y bytes, y comparación simple de strings.
[Referencia oficial](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/).

Las pruebas nuevas reproducen esa diferencia mediante un modelo explícito de
esas reglas, **no mediante una consulta MongoDB real**. No se atribuye equivalencia
operativa a un comparador Python sin probarlo posteriormente contra el servidor.

## Recorrido recomendado: particiones tipadas

1. Autorizar ámbito completo del usuario efectivo y validar destino/R6/UUID.
2. Hacer inventario read-only por tipo de `_id` mediante `$type` de agregación.
   Los grupos tienen cardinalidad pequeña; no devolver IDs/documentos fuente.
3. Si existe un tipo no admitido, bloquear cobertura; no excluirlo silenciosamente.
4. Recorrer en este orden cuatro particiones: int32/Int64, string, Binary, ObjectId.
5. En cada partición filtrar por usuario y `$type`, ordenar `_id:1` con colación
   simple y continuar con `$gt` **solo dentro de esa partición**.
6. Cambiar a la siguiente partición solo tras constatar agotamiento de la anterior.
   Particiones vacías también deben constatarse; un checkpoint no autoriza saltarlas.
7. Validar orden/progreso/tipo del lote recibido y volver a verificar destino.

Los constructores de filtros/pipelines del archivo experimental generan objetos,
no ejecutan comandos. `$type` de consulta admite varios tipos según la
[documentación oficial](https://www.mongodb.com/docs/manual/reference/operator/query/type/).
Para el inventario y validación de IDs lógicos se propone `$type` de expresión:
comprobar un escalar exacto, evitando el comportamiento de consulta sobre elementos
de arrays. Ningún array físico se acepta en este subconjunto.

No se incorporan por analogía double, Decimal128, null, bool, Date, documentos,
MinKey/MaxKey u otros tipos como `_id`. Si aparecen en la futura base sintética,
se necesitará ampliar contrato y equivalencia explícitamente antes de continuar.
Los importes Decimal128 financieros siguen admitidos por las claves canónicas;
esta restricción corresponde exclusivamente a la identidad física del recorrido.

Mantener el original BSON del checkpoint, incluidos Int64 y subtipos Binary.
No usar la codificación binaria BSON completa como clave de orden ni convertir
Int64 a JSON Number. Binary subtipo 0 puede decodificarse como bytes en el driver:
restaurar solo su envoltorio tipado, con codificación BSON idéntica.

## Checkpoints protegidos y reanudación

Propuesta: BSON firmado con HMAC-SHA256 y separación de dominio, sin claves
secretas dentro del token. Vincular run_id, URI/destino previamente aprobado,
base/colección/UUID físico, environment_id R6, usuario, scope, revisión de código,
versión/generación, partición, último `_id`, conteos/progreso y secuencia.
El algoritmo experimental enlaza esos valores mediante `Authorization.binding()`.

Usar clave aleatoria protegida por proveedor de secretos en una futura herramienta;
la clave fija de pruebas está marcada como fixture sintético y no es una credencial.
Comparar MAC en tiempo constante, validar esquema/tamaño y revalidar la autorización
actual además de la firma. Una firma válida no compensa un destino sustituido.
HMAC no cifra: tokens con IDs siguen siendo privados y quedan fuera de Git/logs.

Además mantener la última secuencia/digest aceptable por ejecución: rechazar un
token anterior aunque su firma sea válida. El modelo usa un registro **volátil**,
no una bitácora persistente. Tras perderlo por reinicio, bloquear reanudación y
recomenzar diagnóstico completo con nueva ejecución aprobada; conservar la clave
por sí sola no acredita el avance más reciente.

Límites del oráculo: token máximo 8 KiB; contador de avance BSON int32. Datos más
grandes bloquean, no se truncan. La autoridad solo debe emitir tokens después de
validar el lote efectivamente leído y su agotamiento; las funciones puras no
prueban que el emisor haya leído esos documentos. En producción, quien posea la
clave puede falsificar avance: acceso administrativo y control del emisor son
precondiciones, no propiedades garantizadas por HMAC.

Un checkpoint firmado tampoco demuestra cobertura de una vista viva. No consumir
un checkpoint sin firma como fallback ni resetear automáticamente la partición
ante corrupción. Token inválido: detener, conservar evidencia y solicitar/reiniciar
un diagnóstico completo autorizado, sin presentar un informe parcial como total.

## Duplicados escalables: segundo recorrido de lectura

Separar diagnóstico físico y detección de duplicados. Para esta última proponer:

- `$match` de usuario efectivo e `id` escalar string exacto.
- Proyección limitada a user_id, id y `_id` para desempate.
- `$sort` por `id:1,_id:1`, colación simple.
- Consumir el cursor como stream, reteniendo únicamente el ID anterior (máximo
  256 caracteres), tamaño del grupo y contadores agregados.

Comparación adyacente literal, sin hashes de todo el historial ni deduplicación
por fecha/importe. Contar grupos duplicados y documentos adicionales, sin emitir
IDs. Las identidades inválidas se cuentan/bloquean en el recorrido físico; no
certificar solo el stream filtrado de IDs válidos.

El algoritmo se probó con un generador de 100.001 filas, sin una lista/set global.
Eso demuestra el estado constante del consumidor, no el tiempo o memoria de
MongoDB. La fuente futura todavía debe ordenar el conjunto completo.

Un índice ya existente compatible `(user_id,id,_id)` y colación simple podría
ayudar; no se presupone que exista ni que el optimizador lo utilice. No crear
índices ni ejecutar explain en esta etapa. Medir planes/coste en prueba futura
separadamente autorizada. Mantener `allowDiskUse:false` explícito: falta de memoria,
plazo o error bloquea el resultado. No activar spill automático del servidor.

Alternativa: `$group` por identidad con conteos y resumen final; también requiere
estado servidor proporcional a identidades. El stage es bloqueante y puede agotar
memoria o usar archivos temporales. No equivale a memoria global constante.
[Referencia de `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
Para historiales que no puedan ordenarse sin spill, decidir explícitamente entre
índice autorizado o ordenamiento externo protegido y acotado; ninguno se implementa.

No intentar reanudar parcialmente el paso de duplicados tras perder un cursor
sin preservar/verificar grupo y scope: la propuesta conservadora reinicia ese
paso entero. No escribir resultados en MongoDB ni usar `$out`/`$merge`.

## Lotes, buffers y presupuesto

- Limitar documentos por petición, documentos procesados y bytes BSON por lote.
- Proyectar solamente fuentes necesarias y bloque privado para diagnóstico.
  Preservar campos ausentes/null y BSON original; no recibir datos financieros
  adicionales para construir un informe agregado.
- Un empaquetador streaming aplica presupuesto de documentos/bytes con una fila
  de anticipación. Oversize detiene y no avanza checkpoint sobre esa fila.
- `batchSize` del driver controla cantidad, pero **no garantiza** un presupuesto
  personalizado de bytes ni RSS. Los batches tienen además límites BSON del
  protocolo. [Referencia oficial](https://www.mongodb.com/docs/manual/reference/method/cursor.batchsize/).
- El presupuesto cliente debe incluir batch del driver, documento en decodificación,
  lote procesado, token y overhead Python. Un límite de procesamiento de 4 MiB no
  permite afirmar RSS máximo de 4 MiB; un documento puede superar ese límite antes
  de poder rechazarlo. Probar buffers reales y BSON grande antes de operación.
- Fijar timeouts/maxTimeMS, límite de ejecución/filas/bytes, cancelación y políticas
  de pausa. Un agotamiento no equivale a fin de colección. No cambiar configuración.

Escaneo físico y paso de duplicados son O(N) al menos; ordenar sin índice puede
ser O(N log N), bloquear o usar disco si se permite. El índice `_id` existente
puede ayudar al recorrido, pero filtro de usuario/tipo puede aumentar keys/docs
examinados. No se prometen latencias ni plan indexado sin mediciones.

## Consistencia y certificación

Particionar soluciona el problema de tipos, no la concurrencia. Una inserción en
partición agotada o con `_id` anterior al checkpoint puede omitirse; eliminar o
editar una fila visitada cambia el conjunto después de contarlo. El paso de
duplicados y el físico pueden observar momentos distintos.

Vista viva: mostrar conteos visitados con indicador de no certificación. No usar
majority como sinónimo de una instantánea global. Transacciones snapshot cortas
independientes tampoco comparten automáticamente la misma instantánea.

Certificación futura: ventana operacional demostrable de escritores detenidos
(internos/externos) durante inventario, todos los recorridos y verificación final,
UUID/contexto sin cambios, comparación de conteos y cobertura, cero errores o
fuentes incompatibles, y escritores posteriores de la versión/generación aprobadas.
Un snapshot global a clusterTime sería otra arquitectura: duración/retención y
compatibilidad necesitan aprobación/pruebas; no se implementa ni se presupone aquí.

Reanudar tras interrumpir la ventana exige empezar una verificación completa;
ninguna firma convierte un recorrido parcial previo en una certificación válida.
Este prototipo no emite certificados ni habilita lectores.

## Precondiciones para prueba sintética MongoDB posterior

Autorización nueva antes de cualquier conexión: URI local inequívoca, replica set
PRIMARY/sesiones, nombre de base sintética nueva comprobado ausente y fixtures R6
sin datos reales; no reutilizar las bases financieras o experimentales anteriores.
La creación de fixtures/metadata sintéticos deberá autorizarse explícitamente.

Dentro de ese aislamiento probar: filtros por partición contra orden MongoDB real,
tipos mixtos/Binary/Int64, colección sustituida, contexto incorrecto, documentos
BSON grandes, cursor y timeouts, reinicio/registro perdido, inserciones/eliminaciones,
sort duplicados y explain/memoria sin índices nuevos ni spill no autorizado.
Comparar con lector canónico y no borrar la base al terminar sin permiso.

Acceso real de diagnóstico debe usar permisos mínimos read-only, no endpoints
públicos. UUID financiero/default-user son consistencia, no autenticación. Un
escritor externo o restauración de datos invalida cobertura; no reparar nada.

## Pruebas offline disponibles

`python3 -B -m unittest backend.experiments.test_c3_mongodb_diagnosis_design -v`

23 casos de type bracketing modelado, particiones exhaustivas, tipos no soportados,
HMAC alterado/otro contexto, replay, pérdida de registro, agotamiento de partición,
BSON tipado, stream exacto de duplicados, 100.001 filas generadas, presupuestos y
omisiones posibles bajo concurrencia viva. Ninguna pipeline se ejecutó en MongoDB.

Validación final: 23 pruebas nuevas aprobadas; suite conjunta de 246 pruebas con
240 aprobadas y seis fallos históricos esperados, sin regresiones nuevas. Sintaxis,
análisis de operaciones restringidas y whitespace aprobados. Todas las pruebas son
offline; no hay mediciones ni ejecución de consultas MongoDB. Los archivos previos
permanecen sin cambios por comparación SHA-256, incluidos los 23 experimentales.
