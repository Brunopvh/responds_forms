from __future__ import annotations
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from playwright.sync_api import (
    sync_playwright,
    Page,
    BrowserContext,
    Locator,
    TimeoutError as PlaywrightTimeout,
    Error as PlaywrightError,
)

from responds.page_forms.config import FormsConfig, FormsSubmission

Q_ITEM = "[data-automation-id='questionItem']"
Q_TITLE = "[data-automation-id='questionTitle']"
BTN_SUBMIT = "button[data-automation-id='submitButton']"


class FormSubmissionError(Exception):
    """Erro ao preencher ou enviar uma resposta do formulário."""


class PlaywrightFormsService:
    """
    Camada SERVICE: abre o Microsoft Forms em um Chromium (perfil persistente,
    então o login é feito uma única vez) e preenche UMA resposta por chamada
    de submit().

    IMPORTANTE: a API sync do Playwright tem afinidade de thread. start(),
    submit() e stop() devem ser chamados SEMPRE pela mesma thread
    (o ModelForms roda tudo em uma única worker thread).
    """

    def __init__(
        self, config: FormsConfig, *, log: Callable[[str], None] = print
    ) -> None:
        self.config: FormsConfig = config
        self.log = log
        self._pw = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        profile = Path(self.config.user_data_dir or ".forms-profile")
        profile.mkdir(parents=True, exist_ok=True)

        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=self.config.headless,
            slow_mo=self.config.slow_mo_ms,
            channel=self.config.browser_channel,
        )
        self._ctx.set_default_timeout(self.config.action_timeout_ms)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def stop(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.close()
        except PlaywrightError:
            pass
        finally:
            if self._pw is not None:
                try:
                    self._pw.stop()
                except PlaywrightError:
                    pass
            self._ctx = self._page = self._pw = None

    def __enter__(self) -> PlaywrightFormsService:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Chame start() antes de usar o service")
        return self._page

    # ------------------------------------------------------------------ abertura / login
    def open_form(self) -> None:
        self.page.goto(self.config.form_url, wait_until="domcontentloaded")

    def form_visible(self) -> bool:
        try:
            return self.page.locator(Q_ITEM).first.is_visible()
        except PlaywrightError:
            return False

    def _click_start_if_present(self) -> None:
        btn = self.page.get_by_role(
            "button", name=re.compile(r"^(iniciar agora|start now)$", re.I)
        ).first
        try:
            if btn.is_visible():
                btn.click()
        except PlaywrightError:
            pass

    def wait_until_ready(self, timeout_s: int, should_stop: Callable[[], bool]) -> bool:
        """
        Espera as perguntas aparecerem. Enquanto o usuário faz login no
        navegador a tela é a da Microsoft; quando o Forms carrega, o botão
        'Iniciar agora' (se existir) é clicado automaticamente.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if should_stop():
                return False
            if self.form_visible():
                return True
            self._click_start_if_present()
            self.page.wait_for_timeout(1000)
        return False

    @staticmethod
    def _is_checked(box: Locator) -> bool:
        try:
            return box.is_checked()
        except PlaywrightError:
            return False

    def _tick_receipt(self) -> None:
        page = self.page
        rx = re.compile(r"enviar-?me.*e-?mail", re.I)

        box = page.get_by_role("checkbox", name=rx).first
        try:
            box.wait_for(state="attached", timeout=5000)
        except PlaywrightTimeout:
            raise FormSubmissionError(
                "Checkbox 'e-mail de confirmação' não encontrado no formulário"
            )

        box.scroll_into_view_if_needed()
        if self._is_checked(box):  # idempotente: nunca desmarca
            return

        tentativas = (
            lambda: box.check(timeout=3000),
            lambda: box.check(force=True, timeout=3000),
            lambda: page.get_by_text(rx).first.click(timeout=3000),
        )
        for tentar in tentativas:
            try:
                tentar()
            except PlaywrightError:
                pass
            page.wait_for_timeout(300)
            if self._is_checked(box):
                self.log("  • e-mail de confirmação marcado")
                return

        raise FormSubmissionError("Não foi possível marcar o e-mail de confirmação")

    # ------------------------------------------------------------------
    # submit
    # ------------------------------------------------------------------

    def submit(self, sub: FormsSubmission) -> None:
        cfg = self.config

        if not self.form_visible():
            self.open_form()

            if not self.wait_until_ready(60, lambda: False):
                raise FormSubmissionError(
                    "Formulário não carregou (sessão expirada? faça login novamente)"
                )

        try:
            with self._step("UC"):
                self._fill_text(cfg.title_uc, sub.uc)
            with self._step("TOI"):
                self._fill_text(cfg.title_toi, sub.toi)
            with self._step("local da entrega"):
                self._choose_radio(cfg.title_local, sub.local_label)
            with self._step("tipo de documento"):
                self._choose_dropdown(cfg.title_tipo, sub.tipo_label)
            with self._step("upload de arquivo"):
                self._upload(cfg.title_fotos, sub.files)
            with self._step("data da entrega"):
                self._fill_date(cfg.title_data, sub.date)

            """
            Observações:
                Falha antes de enviar: se a caixa não puder ser marcada, a carta falha antes do envio, 
                em vez de ser lançada sem recibo. Como o envio no Forms não tem desfazer, acho isso 
                mais seguro. Se preferir só avisar no log e enviar mesmo assim, troque os dois raise 
                por self.log(...) e return.
            """

            if cfg.send_receipt:
                with self._step("e-mail de confirmação"):
                    self._tick_receipt()

            self._click_submit()

        except Exception:
            # tira o screenshot no model; aqui só limpa o estado para a próxima carta
            try:
                self.open_form()
                self.wait_until_ready(60, lambda: False)
            except Exception:
                pass
            raise

    def submit_old(self, sub: FormsSubmission) -> None:
        cfg = self.config

        if not self.form_visible():
            self.open_form()
            if not self.wait_until_ready(60, lambda: False):
                raise FormSubmissionError(
                    "Formulário não carregou (sessão expirada? faça login novamente)"
                )

        with self._step("UC"):
            self._fill_text(cfg.title_uc, sub.uc)
        with self._step("TOI"):
            self._fill_text(cfg.title_toi, sub.toi)
        with self._step("local da entrega"):
            self._choose_radio(cfg.title_local, sub.local_label)
        with self._step("tipo de documento"):
            self._choose_dropdown(cfg.title_tipo, sub.tipo_label)
        with self._step("upload de arquivo"):
            self._upload(cfg.title_fotos, sub.files)
        with self._step("data da entrega"):
            self._fill_date(cfg.title_data, sub.date)
        if cfg.send_receipt:
            self._tick_receipt()

        self._click_submit()

    def screenshot(self, path: str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=path, full_page=True)
            Path(path).with_suffix(".html").write_text(
                self.page.content(), encoding="utf-8"
            )
        except (PlaywrightError, OSError):
            pass

    # ------------------------------------------------------------------ helpers
    @contextmanager
    def _step(self, name: str) -> Iterator[None]:
        self.log(f"  • {name}")
        try:
            yield
        except FormSubmissionError:
            raise
        except PlaywrightError as e:
            first_line = (
                str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            )
            raise FormSubmissionError(f"Falha em '{name}': {first_line}") from e

    def _question(self, title_pattern: str) -> Locator:
        page = self.page
        rx = re.compile(title_pattern, re.I)

        # 1) bloco cujo título (questionTitle) bate com o padrão
        q = page.locator(Q_ITEM).filter(has=page.locator(Q_TITLE, has_text=rx)).first

        if q.count() == 0:
            # 2) fallback: bloco cujo texto completo bate com o padrão
            q = page.locator(Q_ITEM).filter(has_text=rx).first

        if q.count() == 0:
            n = page.locator(Q_ITEM).count()
            raise FormSubmissionError(
                f"Pergunta não encontrada: /{title_pattern}/ ({n} blocos questionItem na página)"
            )

        q.scroll_into_view_if_needed()
        return q

    def _fill_text(self, title_pattern: str, value: str) -> None:
        q = self._question(title_pattern)
        q.locator(
            "input[data-automation-id='textInput'], input[type='text']"
        ).first.fill(value)

    def _choose_radio(self, title_pattern: str, label: str) -> None:
        q = self._question(title_pattern)
        q.get_by_text(label, exact=True).first.click()

    def _choose_dropdown(self, title_pattern: str, label: str) -> None:
        q = self._question(title_pattern)
        q.locator(
            "[role='button'][aria-haspopup], [role='combobox'], [aria-haspopup]"
        ).first.click()

        # Passe STRING (não re.compile): evita o problema da "/" em regex JS.
        option = self.page.get_by_role("option", name=label, exact=True).first
        try:
            option.wait_for(state="visible", timeout=5000)
            option.click()
        except (PlaywrightTimeout, PlaywrightError):
            # Fallback: qualquer elemento visível com o texto exato da opção
            self.page.get_by_text(label, exact=True).last.click()

    def _upload(self, title_pattern: str, files: list[str]) -> None:
        if not files:
            raise FormSubmissionError("Nenhum arquivo informado para upload")
        for f in files:
            if not Path(f).is_file():
                raise FormSubmissionError(f"Arquivo não encontrado: {f}")

        page = self.page
        q = self._question(title_pattern)
        btn = q.locator("button[data-automation-id='fileUploadButton']").first

        try:
            with page.expect_file_chooser(timeout=8000) as chooser:
                btn.click()
            chooser.value.set_files(files)
        except PlaywrightTimeout:
            # Fallback: input[type=file] direto, como no projeto antigo.
            q.locator("input[type='file']").first.set_input_files(files)

        # Espera o nome do arquivo aparecer na lista (upload concluído).
        # Se o nome vier truncado, segue em frente: o envio final valida o campo obrigatório.
        for f in files:
            try:
                page.get_by_text(Path(f).name).first.wait_for(
                    timeout=self.config.upload_timeout_ms
                )
            except PlaywrightTimeout:
                page.wait_for_timeout(3000)

    def _fill_date(self, title_pattern: str, date: str) -> None:
        q = self._question(title_pattern)
        field_ = q.locator(
            "input[placeholder^='Insira a data'], input[placeholder*='dd/MM']"
        ).first
        field_.fill(date)
        field_.press("Tab")

    def _click_submit(self) -> None:
        page = self.page
        self.log("  • enviando")
        btn = page.locator(BTN_SUBMIT)
        btn.scroll_into_view_if_needed()
        btn.click()
        try:
            btn.wait_for(state="detached", timeout=30000)
        except PlaywrightTimeout:
            alerts = [
                t.strip()
                for t in page.locator("[role='alert']").all_inner_texts()
                if t.strip()
            ]
            detail = (
                " | ".join(alerts) if alerts else "sem mensagem de validação visível"
            )
            raise FormSubmissionError(f"Envio não confirmado: {detail}")
        page.wait_for_timeout(self.config.wait_after_submit_ms)
