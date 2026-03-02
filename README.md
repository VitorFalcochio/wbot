# WAHA Print Bot (Windows)

Bot de impressao automatica para WhatsApp usando WAHA + FastAPI.

Quando uma mensagem chegar com `#IMPRESSAO` na ultima linha, o bot:
- valida o evento `message.any`
- remove o gatilho do texto
- evita duplicidade com `state.json`
- imprime em impressora termica ESC/POS (TCP 9100) ou Win32

## Como Funciona

1. WAHA recebe mensagens do WhatsApp.
2. WAHA envia webhook para `POST /waha/webhook`.
3. `waha.py` valida gatilho e deduplicacao.
4. Bot imprime o pedido.

## Quick Start (5 minutos)

### 1) Requisitos
- Windows
- Docker Desktop ativo
- Python 3.11+
- WhatsApp no celular para parear

### 2) Instalar dependencias Python
```powershell
cd C:\Waha
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests pywin32
```

### 3) Configurar ambiente
Use `waha.env.example` como base e crie/ajuste `waha.env`.

Minimo recomendado:
```env
WAHA_API_KEY=SEU_TOKEN
PRINT_MODE=ip
PRINTER_IP=192.168.0.130
PRINTER_PORT=9100
TRIGGER=#IMPRESSAO
WAHA_WEBHOOK_URL=http://IP_DO_PC:8000/waha/webhook
```

Se for Win32:
```env
PRINT_MODE=win32
PRINTER_NAME=Nome da impressora no Windows
```

### 4) Subir sistema
```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\run_bot_forever.ps1
```

Esse comando garante:
- WAHA em `http://localhost:3000`
- Bot em `http://localhost:8000`

### 5) Parear WhatsApp no WAHA
- Abrir `http://localhost:3000/dashboard`
- `Sessions > default`
- Escanear QR
- Confirmar status `WORKING`

## Teste Rapido

Envie para seu proprio numero:
```text
PEDIDO #1001
1x X-Burger
1x Suco de Laranja
Observacao: sem cebola
#IMPRESSAO
```

Checagens:
- WAHA ativo: `http://localhost:3000`
- Bot ativo: `http://localhost:8000/health` -> `{"ok":true}`

## Inicio Automatico no Windows

### Instalar startup
```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\install_windows_startup.ps1
```

### Remover startup
```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\uninstall_windows_startup.ps1
```

## Arquivos Principais
- `waha.py`: webhook FastAPI + regra de impressao
- `waha.env`: configuracoes locais (NAO versionar)
- `waha.env.example`: modelo de configuracao
- `run_bot_forever.ps1`: supervisao/restart do bot
- `ensure_waha_container.ps1`: sobe/garante container WAHA
- `install_windows_startup.ps1`: instala auto start
- `uninstall_windows_startup.ps1`: remove auto start
- `MANUAL.txt`: guia completo de instalacao para cliente

## Troubleshooting

### Sessao nao fica em WORKING
- Refaca pareamento no dashboard.
- Verifique se o celular tem internet estavel.

### Nao imprime
- Confira `PRINT_MODE`, `PRINTER_IP`/`PRINTER_NAME`.
- Verifique se `#IMPRESSAO` esta na ultima linha.
- Confirme se a mensagem chega como `fromMe=true` quando `PRINT_SOURCE_MODE=from_me_only`.

### WAHA nao sobe
- Confirmar Docker Desktop ativo.
- Rodar `ensure_waha_container.ps1` manualmente e revisar logs.

## Seguranca
- Nao suba `waha.env` para o Git.
- Nao exponha `WAHA_API_KEY`.
- Mantenha o servidor em rede confiavel.
