# ███╗   ██╗██████╗
# ████╗  ██║██╔══██╗
# ██╔██╗ ██║██║  ██║
# ██║╚██╗██║██║  ██║
# ██║ ╚████║██████╔╝
# ╚═╝  ╚═══╝╚═════╝
#
# ND (Non-Destructive) Blender Add-on
# Copyright (C) 2024 Tristan S. & Ian J. (HugeMenace)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ---
# Contributors: Tristo (HM)
# ---

import bpy
import re
from math import radians
from .. import i18n
from . preferences import get_preferences
from . polling import app_minor_version
from . node_groups import set_node_input


#: Separates the descriptive half of a modifier name from its ASCII tag.
SEPARATOR = " — "

#: Optional custom property holding the English name. It only helps with
#: switching between two non-English languages; matching never relies on it,
#: because not every Blender version lets you write custom properties on a
#: modifier.
ND_KIND = "nd_kind"

#: Blender appends ".001" and friends when a name is already taken.
_NAME_SUFFIX = re.compile(r"\.[0-9]{3}$")


def base_name(name):
    """Modifier name without the duplicate suffix Blender adds."""
    return _NAME_SUFFIX.sub("", name)


def _stored_kind(mod):
    try:
        return mod[ND_KIND]
    except (KeyError, AttributeError, TypeError):
        return None


def _store_kind(mod, english_name):
    try:
        mod[ND_KIND] = english_name
        return True
    except (KeyError, AttributeError, TypeError):
        return False


def english_name(mod):
    """Best known English name of a modifier."""
    kind = _stored_kind(mod)
    return kind if kind else mod.name


def _prefix_variants(prefix):
    """The English prefix plus its translation in every language we ship.

    Matching therefore survives a language switch in either direction.
    """
    return i18n.variants(prefix)


def localized_modifier_name(name):
    """Translate the descriptive part of a modifier name, keep the ASCII tag.

    "Bevel — ND EB" becomes "倒角 — ND EB". Names without a separator are left
    alone: they are Blender's own modifiers or free text.
    """
    prefix, separator, tag = name.partition(SEPARATOR)
    if not separator:
        return name

    translated = i18n.t(prefix)
    if translated == prefix:
        return name

    return translated + separator + tag


def refresh_modifier_name(mod):
    """Re-apply the current language to one modifier. True when it changed."""
    wanted = localized_modifier_name(english_name(mod))

    # Compare without the duplicate suffix: a ".001" copy must not be
    # rewritten over and over, Blender would just renumber it again.
    if base_name(wanted) == base_name(mod.name):
        return False

    mod.name = wanted
    return True


def is_modifier(mod, wanted):
    """True when the modifier is the one ND calls ``wanted``.

    The tag is compared exactly, the prefix either as stored English or as its
    translation. That keeps the check working after a language switch, for
    modifiers made before the names became translatable, and for modifiers
    whose name the user has since edited.
    """
    have = base_name(mod.name)
    target = base_name(wanted)
    if have == target:
        return True

    p_have, s_have, t_have = have.partition(SEPARATOR)
    p_want, s_want, t_want = target.partition(SEPARATOR)
    if not s_have or not s_want or t_have != t_want:
        return False

    return p_have in _prefix_variants(p_want)


def has_tag(mod, tag):
    """True when the ASCII tag of the modifier is ``tag``, e.g. "ND EB"."""
    _, separator, t_have = base_name(mod.name).partition(SEPARATOR)
    return bool(separator) and t_have == tag


def modifier_ends_with(mod, suffix, strict=False):
    """The check behind remove_modifiers_ending_with, language aware.

    ``strict`` compares the name as-is instead of ignoring the ".001" suffix,
    but the prefix is still matched in any language.
    """
    have = mod.name if strict else base_name(mod.name)
    if have.endswith(suffix):
        return True

    p_have, s_have, t_have = have.partition(SEPARATOR)
    p_suffix, s_suffix, t_suffix = suffix.partition(SEPARATOR)
    if not s_have or not s_suffix or t_have != t_suffix:
        return False

    if not p_suffix:
        return True

    return p_have in _prefix_variants(p_suffix)


