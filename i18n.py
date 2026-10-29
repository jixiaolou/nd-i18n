# ====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ======================= END GPL LICENSE BLOCK ========================

"""JSON based internationalisation.

Every language is one JSON file in the ``locales`` folder:

    {
      "locale": "zh_HANS",     <- Blender locale identifier
      "name": "简体中文",       <- label shown in the Language menu
      "messages": {
        "<message id>": "<translation>",
        ...
      }
    }

Adding a language is just dropping a new JSON file in ``locales/``; no code
change is needed. Message IDs are the English strings used in the source code,
so ``en_US.json`` maps every ID to itself and doubles as the reference list of
translatable strings.

Two layers are supported:

* Blender's own translation catalogue, registered with
  ``bpy.app.translations.register()``. This translates RNA names/descriptions
  (property labels and tooltips) and operator names.
* A language chosen explicitly in the add-on preferences. For text the add-on
  draws itself the choice is applied directly; for RNA strings the chosen
  language is additionally injected into the catalogue Blender currently uses,
  so labels follow the choice too.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import bpy

# TODO: set this to the add-on name; it is only used in log messages.
ADDON_NAME = "ND"

#: Value of the language property that means "use Blender's own language".
AUTO = "AUTO"

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

# Blender looks strings up with different contexts, depending on where they are
# drawn. Registering every message under all of them is cheap and prevents
# "translated everywhere except in that one panel" surprises.
_TRANSLATION_CONTEXTS = ("*", "Operator", "Property")

_MODULE_NAME = __name__

#: locale identifier -> {"name": str, "messages": {msgid: translation}}
_LOCALES: Dict[str, dict] = {}

#: Language selected in the add-on preferences (``AUTO`` or a locale id).
_pref_language: str = AUTO

#: Locale forced by the preferences, or None when following Blender.
_forced_locale: Optional[str] = None

_translations_registered = False


# ---------------------------------------------------------------------------
# Loading the JSON language files
# ---------------------------------------------------------------------------


def load_locales() -> Dict[str, dict]:
    """(Re)load every ``*.json`` file in the locales folder."""
    _LOCALES.clear()
    if not os.path.isdir(LOCALES_DIR):
        print(f"{ADDON_NAME}: locales folder not found: {LOCALES_DIR}")
        return _LOCALES

    for filename in sorted(os.listdir(LOCALES_DIR)):
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(LOCALES_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError) as ex:
            print(f"{ADDON_NAME}: skipping locale file {filename}: {ex}")
            continue

        if not isinstance(data, dict):
            print(f"{ADDON_NAME}: skipping locale file {filename}: not an object")
            continue

        messages = data.get("messages")
        if not isinstance(messages, dict):
            print(f"{ADDON_NAME}: skipping locale file {filename}: no messages")
            continue

        locale = str(data.get("locale") or os.path.splitext(filename)[0])
        _LOCALES[locale] = {
            "name": str(data.get("name") or locale),
            "messages": {
                str(msgid): str(translation)
                for msgid, translation in messages.items()
                if isinstance(translation, str)
            },
        }

    return _LOCALES


def available_locales() -> List[str]:
    """Locale identifiers of all loaded language files, sorted by their label."""
    return sorted(_LOCALES, key=lambda loc: _LOCALES[loc]["name"])


def locale_label(locale: str) -> str:
    data = _LOCALES.get(locale)
    return data["name"] if data else locale


def load_msgids() -> List[str]:
    """All message IDs, taken from the English file (or the union of all files)."""
    msgids = []
    seen = set()
    order = []
    if "en_US" in _LOCALES:
        order.append("en_US")
    order.extend(loc for loc in _LOCALES if loc != "en_US")
    for locale in order:
        for msgid in _LOCALES[locale]["messages"]:
            if msgid not in seen:
                seen.add(msgid)
                msgids.append(msgid)
    return msgids


# ---------------------------------------------------------------------------
# Blender translation catalogue
# ---------------------------------------------------------------------------


def _ui_locale() -> str:
    """The language Blender's interface is currently displayed in."""
    try:
        language = bpy.context.preferences.view.language
    except AttributeError:  # Not available during early start-up.
        return "en_US"
    if not language or language == "DEFAULT":
        return "en_US"
    return language


