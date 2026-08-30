# Instalación de MCP

Spire distribuye un servidor MCP JSON-RPC sobre `stdio`. No abre puertos y no
requiere un paquete MCP adicional.

## Instalar

```bash
uv sync
```

Como alternativa:

```bash
python -m pip install -e ".[dev]"
```

## Iniciar el servidor

```bash
spire mcp
```

El proceso espera mensajes JSON-RPC por `stdin` y responde por `stdout`.
Configura el directorio de trabajo en la raíz del checkout para que Spire use
el archivo de configuración y el workspace de ese proyecto.

Ejemplo conceptual para Claude Desktop:

```json
{
  "mcpServers": {
    "spire": {
      "command": "spire",
      "args": ["mcp"],
      "cwd": "/ruta/al/checkout/spire-v2"
    }
  }
}
```

Si el ejecutable no está en el `PATH`, usa el entorno virtual explícito:

```json
{
  "mcpServers": {
    "spire": {
      "command": "/ruta/al/checkout/spire-v2/.venv/bin/spire",
      "args": ["mcp"],
      "cwd": "/ruta/al/checkout/spire-v2"
    }
  }
}
```

## Herramientas y autoridad

El servidor expone herramientas de estado de autenticación, cuentas,
descubrimiento, refresh explícito, campañas, evidencia, candidatos negativos y
runs. Puede preparar `UPDATE_BUDGET`, `ADD_NEGATIVE_KEYWORD` y
`CREATE_SEARCH_CAMPAIGN` hasta `WAITING_FOR_APPROVAL`; las campañas Search se
preparan siempre como `PAUSED`.

Los datasets segmentados de Google Ads requieren un rango finito. En
`account_refresh`, pasa `date_range` con `start` y `end` cuando necesites
evidencia de rendimiento.

No expone `approve_run`, `grant_authority` ni `mint_approval`. La aprobación
humana se realiza únicamente mediante el CLI confiable:

```bash
spire runs approve --run-id <run_id>
spire runs resume --run-id <run_id>
```

La autenticación inicial se realiza fuera de MCP:

```bash
spire auth google-ads login
spire auth google-ads verify --customer-id <customer_id>
```

Consulta [Google Ads Authentication](google-ads-auth.md) para credenciales y
cache de tokens.
