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

from .. lib.preferences import get_preferences
from .. import i18n


# Icon-only buttons: an empty label that is not a translatable message id.
ICON_ONLY = ""


def create_box(text, layout, props, prop_name, icons, shortcuts):
    box = layout.box()
    row = box.row(align=True)

    prop_active = getattr(props, prop_name)

    row.prop(props, prop_name,
        icon="TRIA_DOWN" if prop_active else "TRIA_RIGHT", icon_only=True, emboss=False
    )

    # Drawn by the add-on, not by Blender: the catalogue does not reach it.
    row.label(text=i18n.t(text))

    for op, mode in shortcuts:
        if mode:
            row.operator(op, icon=icons[f'{op}+{mode}'], text=ICON_ONLY).mode = mode
        else:
            row.operator(op, icon=icons[op], text=ICON_ONLY)

    if prop_active:
        return box.column()
    else:
        return None


def render_ops(ops, layout, new_row=True, use_separator=False):
    for op in ops:
        if op is None:
            if use_separator:
                layout.separator()
            continue

        op, icon, label, mode, experimental = op

        if experimental and not get_preferences().enable_experimental_features:
            continue

        if new_row:
            row = layout.row(align=True)
            row.scale_y = 1.2
        else:
            row = layout

        # A custom label bypasses the operator's own (translated) bl_label, so
        # it has to be translated here.
        if label:
            label = i18n.t(label)

        if mode:
            row.operator(op, icon=icon, text=label).mode = mode
        else:
            row.operator(op, icon=icon, text=label)
