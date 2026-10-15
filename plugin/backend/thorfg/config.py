import math
import re
import tomllib

import tomlkit

from .paths import ThorError


PREFIX = "ThorFG:"
from .bundle import SLOT


def defaults():
    return {"schema_version": 1, "active_runtime": None, "profiles": {}}


def migrate_settings(data):
    if not isinstance(data, dict):
        raise ThorError("Повреждены настройки ThorFG")
    version = data.get("schema_version", 0)
    if version == 0:
        # Ранние локальные прототипы хранили profiles без версии схемы.
        data = {**defaults(), **data, "schema_version": 1}
    if data.get("schema_version") != 1 or not isinstance(data.get("profiles"), dict):
        raise ThorError("Версия настроек ThorFG не поддерживается")
    for appid, profile in data["profiles"].items():
        data["profiles"][appid] = validate_profile(appid, profile)
    active = data.get("active_runtime")
    if active is not None and (not isinstance(active, str) or not SLOT.fullmatch(active)):
        raise ThorError("Неверный активный runtime")
    return data


def validate_profile(appid, value):
    if not isinstance(appid, str) or not re.fullmatch(r"[0-9]{1,12}", appid):
        raise ThorError("Неверный Steam App ID")
    if not isinstance(value, dict):
        raise ThorError("Некорректный профиль")
    allowed = {"enabled", "multiplier", "flow_scale", "performance_mode", "process", "runtime"}
    if set(value) - allowed:
        raise ThorError("Неизвестные параметры профиля")
    result = {"enabled": False, "multiplier": 2, "flow_scale": 0.5,
              "performance_mode": True, "process": "", "runtime": "historical", **value}
    for key in ("enabled", "performance_mode"):
        if type(result[key]) is not bool:
            raise ThorError("Переключатель должен иметь логическое значение")
    if type(result["multiplier"]) is not int or result["multiplier"] not in (2, 3, 4):
        raise ThorError("Поддерживаются множители x2, x3 и x4")
    scale = result["flow_scale"]
    if type(scale) not in (int, float) or not math.isfinite(scale) or not 0.25 <= scale <= 1.0:
        raise ThorError("Flow Scale должен быть от 0.25 до 1.0")
    process = result["process"]
    if not isinstance(process, str) or len(process) > 512 or any(ord(c) < 32 for c in process):
        raise ThorError("Некорректное имя процесса")
    if "\\" in process:
        raise ThorError("Используйте имя EXE или суффикс пути с / как в Linux")
    if result["enabled"] and (not process.strip() or process.startswith("/") or ".." in process.split("/")):
        raise ThorError("Укажите имя реального процесса игры")
    if not isinstance(result["runtime"], str) or not SLOT.fullmatch(result["runtime"]):
        raise ThorError("Некорректное имя runtime")
    return result


def parse_config(raw):
    try:
        text = raw.decode("utf-8") if raw is not None else "version = 2\n[global]\nallow_fp16 = true\n"
        parsed = tomllib.loads(text)
        if parsed.get("version") != 2 or type(parsed.get("version")) is not int:
            raise ThorError("Поддерживается только конфигурация LSFG-VK version=2")
        if not isinstance(parsed.get("global", {}), dict) or not isinstance(parsed.get("profile", []), list):
            raise ThorError("Неверная структура конфигурации LSFG-VK")
        for profile in parsed.get("profile", []):
            if not isinstance(profile, dict):
                raise ThorError("Неверная структура профиля LSFG-VK")
            targets(profile)
            if not isinstance(profile.get("name", ""), str):
                raise ThorError("Название профиля LSFG-VK должно быть строкой")
            multiplier = profile.get("multiplier", 2)
            flow = profile.get("flow_scale", 1.0)
            if type(multiplier) is not int or multiplier < 1:
                raise ThorError("Некорректный множитель существующего профиля")
            if type(flow) not in (int, float) or not math.isfinite(flow) or not .25 <= flow <= 1:
                raise ThorError("Некорректный Flow Scale существующего профиля")
            if type(profile.get("performance_mode", False)) is not bool:
                raise ThorError("Некорректный Performance Mode существующего профиля")
        global_conf = parsed.get("global", {})
        if "dll" in global_conf and not isinstance(global_conf["dll"], str):
            raise ThorError("Путь DLL должен быть строкой")
        if type(global_conf.get("allow_fp16", True)) is not bool:
            raise ThorError("allow_fp16 должен иметь логическое значение")
        return tomlkit.parse(text)
    except (ValueError, UnicodeError, TypeError, tomlkit.exceptions.TOMLKitError) as exc:
        raise ThorError("Не удалось прочитать конфигурацию TOML; исходный файл сохранён") from exc


