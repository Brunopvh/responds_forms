from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from table_stream import File
from pyflutter_ui import ThemeMode

SCHEMA_VERSION: Final[int] = 1
MAX_JSON_BYTES: Final[int] = 256 * 1024  # um config legítimo tem poucos KB
MAX_NAMED_DIRS: Final[int] = 50
MAX_PATH_LEN: Final[int] = 1024


class ConfigValidationError(ValueError):
    """Arquivo de configuração rejeitado (estrutura/tipos/caminhos inseguros)."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems: list[str] = problems


@dataclass(frozen=True)
class ImportedSettings:
    """Somente os campos presentes e válidos no arquivo importado."""

    initial_dir: Path | None = None
    last_dir: Path | None = None
    work_dir: Path | None = None
    documents_dir: Path | None = None
    cartas_dir: Path | None = None
    theme_mode: ThemeMode | None = None
    initial_dir_map: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportPlan:
    settings: ImportedSettings
    skipped: list[str]  # campos ignorados (ex.: pasta inexistente neste computador)


class ConfigValidator:
    """
    Valida o JSON importado. Entrada NÃO confiável: nada é executado, só lido.

    Rejeita o arquivo inteiro se: não for objeto JSON, schema_version diferente,
    chaves desconhecidas, tipos errados, caminho relativo, UNC (\\\\servidor\\...)
    ou com byte nulo. Pasta inexistente só é ignorada (e reportada).
    """

    _PATH_KEYS: Final[tuple[str, ...]] = (
        "initial_dir",
        "last_dir",
        "work_dir",
        "documents_dir",
        "cartas_dir",
    )
    _ALLOWED: Final[frozenset[str]] = frozenset(
        {"schema_version", "theme_mode", "initial_dir_map", *_PATH_KEYS}
    )

    def validate(self, raw: object) -> ImportPlan:
        if not isinstance(raw, dict):
            raise ConfigValidationError(["O arquivo precisa conter um objeto JSON ({...})."])

        problems: list[str] = []
        skipped: list[str] = []

        if raw.get("schema_version") != SCHEMA_VERSION:
            problems.append(f"schema_version inválido (esperado {SCHEMA_VERSION}).")

        for key in raw:
            if key not in self._ALLOWED:
                problems.append(f"Chave desconhecida: {key!r}")

        paths: dict[str, Path] = {}
        for key in self._PATH_KEYS:
            if key in raw:
                parsed = self._parse_dir(key, raw[key], problems, skipped)
                if parsed is not None:
                    paths[key] = parsed

        theme = self._parse_theme(raw["theme_mode"], problems) if "theme_mode" in raw else None
        named = self._parse_named(raw.get("initial_dir_map", {}), problems, skipped)

        if problems:
            raise ConfigValidationError(problems)

        return ImportPlan(
            ImportedSettings(
                initial_dir=paths.get("initial_dir"),
                last_dir=paths.get("last_dir"),
                work_dir=paths.get("work_dir"),
                documents_dir=paths.get("documents_dir"),
                cartas_dir=paths.get("cartas_dir"),
                theme_mode=theme,
                initial_dir_map=named,
            ),
            skipped,
        )

    @staticmethod
    def _parse_dir(
        label: str, value: object, problems: list[str], skipped: list[str]
    ) -> Path | None:
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{label}: deve ser um texto não vazio.")
            return None
        if "\x00" in value or len(value) > MAX_PATH_LEN:
            problems.append(f"{label}: caminho inválido.")
            return None
        if value.startswith(("\\\\", "//")):
            problems.append(f"{label}: caminhos de rede (UNC) não são aceitos.")
            return None

        path = Path(os.path.normpath(value))
        if not path.is_absolute():
            problems.append(f"{label}: o caminho precisa ser absoluto.")
            return None
        try:
            exists = path.is_dir()
        except OSError:
            exists = False
        if not exists:
            skipped.append(f"{label}: pasta inexistente neste computador ({value})")
            return None
        return path

    @staticmethod
    def _parse_theme(value: object, problems: list[str]) -> ThemeMode | None:
        if isinstance(value, str):
            try:
                return ThemeMode(value.strip().lower())
            except ValueError:
                pass
        problems.append("theme_mode: use 'dark', 'light' ou 'system'.")
        return None

    def _parse_named(
        self, value: object, problems: list[str], skipped: list[str]
    ) -> dict[str, Path]:
        result: dict[str, Path] = {}
        if not isinstance(value, dict):
            problems.append("initial_dir_map: deve ser um objeto {nome: pasta}.")
            return result
        if len(value) > MAX_NAMED_DIRS:
            problems.append(f"initial_dir_map: máximo de {MAX_NAMED_DIRS} entradas.")
            return result

        for name, item in value.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 64:
                problems.append(f"initial_dir_map: nome inválido: {name!r}")
                continue
            parsed = self._parse_dir(f"initial_dir_map[{name}]", item, problems, skipped)
            if parsed is not None:
                result[name] = parsed
        return result


class ModelSettings:
    """Model: sem UI. Lê/grava o JSON de configurações com validação."""

    def __init__(self, validator: ConfigValidator | None = None) -> None:
        self._validator: ConfigValidator = validator or ConfigValidator()

    def export_config(self, data: dict[str, object], target: File) -> None:
        """Grava o JSON de forma atômica (tmp + replace): nunca deixa arquivo pela metade."""
        payload: dict[str, object] = {"schema_version": SCHEMA_VERSION, **data}
        text = json.dumps(payload, ensure_ascii=False, indent=2)

        final = Path(target.absolute())
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, final)

    def read_import(self, source: File) -> ImportPlan:
        path = Path(source.absolute())
        try:
            if path.stat().st_size > MAX_JSON_BYTES:
                raise ConfigValidationError(
                    [f"Arquivo muito grande (máximo {MAX_JSON_BYTES // 1024} KB)."]
                )
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ConfigValidationError([f"Não foi possível ler o arquivo: {e}"]) from e

        try:
            raw: object = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(
                [f"JSON inválido (linha {e.lineno}, coluna {e.colno})."]
            ) from e
        except RecursionError as e:
            raise ConfigValidationError(["JSON aninhado demais."]) from e

        return self._validator.validate(raw)
