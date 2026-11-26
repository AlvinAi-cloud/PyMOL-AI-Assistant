"""Offline help text shared by the AI Assistant and Presets help menus."""
from html import escape

from .graphics import HELP, PALETTES, PRESETS
from .focus import FOCUS_HELP


def _paragraph(title, text):
    return "<p><b>" + escape(title) + ".</b> " + escape(text) + "</p>"


def _preset_guide():
    sections = [
        "<h2>Presets, options and polymer colors</h2>",
        "<p>Open <b>Presets</b> in the menu bar, or use the <b>Presets</b> button "
        "beneath Builder/Properties. Choose a lighting preset first, then adjust "
        "the independent options. Hover over a menu entry for a short explanation.</p>",
        "<p>Lighting presets keep molecular colors, coordinates, camera orientation "
        "and representations. They do not turn a cartoon into a surface or select "
        "a ligand for you. <b>Publication</b> selects a white background; the other "
        "presets keep the current background.</p>",
        "<h3>Combinations to try</h3>"
        "<ul>"
        "<li><b>Ligand or pocket.</b> Choose <b>Soft</b>, select any residues to emphasize, "
        "then choose <b>Transparent protein + highlights</b>. Use Ray to check how clearly "
        "the sticks show through the protein. Silhouettes can compete with small details.</li>"
        "<li><b>Chain diagram.</b> Use <b>Paper Cutout</b>, choose <b>Pastel chains</b> if "
        "you want new colors, and select <b>White</b> or <b>Transparent PNG</b>. "
        "<b>Illustration</b> gives a flatter diagram with darker contours.</li>"
        "<li><b>Matching figure panels.</b> Start with <b>Publication</b> and choose "
        "<b>Orthographic</b>. Keep the same camera and zoom across panels. "
        "Use <b>High</b> render quality for the final exports.</li>"
        "<li><b>Sculpted surface.</b> Show the protein as a surface and apply <b>Studio</b>. "
        "Choose <b>Soft</b> for subtler highlights and crevice shading.</li>"
        "</ul>",
        "<h3>" + str(len(PRESETS)) + " lighting presets</h3>",
    ]
    for label, description, _settings in PRESETS.values():
        sections.append(_paragraph(label, description))
    sections.append("<h3>Independent options</h3>")
    for key, label in [
        ("shadows", "Shadows (Ray)"),
        ("silhouettes", "Silhouettes (Ray)"),
        ("depth_cue", "Depth cue"),
        ("surface_depth", "Surface depth (AO)"),
        ("background", "Background"),
        ("material", "Material"),
        ("outline_strength", "Outline strength (Ray)"),
        ("outline_color", "Outline color (Ray)"),
        ("projection", "Projection"),
        ("quality", "Render quality (Ray)"),
    ]:
        sections.append(_paragraph(label, HELP[key]))
    sections.extend([
        "<h3>Translucent protein focus</h3>",
        _paragraph("Highlight a ligand or selected residues", FOCUS_HELP),
        "<p>This is an explicit <b>representation change</b>, separate from the "
        "eight lighting presets. Choose <b>Presets &gt; Transparent protein + highlights</b> "
        "to highlight organic ligands in enabled objects. Select one or more protein residues "
        "first to highlight them as well. Selecting even one atom of a protein residue highlights that "
        "whole residue. Solvent is excluded from the focus.</p>",
        "<p>The protein becomes a translucent cartoon; any protein surface "
        "patches that were already visible remain visible with the same "
        "transparency. The ligands and any selected protein residues become opaque "
        "sticks. Other nonprotein atoms keep their existing display. "
        "The selected lighting preset and atom colors are retained.</p>",
        "<p>Adjust the view, then choose Ray to inspect the final transparency. "
        "The highlighted residue's cartoon remains translucent; its sticks "
        "provide the opaque focus. To reverse the representation changes, "
        "ask the AI to restore its checkpoint or reload a saved session.</p>",
    ])
    sections.extend([
        "<h3>Optional polymer colors</h3>",
        "<p><b>Polymer colors</b> is a separate recoloring action, not part of a "
        "lighting preset. The menu applies a palette to all loaded polymers. "
        "The AI can apply one to a specific polymer selection when you ask.</p>",
    ])
    for label, description in PALETTES.values():
        sections.append(_paragraph(label, description))
    sections.extend([
        "<p>Ligands, solvent and other nonpolymer atoms retain their colors. "
        "Representation-specific color overrides can hide atom coloring. "
        "Palettes are decorative: they do not measure confidence, B-factor or "
        "hydrophobicity.</p>",
        _paragraph("Reset graphics", HELP["reset"]),
        "<p>To reverse palette coloring, ask the AI to restore the most recent "
        "relevant checkpoint, or reload a session saved before recoloring. "
        "Reset graphics keeps the current atom colors.</p>",
        "<h3>Try asking the AI</h3>",
        "<ul>"
        "<li>Use Paper Cutout with fine charcoal outlines and a white background.</li>"
        "<li>Use Studio lighting with surface depth enabled.</li>"
        "<li>Recolor the polymer chains with the pastel palette; keep ligand colors.</li>"
        "<li>Use orthographic projection and High render quality for this figure.</li>"
        "<li>Make the protein translucent and show my selected residues as opaque sticks.</li>"
        "</ul>",
    ])
    return "".join(sections)


