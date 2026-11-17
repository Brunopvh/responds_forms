from pyflutter_ui import AppConfigNotifier, TkMaterialApp, run_app
from responds.page_forms import ControllerForms, ModelForms
from responds.page_forms.view_forms import PageRespondsForms
from responds.page_whatsapp import ControllerWhatsAppPage, ModelWhatsApp
from responds.page_settings import ControllerSettings, ModelSettings


def run_ui_forms() -> None:
    app = TkMaterialApp(PageRespondsForms(), width=1100, height=700)

    # ANTES do run_app (lê o tema salvo)
    app.register_notifier(AppConfigNotifier.create())

    app.register_notifier(ControllerForms(ModelForms()))
    app.register_notifier(ControllerWhatsAppPage(ModelWhatsApp()))

    settings = ControllerSettings(ModelSettings())
    app.register_notifier(settings)
    settings.apply_saved_config()  # reaplica o dir das cartas salvo

    run_app(app)


def main():
    run_ui_forms()


if __name__ == "__main__":
    main()
