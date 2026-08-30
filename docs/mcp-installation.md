# Instalación de MCP

## Estado actual

Spire v2 todavía no distribuye un servidor MCP ejecutable. El repositorio
contiene la superficie interna `McpExecutionSurface`, pero no contiene:

- un comando `spire mcp`;
- un entrypoint MCP para `stdio`, SSE o Streamable HTTP;
- un registro automático para Claude Desktop, Cursor u otro host MCP.

Por lo tanto, actualmente no hay una instalación MCP soportada que añadir a
la configuración de un cliente externo. No uses un comando o una ruta
inventados como `spire mcp install`.

## Lo que sí se puede instalar

Instala Spire como paquete editable desde la raíz del repositorio:

```text
python -m pip install -e ".[dev]"
```

Esto instala el paquete Python y sus herramientas de desarrollo. También
habilita el CLI de autenticación:

```text
spire auth google-ads status
spire auth google-ads login
spire auth google-ads verify --customer-id <customer_id>
```

La autenticación está documentada en
[Google Ads Authentication](google-ads-auth.md).

## Superficie MCP interna

La clase `McpExecutionSurface` representa la frontera prevista para llamadas
de agente, pero no es un servidor MCP ni abre un puerto. Su responsabilidad
actual es preparar cambios a través del servicio canónico; no puede aprobar ni
conceder autoridad a sí misma.

No es necesario instalar un paquete MCP adicional para las pruebas internas.
Las pruebas se ejecutan con:

```text
pytest
```

## Cuando exista un servidor MCP

La instalación deberá documentarse junto con el entrypoint real y su contrato
de transporte. Como mínimo, esa guía tendrá que especificar:

1. instalación del paquete;
2. comando exacto del servidor;
3. configuración para el host MCP elegido;
4. variables de entorno y ubicación de credenciales;
5. herramientas expuestas;
6. límites de autoridad y aprobación humana;
7. comprobación con una llamada de solo lectura.

Hasta que ese entrypoint exista, las capacidades Python y el CLI de
autenticación son las únicas superficies soportadas.
