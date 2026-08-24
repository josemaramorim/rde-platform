"""
start_tunnel.py — RDE Platform
Inicia o Cloudflare Quick Tunnel, captura a URL e atualiza tunnel_config.json.
Uso: python start_tunnel.py
O tunnel roda até Ctrl+C.
"""
import os, sys, subprocess, json, re, signal
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

def find_cloudflared():
    import shutil
    for p in [shutil.which("cloudflared"), str(ROOT / "cloudflared.exe")]:
        if p and Path(p).exists():
            return p
    return None

def main():
    cf = find_cloudflared()
    if not cf:
        print("  ERRO: cloudflared não encontrado. Execute setup_tunnel.py primeiro.")
        sys.exit(1)

    print("=" * 60)
    print("  RDE Platform - Iniciando Cloudflare Tunnel")
    print("=" * 60)
    print()

    proc = subprocess.Popen(
        [cf, "tunnel", "--url", "http://localhost:8000", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "TUNNEL_NO_AUTOUPDATE": "1"}
    )

    url = None
    try:
        for line in iter(proc.stdout.readline, ""):
            print(line, end="")
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not url:
                url = m.group(0)
                print()
                print("=" * 60)
                print(f"  TUNNEL URL: {url}")
                print("=" * 60)
                print()
                print("  Compartilhe esta URL com os clientes.")
                print("  Eles devem acessar /setup e colar esta URL.")
                print()
                # Salva no tunnel_config.json
                (ROOT / "tunnel_config.json").write_text(
                    json.dumps({"admin_server_url": url, "tunnel_url": url}, indent=2),
                    encoding="utf-8"
                )
                print("  (URL salva em tunnel_config.json)")
                print()

    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait(timeout=10)

if __name__ == "__main__":
    main()