def targets(profile):
    value = profile.get("active_in", [])
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ThorError("Некорректное поле active_in")
    return value


def validate_compatibility(document, adapter):
    if adapter != "stable-2.0":
        for profile in document.get("profile", []):
            if profile.get("multiplier", 2) <= 1 or profile.get("pacing", "none") != "none":
                raise ThorError("Профиль несовместим с историческим runtime")
        return
    if set(document) - {"version", "global", "profile"}:
        raise ThorError("Стабильная 2.0 отвергает неизвестные верхние поля TOML")
    if set(document.get("global", {})) - {"dll", "allow_fp16", "log_level", "log_file"}:
        raise ThorError("Глобальные поля несовместимы со стабильной 2.0")
    allowed = {"name", "active_in", "multiplier", "flow_scale", "performance_mode",
               "pacing", "pacing_mode", "override_present_mode", "preserve_swapchain_image_count"}
    for profile in document.get("profile", []):
        if set(profile) - allowed:
            raise ThorError("Поля профиля несовместимы со стабильной 2.0; исходный TOML сохранён")
        pacing = profile.get("pacing_mode", profile.get("pacing", "vsync"))
        if not isinstance(pacing, str) or pacing.lower() not in ("vsync", "none"):
            raise ThorError("Неподдерживаемый режим pacing")
        for key in ("override_present_mode", "preserve_swapchain_image_count"):
            if key in profile and type(profile[key]) is not bool:
                raise ThorError("Неверный тип параметра стабильного runtime")


def render(raw, profiles, adapter="historical-2dev", dll=None):
    document = parse_config(raw)
    validate_compatibility(document, adapter)
    existing = document.get("profile", [])
    managed = {}
    result = tomlkit.aot()
    for profile in existing:
        name = profile.get("name", "")
        appid = name[len(PREFIX):] if isinstance(name, str) and name.startswith(PREFIX) else None
        if appid in profiles:
            if appid in managed:
                raise ThorError("Дублирующиеся профили ThorFG в конфигурации")
            managed[appid] = profile
        else:
            result.append(profile)
    all_targets = [target for item in result for target in targets(item)]
    for appid, profile in profiles.items():
        profile = validate_profile(appid, profile)
        if not profile["enabled"]:
            continue
        target = profile["process"]
        if any(target.endswith(other) or other.endswith(target) for other in all_targets):
            raise ThorError("Профиль процесса конфликтует с существующим active_in")
        all_targets.append(target)
        table = managed.get(appid, tomlkit.table())
        table.update({"name": PREFIX + appid, "active_in": [target],
                      "multiplier": profile["multiplier"], "flow_scale": float(profile["flow_scale"]),
                      "performance_mode": profile["performance_mode"]})
        result.append(table)
    if result:
        document["profile"] = result
    else:
        document["profile"] = []
    if "global" not in document:
        document["global"] = tomlkit.table()
    if dll:
        document["global"]["dll"] = dll
    output = tomlkit.dumps(document).encode("utf-8")
    parse_config(output)
    validate_compatibility(document, adapter)
    return output