def _catalog(messages: Dict[str, str]) -> Dict[Tuple[str, str], str]:
    catalog = {}
    for msgid, translation in messages.items():
        for context in _TRANSLATION_CONTEXTS:
            catalog[(context, msgid)] = translation
    return catalog


def build_catalogs(forced_locale: Optional[str] = None) -> Dict[str, dict]:
    """Build the dictionary handed to ``bpy.app.translations.register()``."""
    catalogs = {
        locale: _catalog(data["messages"]) for locale, data in _LOCALES.items()
    }

    if forced_locale and forced_locale in _LOCALES:
        ui_locale = _ui_locale()
        if forced_locale != ui_locale:
            # Blender only consults the catalogue of the language it displays.
            # Injecting the chosen language there makes RNA strings (property
            # names/tooltips, operator names) follow the add-on preference too.
            catalogs[ui_locale] = _catalog(_LOCALES[forced_locale]["messages"])
    return catalogs


def register_translations(forced_locale: Optional[str] = None) -> None:
    global _translations_registered

    # Always unregister first: after a module reload the flag may say "not
    # registered" while Blender still holds a catalogue from a previous
    # registration, which would make register() fail.
    unregister_translations(force=True)
    try:
        bpy.app.translations.register(_MODULE_NAME, build_catalogs(forced_locale))
        _translations_registered = True
    except Exception as ex:  # Never block loading the add-on over this.
        print(f"{ADDON_NAME}: could not register translations: {ex}")


def unregister_translations(force: bool = False) -> None:
    global _translations_registered

    if not _translations_registered and not force:
        return
    try:
        bpy.app.translations.unregister(_MODULE_NAME)
    except Exception:
        pass
    _translations_registered = False


# ---------------------------------------------------------------------------
# The language actually used
# ---------------------------------------------------------------------------


def activate(pref_language: Optional[str]) -> None:
    """Apply the language chosen in the add-on preferences."""
    global _pref_language, _forced_locale

    _pref_language = pref_language or AUTO
    if _pref_language == AUTO or _pref_language not in _LOCALES:
        _forced_locale = None
    else:
        _forced_locale = _pref_language

    register_translations(_forced_locale)
    redraw_all()


def ensure_active(pref_language: Optional[str]) -> None:
    """Apply the preference, but only when it actually changed."""
    if (pref_language or AUTO) != _pref_language:
        activate(pref_language)


def active_locale() -> Optional[str]:
    """Locale providing the strings right now, or None for "untranslated"."""
    if _forced_locale:
        return _forced_locale
    ui_locale = _ui_locale()
    return ui_locale if ui_locale in _LOCALES else None


def redraw_all() -> None:
    """Redraw the whole UI, so a language change is visible immediately."""
    try:
        windows = bpy.context.window_manager.windows
    except AttributeError:
        return
    for window in windows:
        for area in window.screen.areas:
            area.tag_redraw()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def t(msgid: str) -> str:
    """Translate a message ID; returns the message ID when untranslated."""
    locale = active_locale()
    if locale:
        translation = _LOCALES[locale]["messages"].get(msgid)
        if translation is not None:
            return translation

    # Fall back to Blender's own catalogue, for languages that Blender ships but
    # this add-on has no JSON file for.
    try:
        return bpy.app.translations.pgettext_iface(msgid)
    except AttributeError:  # Very old Blender versions.
        return msgid


def counted(singular: str, plural: str, count: float, value: str) -> str:
    """Translate a counted phrase, picking the singular or plural variant."""
    msgid = singular if round(count) == 1 else plural
    return t(msgid).format(count=value)


def build_language_items() -> Tuple[Tuple[str, str, str], ...]:
    """EnumProperty items for the Language menu in the preferences.

    The items are built once, at import time, instead of using an items
    callback. Blender has a long standing bug with dynamic enum items ("Python
    must keep a reference to the strings returned by the callback or Blender
    will misbehave"), and on several builds registering such a property simply
    fails with ``'language' EnumProperty could not register``.
    """
    items = [
        (
            AUTO,
            "Follow Blender's interface language",
            "Interface language used by this add-on. "
            "The first entry follows Blender's own language.",
        )
    ]
    for locale in available_locales():
        label = locale_label(locale)
        items.append((locale, label, label))
    return tuple(items)


load_locales()

#: Static items for the Language enum property. Must be kept alive forever.
LANGUAGE_ITEMS = build_language_items()
