"""Explicit translucent-protein focus view, independent of lighting and colors."""
import math
import re


FOCUS_HELP = (
    "Make enabled protein cartoons 70% transparent and show enabled organic ligands plus "
    "any actively selected protein residues as opaque sticks. Existing protein surface patches remain "
    "visible with the same transparency. Ligand spheres and surfaces give way to sticks "
    "so the bonds remain visible. Keeps molecular colors, coordinates, "
    "camera and lighting; changes protein representations. Select internal "
    "protein residues first if you want to highlight them as well. Use Ray for the final "
    "transparent appearance. Try Soft lighting or turn off Silhouettes if dark outlines "
    "obscure small ligand details. Ask the AI to restore its checkpoint to undo the view."
)


def default_focus_selection(cmd):
    """Use enabled organic ligands and the active mouse selection."""
    selection = "organic"
    if "sele" in cmd.get_names("selections", enabled_only=1):
        selection += " or (%sele and polymer.protein)"
    return "enabled and (" + selection + ")"


def _enabled_scope(cmd):
    # The atom selector "enabled" ignores parent-group visibility. A %group
    # selection includes all its descendants, even for disabled groups.
    groups = set(cmd.get_names("group_objects"))
    disabled_groups = groups.difference(cmd.get_names("group_objects", enabled_only=1))
    if not disabled_groups:
        return "enabled"

    wildcard = cmd.get("wildcard")
    for name in disabled_groups:
        if not re.fullmatch(r"[A-Za-z0-9_.+^\-]+", name) or (wildcard and wildcard[0] in name):
            raise ValueError("Rename the disabled group with a plain name before applying the focus view.")
    group_selection = " or ".join("%" + name for name in sorted(disabled_groups))
    return f"(enabled and not ({group_selection}))"


def _focus_selections(cmd, selection):
    if not isinstance(selection, str) or not selection.strip():
        raise ValueError("Select a ligand or protein residue to highlight.")
    scope = _enabled_scope(cmd)
    protein = f"({scope} and polymer.protein)"
    if not cmd.count_atoms(protein):
        raise ValueError("Load and enable a protein before applying the translucent focus view.")
    highlights = f"({scope} and (organic or polymer.protein) and not solvent)"
    target = f"(byres (({selection.strip()}) and {highlights})) and {highlights}"
    try:
        count = cmd.count_atoms(target)
    except Exception:
        raise ValueError("Choose a valid ligand or protein-residue selection.") from None
    if not count:
        raise ValueError("Select an organic ligand or protein residue in an enabled object to highlight.")
    return protein, target


def focus_target(cmd, selection):
    """Validate without mutations and return the whole-residue highlight selection."""
    return _focus_selections(cmd, selection)[1]


def apply_focus(cmd, selection, transparency=.70):
    """Show a translucent protein scaffold with opaque whole-residue focus sticks."""
    if isinstance(transparency, bool) or not isinstance(transparency, (int, float)) or not math.isfinite(transparency) or not 0 <= transparency <= 1:
        raise ValueError("Protein transparency must be a number between 0 and 1.")
    protein, target = _focus_selections(cmd, selection)
    protein_atoms = cmd.count_atoms(protein)
    highlighted_atoms = cmd.count_atoms(target)
    surface = protein + " and rep surface"
    surface_atoms = cmd.count_atoms(surface)
    temporary_surface = None
    try:
        # Capture an existing surface subset before hiding representations. A
        # temporary disabled selection avoids assuming anything about object names.
        if surface_atoms:
            temporary_surface = cmd.get_unused_name("_pymol_ai_focus_surface")
            cmd.select(temporary_surface, surface, enable=0, quiet=1)
        cmd.hide("everything", protein)
        cmd.show("cartoon", protein)
        cmd.set("cartoon_transparency", float(transparency), protein)
        if temporary_surface:
            cmd.show("surface", temporary_surface)
            cmd.set("transparency", float(transparency), protein)
        ligand = f"({target}) and organic and not polymer"
        # Opaque ligand shells can cover the sticks that the focus view adds.
        for representation in ("spheres", "surface", "mesh", "dots"):
            cmd.hide(representation, ligand)
        cmd.show("sticks", target)
        cmd.set("stick_transparency", 0, target)
        cmd.set("stick_radius", .22, target)
    finally:
        if temporary_surface:
            cmd.delete(temporary_surface)
    return {
        "selection": selection,
        "proteinAtoms": protein_atoms,
        "highlightedAtoms": highlighted_atoms,
        "proteinTransparency": float(transparency),
        "retainedSurfaceAtoms": surface_atoms,
        "note": (
            "Enabled protein representations changed to a translucent cartoon, retaining "
            "any previously visible protein surface subset. Highlighted whole "
            "residues or organic ligand are opaque sticks. Molecular colors, "
            "coordinates, camera and lighting were retained. Other nonprotein "
            "atoms were left unchanged. Use Ray for the final transparent appearance."
        ),
    }