HELP_PAGES = {
    "assistant_start": (
        "Getting started with AI Assistant",
        "<h2>Getting started with AI Assistant</h2>"
        "<p>The assistant works with the molecular scene in this PyMOL window. "
        "Ordinary PyMOL tools, presets and this help remain available without an "
        "AI connection.</p>"
        "<ol>"
        "<li><b>Load a structure.</b> Use File &gt; Open, or click <b>Example</b> "
        "in the assistant panel to load the bundled tutorial structure.</li>"
        "<li><b>Connect a model.</b> Open <b>Accounts…</b> in the panel or "
        "<b>AI Assistant &gt; Accounts and Models…</b>. Choose an API provider "
        "and enter your own key, or choose a compatible/local API endpoint. "
        "The ChatGPT account tab offers browser sign-in for an eligible account.</li>"
        "<li><b>Choose the model.</b> Refresh the available models or enter a "
        "model ID, then use the selected model. A vision-capable model is needed "
        "for requests that examine images of the window.</li>"
        "<li><b>Describe a task and press Send.</b> Be specific about the loaded "
        "object, chain, selection, desired appearance or output file.</li>"
        "</ol>"
        "<p><b>Test connection</b> sends a small model request and may use provider "
        "quota. API charges and account eligibility depend on your chosen provider. "
        "The Remember option saves the connection for this app; it does not "
        "import another application's account.</p>"
        "<h3>Examples</h3>"
        "<ul>"
        "<li>Show the protein as a cartoon and its ligand as sticks.</li>"
        "<li>Examine the current view and suggest how to make the ligand clearer.</li>"
        "<li>Read the sequence of the current selection.</li>"
        "<li>Apply Soft lighting and a white background, keeping my colors.</li>"
        "</ul>"
        "<p>The assistant runs supported PyMOL operations automatically, reads "
        "their actual results and can continue with another step. Watch the "
        "conversation and the commands/results area below the input.</p>"
        "<p><b>Clear</b> clears the conversation; it does not clear the molecular "
        "scene. Use <b>AI Assistant</b> in the menu bar to show the panel again "
        "if you close or hide it.</p>",
    ),
    "assistant_capabilities": (
        "AI capabilities, results and recovery",
        "<h2>AI capabilities, results and recovery</h2>"
        "<h3>Operate PyMOL</h3>"
        "<p>The assistant can change representations, colors and selections; "
        "orient and zoom; run measurements and alignments; apply named presets "
        "and options; and use supported PyMOL command-line operations for loading, "
        "saving and image export. Give exact object or selection names where "
        "possible, and provide the intended local file path for file operations.</p>"
        "<p>Normal molecular commands are available to the AI. Arbitrary Python "
        "and shell scripts are not exposed as AI command tools.</p>"
        "<h3>Examine the window or read sequences</h3>"
        "<p>The assistant can request an actual image of the molecular viewport "
        "or this PyMOL window when useful. Image requests need a vision-capable "
        "model. It can also extract FASTA directly from loaded polymer atoms "
        "for a requested selection. Unresolved residues absent from the loaded "
        "structure may be missing from that sequence.</p>"
        "<p>Images and sequences are requested on demand, rather than attached "
        "to every message. When requested, they are sent to the connected model "
        "as part of the task.</p>"
        "<h3>Read results</h3>"
        "<p>The commands/results area shows the operations, actual console "
        "output, returned values and errors as the assistant works. If something "
        "fails, describe the problem or refer to that error in your next message. "
        "Ask the assistant to inspect a fresh view after important visual changes.</p>"
        "<h3>Stop or recover</h3>"
        "<p>Use <b>Cancel</b> to stop further work after the current command. "
        "Operations already completed remain applied. Save a PyMOL session "
        "before major edits if you want a durable copy of the starting scene.</p>"
        "<p>Before a changing assistant turn, the app creates a scene checkpoint. "
        "You can ask <i>Undo your last changes</i> or <i>Restore the checkpoint</i>. "
        "This restores the scene saved before that changing turn, which may "
        "contain several commands. A limited recent checkpoint history is kept; "
        "this is not an unlimited history of every action.</p>"
        "<p>A checkpoint cannot reverse external effects such as an overwritten "
        "exported file or a downloaded file. It also does not guarantee recovery "
        "of unrelated manual edits. <b>Reset graphics</b> resets lighting and "
        "background; it is not an undo command.</p>",
    ),
    "presets_guide": ("Presets, options and polymer colors", _preset_guide()),
    "rendering_guide": (
        "Draw, Ray and image export",
        "<h2>Draw, Ray and image export</h2>"
        "<h3>Which view am I looking at?</h3>"
        "<p>The interactive molecular view updates while you rotate and zoom. "
        "It is useful for positioning the scene and checking colors and "
        "representations. <b>Draw</b> uses the graphics view for a fast image. "
        "<b>Ray</b> computes the final rendered appearance, including contours "
        "and cast shadows.</p>"
        "<h3>Quick rendered preview</h3>"
        "<ol>"
        "<li>Arrange the scene and choose a lighting preset.</li>"
        "<li>Adjust independent options if needed. To see outline strength or "
        "outline color, enable <b>Silhouettes</b>.</li>"
        "<li>Choose <b>Presets &gt; Render preview (Ray)</b>. This renders the "
        "current view up to 900 pixels wide. Rotating returns to the interactive view.</li>"
        "</ol>"
        "<p>Use Ray to judge final shadows, outlines, surface depth and edge "
        "smoothing. After changing a setting, render again to refresh a previous "
        "Ray image. Some effects are subtle on cartoons and stronger on surfaces.</p>"
        "<h3>Final image</h3>"
        "<p>Open PyMOL's <b>Draw/Ray</b> controls, choose the output dimensions "
        "and choose <b>Ray</b>. Use PyMOL's existing <b>Export image as</b> menu "
        "to save the image. Ask the AI to export a PNG if you prefer, giving "
        "the desired path and dimensions.</p>"
        "<p><b>Render quality &gt; High</b> samples the Ray image more densely for smoother "
        "edges. High and Silhouettes both increase the time and memory required. "
        "Use <b>Standard</b> for quicker previews and set the export dimensions separately.</p>"
        "<h3>White or transparent backgrounds</h3>"
        "<p>Choose <b>Background &gt; White</b> for an opaque figure background, "
        "or <b>Background &gt; Transparent PNG</b> for an alpha channel that can "
        "be placed over another background. The interactive view remains white "
        "with the transparent option; a Ray preview may show a checkerboard. "
        "Check the saved PNG in an application that displays transparency.</p>"
        "<h3>Reset and compare</h3>"
        + _paragraph("Reset graphics", HELP["reset"])
        + "<p>For a fair comparison of lighting presets, keep the same camera, "
        "representations and colors. Choose a preset first and then apply "
        "independent options, since another preset replaces its lighting and "
        "outline settings. Palette coloring is a separate action and remains "
        "until recolored, recovered from a checkpoint or reloaded.</p>",
    ),
}