def modifier_starts_with(mod, prefix):
    """The check behind remove_modifiers_starting_with, language aware."""
    have = base_name(mod.name)
    if have.startswith(prefix):
        return True

    p_have = have.partition(SEPARATOR)[0]
    return any(p_have.startswith(v) for v in _prefix_variants(prefix))


def localize_scene_modifier_names():
    """Apply the current language to every modifier already in the file."""
    changed = 0
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if refresh_modifier_name(mod):
                changed += 1
    return changed


def rename_modifier(mod, english_name):
    """Give a modifier its ND name, translated when possible.

    The English name is always applied first, so the ASCII tag is in place
    before the prefix is translated.
    """
    mod.name = english_name
    _store_kind(mod, mod.name)

    localized = localized_modifier_name(english_name)
    if localized != english_name:
        mod.name = localized


def new_modifier(object, mod_name, mod_type, rectify=True):
    mod = object.modifiers.new(mod_name, mod_type)

    rename_modifier(mod, mod_name)

    mod.show_viewport = True
    mod.show_in_editmode = True
    mod.show_expanded = False

    show_cage_mods = ['DISPLACE']
    if mod_type in show_cage_mods:
        mod.show_on_cage = True

    if rectify:
        rectify_mod_order(object, mod.name)

    return mod


def move_mod_to_index(object, mod_name, index):
    if app_minor_version() < (4, 0):
        bpy.ops.object.modifier_move_to_index({'object': object}, modifier=mod_name, index=index)
    else:
        with bpy.context.temp_override(object=object):
            bpy.ops.object.modifier_move_to_index(modifier=mod_name, index=index)


def rectify_mod_order(object, mod_name):
    mods = list(object.modifiers)

    if len(mods) < 2:
        return

    matching_mod_index = None
    for index, mod in enumerate(mods):
        if is_modifier(mod, "Weighted Normal — ND WN"):
            matching_mod_index = index
            break

        if is_modifier(mod, "Weld — ND SW"):
            matching_mod_index = index
            break

        if is_modifier(mod, "Weld — ND B"):
            matching_mod_index = index
            break

        if is_modifier(mod, "Decimate — ND SD"):
            matching_mod_index = index
            break

        if mod.type == 'BEVEL' and mod.affect == 'EDGES' and mod.limit_method == 'ANGLE':
            if mod.segments > 1 or (mod.segments == 1 and mod.harden_normals):
                matching_mod_index = index
                break

    if matching_mod_index is None:
        return

    move_mod_to_index(object, mod_name, matching_mod_index)


def is_sba_mod(mod):
    if mod.type != 'NODES':
        return False

    if is_modifier(mod, "Smooth — ND SBA") or mod.name.startswith("Smooth by Angle"):
        return True

    if mod.node_group is not None and mod.node_group.name.startswith("Smooth by Angle"):
        return True

    return False


def get_sba_mod(object):
    for mod in object.modifiers:
        if is_sba_mod(mod):
            return mod

    return None


def has_sba_mod(object):
    return get_sba_mod(object) != None


