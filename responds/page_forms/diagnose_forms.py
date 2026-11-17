"""
Diagnóstico do Microsoft Forms: imprime a estrutura real de cada pergunta.

Uso (na raiz do projeto, com o App Convert FECHADO, pois o perfil do navegador
não pode ser usado por dois processos ao mesmo tempo):

    uv run python -m converter.page_forms.diagnose_forms

Se pedir login, faça no navegador que abrir; o script continua sozinho.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

from app.page_forms.config import FormsConfig
from app.page_forms.service import PlaywrightFormsService, Q_ITEM

JS = """
(sel) => [...document.querySelectorAll(sel)].map((q, i) => ({
  i,
  innerText: (q.innerText || '').replace(/\\s+/g, ' ').slice(0, 160),
  textContent: (q.textContent || '').replace(/\\s+/g, ' ').slice(0, 160),
  automation_ids: [...new Set([...q.querySelectorAll('[data-automation-id]')]
      .map(e => e.getAttribute('data-automation-id')))],
  controls: [...q.querySelectorAll(
      "input, textarea, button, [role=combobox], [role=radio], [role=listbox], [aria-haspopup]")]
      .slice(0, 8).map(e => [
        e.tagName.toLowerCase(),
        'type=' + e.getAttribute('type'),
        'role=' + e.getAttribute('role'),
        'aria-label=' + e.getAttribute('aria-label'),
        'placeholder=' + e.getAttribute('placeholder'),
        'auto=' + e.getAttribute('data-automation-id'),
        'name=' + e.getAttribute('name'),
      ].join(' | '))
}))
"""


def main() -> None:
    profile = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path.home() / "Downloads" / "RFA" / "Forms" / "browser-profile"
    )
    cfg = FormsConfig(user_data_dir=str(profile), slow_mo_ms=0)

    with PlaywrightFormsService(cfg) as svc:
        svc.open_form()
        print("Aguardando o formulário (faça login no navegador se pedir)...")
        if not svc.wait_until_ready(600, lambda: False):
            print("Formulário não carregou.")
            return

        svc.page.wait_for_timeout(2000)
        data = svc.page.evaluate(JS, Q_ITEM)
        print(f"\n{len(data)} blocos encontrados em {Q_ITEM}\n")
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
