from __future__ import annotations
from dataclasses import dataclass, field
from cartas import LocalEntregaCarta, TipoCarta

FORMS_URL = (
    "https://forms.office.com/pages/responsepage.aspx"
    "?id=hoDG-Fy5y0mdOO03lAq-9Q3te9L0aHxBnNMUUIYjxH9UMVFGS0ozVEVKVU84RlBDNTJXVlQ1UUZZRy4u"
)

# Enum interno (HeaderTOI/LocalEntregaCarta) -> texto EXATO da opção no Forms.
LOCAL_LABELS: dict[str, str] = {
    LocalEntregaCarta.OUTRO.value: "OUTRO LOCAL DE ENTREGA",
    LocalEntregaCarta.MAOS.value: "ENTREGUE EM MÃOS",
    LocalEntregaCarta.CORREIOS.value: "CAIXA DE CORREIOS",
    LocalEntregaCarta.PORTAO.value: "PORTA/PORTÃO",
}

# Enum interno (TipoCarta) -> texto EXATO da opção na lista suspensa.
TIPO_LABELS: dict[str, str] = {
    TipoCarta.CARTA_CALCULO.value: "CARTA/FATURA",
}

DEFAULT_LOCAL = LocalEntregaCarta.OUTRO.value
DEFAULT_TIPO = TipoCarta.CARTA_CALCULO.value


@dataclass
class FormsSubmission:
    """
    Contrato entre Model e Service: UMA resposta do formulário, já validada
    e com os textos finais das opções. O Service não conhece pandas nem PyFlutter.
    """

    uc: str
    toi: str
    local_label: str
    tipo_label: str
    date: str  # dd/MM/yyyy
    files: list[str] = field(default_factory=list)


@dataclass
class FormsConfig:
    form_url: str = FORMS_URL

    # Perfil persistente do Chromium: o login Microsoft fica salvo entre execuções.
    user_data_dir: str = ""
    screenshot_dir: str = ""
    headless: bool = False
    slow_mo_ms: int = 150  # pausa automática entre CADA ação do Playwright
    pause_between_rows_s: float = 1.5  # pausa entre uma carta e outra
    browser_channel: str | None = "msedge"  # ex.: "chrome" para usar o Chrome instalado

    login_timeout_s: int = 900
    action_timeout_ms: int = 15000
    upload_timeout_ms: int = 120000
    wait_after_submit_ms: int = 1500
    send_receipt: bool = True  # marcar "Enviar-me um email de confirmação"

    # Regex (case-insensitive) que identifica o TÍTULO de cada pergunta.
    # O texto do bloco vem colado ("1.UCTexto de linha única."), por isso NÃO
    # se usa \b: ancora no início, depois do número da pergunta ("1.", "2." ...).
    title_uc: str = r"^\s*\d+\.\s*UC"
    title_toi: str = r"^\s*\d+\.\s*TOI"
    title_local: str = r"^\s*\d+\.\s*LOCAL DA ENTREGA"
    title_tipo: str = r"^\s*\d+\.\s*TIPO DE DOCUMENTO"
    title_fotos: str = r"^\s*\d+\.\s*FOTOS"
    title_data: str = r"^\s*\d+\.\s*DATA DA ENTREGA"