def add_smooth_by_angle(context, object):
    if app_minor_version() < (4, 1):
        return

    if has_sba_mod(object):
        return

    with bpy.context.temp_override(object=object):
        sba_node_group = bpy.data.node_groups.get("Smooth by Angle")

        if sba_node_group == None and app_minor_version() == (4, 1):
            bpy.ops.object.shade_smooth()
            bpy.ops.object.modifier_add_node_group(asset_library_type='ESSENTIALS', asset_library_identifier="",
                    relative_asset_identifier="geometry_nodes\\smooth_by_angle.blend\\NodeTree\\Smooth by Angle")

        if sba_node_group == None and app_minor_version() > (4, 1):
            bpy.ops.object.shade_auto_smooth()

        sba_mod = None

        if sba_node_group != None:
            sba_mod = object.modifiers.new("Smooth — ND SBA", 'NODES')
            _store_kind(sba_mod, sba_mod.name)
            sba_mod.node_group = sba_node_group
            if app_minor_version() > (4, 1):
                sba_mod.use_pin_to_last = True
            if app_minor_version() >= (4, 1):
                sba_mod.show_group_selector = False

        # It isn't pretty, but it's the only way to get the modifier as modifier_add_node_group/shade_auto_smooth
        # runs asynchronously which doesn't guarantee the modifier is ready before the next chunk of code.
        # This is a temporary solution until Blender provides a way to check if the modifier is ready.
        count = 0
        while sba_mod is None and count < 25:
            sba_mod = get_sba_mod(object)
            if sba_mod != None:
                break
            object.data.update()
            count += 1

        # If the modifier is still None, give up.
        if sba_mod == None:
            return

        rename_modifier(sba_mod, "Smooth — ND SBA")
        set_smoothing_angle(context, object, radians(float(get_preferences().default_smoothing_angle)), True)

        ensure_tail_mod_consistency(object, force=True)


def set_smoothing_angle(context, object, angle, ignore_sharpness=False):
    mod = get_sba_mod(object)

    if mod is None:
        return

    set_node_input(mod, "Input_1", angle)
    set_node_input(mod, "Socket_1", ignore_sharpness)

    mod.node_group.interface_update(context)
    object.data.update()


def ensure_tail_mod_consistency(object, force=False):
    # For Blender 4.1.0 and above, the smoothing and weighted normal
    # modifiers are pinned at the end of the stack by ND.
    if force == False and app_minor_version() > (4, 1):
        return

    mod_order = ['Smooth by Angle', 'Smooth — ND SBA', 'Weighted Normal — ND WN', 'Triangulate — ND']
    object_mods = list(object.modifiers)

    for wanted in mod_order:
        mod_name = None
        for mod in object_mods:
            if is_modifier(mod, wanted):
                mod_name = mod.name
                break
        if mod_name is None:
            continue

        if app_minor_version() < (4, 0):
            bpy.ops.object.modifier_move_to_index({'object': object}, modifier=mod_name, index=len(object_mods) - 1)
        else:
            with bpy.context.temp_override(object=object):
                bpy.ops.object.modifier_move_to_index(modifier=mod_name, index=len(object_mods) - 1)


def remove_problematic_boolean_mods(object):
    mods = [mod for mod in object.modifiers]
    remove_mods = []

    for mod in mods:
        if is_modifier(mod, "Weighted Normal — ND WN"):
            remove_mods.append(mod)
            continue

        if is_modifier(mod, "Triangulate — ND"):
            remove_mods.append(mod)
            continue

        if mod.type == 'BEVEL' and mod.affect == 'EDGES' and mod.limit_method == 'ANGLE':
            if mod.segments > 1 or (mod.segments == 1 and mod.harden_normals):
                remove_mods.append(mod)
                continue

    for mod in remove_mods:
        object.modifiers.remove(mod)


def remove_modifiers_ending_with(objects, suffix, strict=False):
    for object in objects:
        for mod in list(object.modifiers):
            mod_name = mod.name
            if modifier_ends_with(mod, suffix, strict):
                if app_minor_version() < (4, 0):
                    bpy.ops.object.modifier_remove({'object': object}, modifier=mod_name)
                else:
                    with bpy.context.temp_override(object=object):
                        bpy.ops.object.modifier_remove(modifier=mod_name)


def remove_modifiers_starting_with(objects, suffix):
    for object in objects:
        for mod in list(object.modifiers):
            mod_name = mod.name
            if modifier_starts_with(mod, suffix):
                if app_minor_version() < (4, 0):
                    bpy.ops.object.modifier_remove({'object': object}, modifier=mod_name)
                else:
                    with bpy.context.temp_override(object=object):
                        bpy.ops.object.modifier_remove(modifier=mod_name)
