"""Shared, deterministic graphics controls for the menus and AI tools."""

BASE = {
    'ambient': .35, 'direct': .65, 'reflect': .18, 'specular': .22,
    'shininess': 35, 'light_count': 2, 'ray_shadows': 0,
    'ambient_occlusion_mode': 0, 'ambient_occlusion_scale': 14,
    'ambient_occlusion_smooth': 10, 'ray_trace_mode': 0,
    'ray_trace_gain': .045, 'ray_trace_color': 'black',
    'depth_cue': 0, 'ray_trace_fog': 0, 'fog_start': .6,
    'ray_shadow_decay_factor': 0,
}
PRESETS = {
    'simple': ('Simple', 'Balanced lighting with modest highlights, no cast shadows and no outlines. A good starting point for everyday viewing. Visible in the interactive view; choose Ray in Draw/Ray for a final rendered image.', {}),
    'soft': ('Soft', 'Matte shading with darker surface crevices (ambient occlusion). Useful for molecular surfaces, pockets and grooves; the difference is less pronounced on cartoons. Choose Ray in Draw/Ray to check the final shading.', {
        'ambient': .68, 'direct': .25, 'reflect': .08, 'specular': .05,
        'light_count': 5, 'ambient_occlusion_mode': 2}),
    'full': ('Full', 'Directional shadows, surface ambient occlusion and highlights give stronger depth. Useful for overlapping parts, assemblies and surfaces. Choose Ray in Draw/Ray to see the shadows; large surfaces can take longer to render.', {
        'specular': .3, 'ray_shadows': 1, 'light_count': 3, 'ambient_occlusion_mode': 2}),
    'flat': ('Flat', 'Uniform colors with almost no lighting-based shading. Useful for diagrams, but depth can be hard to read. Try enabling Silhouettes; choose Ray in Draw/Ray to see those outlines.', {
        'ambient': 1, 'direct': 0, 'reflect': 0, 'specular': 0}),
    'publication': ('Publication', 'Gentle lighting, restrained highlights and fine outlines on a white background. A starting point for papers and reports; keeps molecular colors. Choose Ray in Draw/Ray to see the outlines before exporting.', {
        'ambient': .52, 'direct': .4, 'reflect': .1, 'specular': .12,
        'ray_trace_mode': 1, 'ray_trace_gain': .025, 'ray_trace_color': '0x334455'}),
    'illustration': ('Illustration', 'Flat colors with dark outlines for explanatory diagrams. Keeps molecular colors and the current background, making colored chains or domains easy to distinguish. Choose Ray in Draw/Ray to see the outlines.', {
        'ambient': 1, 'direct': 0, 'reflect': 0, 'specular': 0,
        'ray_trace_mode': 1, 'ray_trace_gain': .04}),
    'paper_cutout': ('Paper Cutout', 'Matte colors, charcoal contours and a little directional shading give a layered paper appearance. Useful for cartoons and chain diagrams; less flat than Illustration. Keeps colors, background and representations. Choose Ray in Draw/Ray for the contours; try an optional polymer palette afterwards.', {
        'ambient': .72, 'direct': .28, 'reflect': .04, 'specular': 0,
        'light_count': 3, 'ray_trace_mode': 1, 'ray_trace_gain': .035,
        'ray_trace_color': '0x3D4148'}),
    'studio': ('Studio', 'A stronger directional light with polished highlights and surface depth gives rounded shapes a sculpted appearance. Useful for surfaces and ligand sticks, especially on a light background. Keeps molecular colors and representations. Choose Ray in Draw/Ray to see the shadows and final shading.', {
        'ambient': .18, 'direct': .85, 'reflect': .25, 'specular': .4,
        'shininess': 65, 'light_count': 2, 'ray_shadows': 1,
        'ambient_occlusion_mode': 2, 'ambient_occlusion_scale': 10}),
}
OUTLINE_STRENGTH = {'fine': .020, 'standard': .045, 'bold': .075}
OUTLINE_COLORS = {'charcoal': '0x3D4148', 'black': 'black', 'gray': '0x777777'}
PALETTES = {
    'pastel_chains': ('Pastel chains', 'Explicitly recolor all loaded polymer chains with a muted, decorative palette. Each object/segment/chain is treated separately; colors repeat after six chains. Ligands, solvent and other nonpolymer atoms retain their colors. This is categorical coloring, not a molecular measurement.'),
    'contrast_chains': ('Contrast chains', 'Explicitly recolor all loaded polymer chains with stronger, distinct colors for presentations and crowded assemblies. Colors repeat after six chains; keep chain labels for identification. Ligands and solvent retain their colors. This palette does not encode confidence or a molecular property.'),
    'residue_gradient': ('Residue gradient', 'Explicitly recolor all loaded polymers from teal through cream to amber in stored residue order, restarting for each object/segment/chain. Useful for following a fold. Ligands and solvent retain their colors. Missing residues are not filled in; this is not confidence, B-factor or hydrophobicity coloring.'),
}
# Independently chosen colors. Palette application is a separate opt-in action.
CHAIN_COLORS = {
    'pastel_chains': [(0.48, .72, .76), (.88, .66, .48), (.65, .61, .80),
                      (.73, .78, .49), (.85, .59, .68), (.53, .72, .56)],
    'contrast_chains': [(.12, .48, .65), (.83, .37, .16), (.52, .33, .68),
                       (.29, .60, .31), (.76, .31, .49), (.66, .55, .15)],
}
HELP = {
    'shadows': 'Cast directional shadows to separate overlapping molecular parts. This effect appears in Ray renders, not the ordinary interactive view. Choose Ray in Draw/Ray, or Render preview (Ray) after changing it.',
    'silhouettes': 'Add dark outlines to clarify molecular boundaries, especially with Flat lighting. Outlines appear in Ray renders, not the ordinary interactive view. Choose Ray in Draw/Ray, or Render preview (Ray) to see them.',
    'depth_cue': 'Gently fade distant parts toward the background to distinguish front from back. Affects the interactive view and Ray renders. Disable it if important distant features become too faint.',
    'surface_depth': 'Use ambient occlusion to darken crevices and help overlapping surfaces read in depth. Most useful on curved molecular surfaces; flat lighting can make it subtle. Independent of cast shadows. Choose Ray in Draw/Ray to assess the final effect.',
    'outline_strength': 'Tune contour emphasis independently of lighting. These are relative outline strengths, not fixed pixel widths; the result depends on shape and image resolution. Enable Silhouettes and choose Ray in Draw/Ray to see them.',
    'outline_strength_fine': 'Use restrained contours for dense figures and small details. This changes outline strength, not exact line width. Enable Silhouettes and choose Ray in Draw/Ray to see the outlines.',
    'outline_strength_standard': 'Use medium contour emphasis for everyday molecular diagrams. Enable Silhouettes and choose Ray in Draw/Ray; the visible thickness depends on molecular shape and export size.',
    'outline_strength_bold': 'Use stronger contour emphasis for simplified cartoons and slides. Bold contours can hide small details. Enable Silhouettes and choose Ray in Draw/Ray to inspect the result.',
    'outline_color': 'Set the contour color without recoloring molecular atoms. Charcoal is softer than black; gray is more subdued. Enable Silhouettes and choose Ray in Draw/Ray to see the color.',
    'outline_color_charcoal': 'Use dark charcoal contours for a softer paper-like boundary. Does not change molecular colors. Enable Silhouettes and choose Ray in Draw/Ray to see the contours.',
    'outline_color_black': 'Use black contours for maximum contrast, especially on white or transparent backgrounds. Does not recolor atoms. Enable Silhouettes and choose Ray in Draw/Ray.',
    'outline_color_gray': 'Use gray contours to reduce heavy borders in pale figures. They may be faint on gray backgrounds. Enable Silhouettes and choose Ray in Draw/Ray to check contrast.',
    'projection': 'Choose how depth is projected onto the image. Orthographic avoids perspective scaling; Perspective makes nearer parts look larger. This intentionally changes projection while retaining the camera orientation, atom positions and representations.',
    'projection_orthographic': 'Use parallel projection so depth does not make nearer parts appear larger. Useful for consistent figure panels. Changes projection only; it does not align structures or change molecular coordinates.',
    'projection_perspective': 'Use perspective so nearer parts appear larger, giving a stronger sense of depth. Useful for presentations. Changes projection only; it does not change molecular coordinates.',
    'quality': 'Choose Ray edge smoothing independently of lighting. Standard suits quick renders and High uses more samples for smoother final images. Silhouettes also increase sampling. The output dimensions stay the same.',
    'quality_standard': 'Use adaptive antialiasing for faster Ray previews and ordinary exports. Does not change molecular geometry, output dimensions or representation choices. Choose Ray in Draw/Ray to refresh the rendered image.',
    'quality_high': 'Use more samples to smooth Ray edges in final figures. This uses more memory and render time, especially with Silhouettes. Set the output dimensions separately in Draw/Ray.',
    'palettes': 'Optional decorative coloring, separate from lighting presets. These actions recolor all loaded polymers, preserving ligand and solvent colors. Presets and Reset graphics do not restore prior colors; ask the AI to undo the coloring, or reload your saved session.',
    'background': 'Choose a white, black or transparent background. These choices replace any existing background gradient or image. Transparent PNGs contain an alpha channel and use white in the interactive view.',
    'background_white': 'Use an opaque white background, useful for papers, reports and light slides. Applies to the interactive view and rendered images; PNG exports are opaque.',
    'background_black': 'Use an opaque black background, useful for dark slides and emphasizing bright molecular colors. Applies to the interactive view and rendered images; PNG exports are opaque.',
    'background_transparent': 'Export a transparent PNG for placement over another background in slides or figures. The interactive view remains white; a Ray preview may show a checkerboard. Choose Ray in Draw/Ray and use the normal PNG export controls.',
    'material': 'Adjust shiny highlights independently of the lighting preset. Matte removes reflections; Glossy strengthens them. Choose a preset first, then adjust the material.',
    'material_matte': 'Remove shiny highlights and reflections while retaining the chosen lighting. Useful for readable molecular surfaces and illustrations. Choose Ray in Draw/Ray to inspect the final appearance.',
    'material_glossy': 'Strengthen shiny highlights and reflections to emphasize curvature. Useful for a polished 3D appearance; strong highlights can distract in dense figures. Choose Ray in Draw/Ray to inspect the final appearance.',
    'render_preview': 'Ray-render the current view up to 900 pixels wide to see shadows and silhouettes. Rotating returns to the interactive view. Use the normal Draw/Ray and export controls for the final image at your chosen resolution.',
    'reset': 'Return to Simple lighting and a white background. Keeps the camera, projection, edge-smoothing quality, representations and current molecular colors; it does not reverse palette coloring or other scene edits. Choose Ray in Draw/Ray to refresh a rendered image.',
    'button': 'Choose a graphics preset and independent options. Hover over each entry for an explanation. Select a preset first, then adjust options. Shadows and silhouettes require Ray in Draw/Ray or Render preview (Ray).',
}
OPTION_VALUES = {
    'shadows': [False, True], 'silhouettes': [False, True],
    'background': ['white', 'black', 'transparent'],
    'material': ['matte', 'glossy'], 'depth_cue': [False, True],
    'surface_depth': [False, True],
    'outline_strength': list(OUTLINE_STRENGTH), 'outline_color': list(OUTLINE_COLORS),
    'projection': ['orthographic', 'perspective'], 'quality': ['standard', 'high'],
}
RENDER_NOTE = 'Use Ray for final shadows, contours and edge smoothing. Use Ray with Transparent PNG to export a transparent background.'


class GraphicsControls:
    def __init__(self, cmd):
        self.cmd = cmd

    def validate_preset(self, name):
        if not isinstance(name, str) or name not in PRESETS:
            raise ValueError('Choose a graphics preset: ' + ', '.join(PRESETS))

    @staticmethod
    def validate_options(options):
        if not isinstance(options, dict) or not options or set(options) - set(OPTION_VALUES):
            raise ValueError('Choose one or more supported graphics options: ' + ', '.join(OPTION_VALUES))
        for key, value in options.items():
            if key in {'shadows', 'silhouettes', 'depth_cue', 'surface_depth'}:
                if type(value) is not bool:
                    raise ValueError(key + ' must be true or false.')
            elif not isinstance(value, str) or value not in OPTION_VALUES[key]:
                raise ValueError(key + ' must be one of: ' + ', '.join(OPTION_VALUES[key]))

    def apply_preset(self, name):
        self.validate_preset(name)
        settings = dict(BASE)
        settings.update(PRESETS[name][2])
        for key, value in settings.items():
            self.cmd.set(key, value)
        if name == 'publication':
            self.set_options({'background': 'white'})
        return {'preset': name, 'label': PRESETS[name][0],
                'current': self.state(), 'renderNote': RENDER_NOTE}

    def set_options(self, options):
        self.validate_options(options)
        for key, value in options.items():
            if key == 'shadows':
                self.cmd.set('ray_shadows', int(value))
            elif key == 'silhouettes':
                self.cmd.set('ray_trace_mode', 1 if value else 0)
            elif key == 'background':
                self.cmd.set('bg_image_filename', '')
                self.cmd.set('bg_gradient', 0)
                self.cmd.bg_color('white' if value == 'transparent' else value)
                self.cmd.set('opaque_background', 1)
                self.cmd.set('ray_opaque_background', 0 if value == 'transparent' else 1)
            elif key == 'material':
                for setting, number in ({'specular': 0, 'reflect': 0, 'shininess': 20} if value == 'matte'
                                        else {'specular': .7, 'reflect': .35, 'shininess': 55}).items():
                    self.cmd.set(setting, number)
            elif key == 'depth_cue':
                self.cmd.set('depth_cue', int(value))
                self.cmd.set('ray_trace_fog', 1 if value else 0)
                self.cmd.set('fog_start', .6)
            elif key == 'surface_depth':
                self.cmd.set('ambient_occlusion_mode', 2 if value else 0)
            elif key == 'outline_strength':
                self.cmd.set('ray_trace_gain', OUTLINE_STRENGTH[value])
            elif key == 'outline_color':
                self.cmd.set('ray_trace_color', OUTLINE_COLORS[value])
            elif key == 'projection':
                self.cmd.set('orthoscopic', int(value == 'orthographic'))
                self.cmd.set('ray_orthoscopic', -1)
            elif key == 'quality':
                self.cmd.set('antialias', 2 if value == 'high' else 1)
        return {'optionsApplied': dict(options), 'current': self.state(), 'renderNote': RENDER_NOTE}

    def validate_palette(self, palette, selection):
        if not isinstance(palette, str) or palette not in PALETTES:
            raise ValueError('Choose a polymer palette: ' + ', '.join(PALETTES))
        target = '(' + selection + ') and polymer'
        if not self.cmd.count_atoms(target):
            raise ValueError('The selection contains no polymer atoms to recolor.')
        return target

    def apply_palette(self, palette, selection):
        target = self.validate_palette(palette, selection)
        rows = []
        self.cmd.iterate(target, 'rows.append((model, segi, chain, resi, index))', space={'rows': rows})
        chains = sorted({row[:3] for row in rows})
        if palette in CHAIN_COLORS:
            colors = {}
            for number, chain in enumerate(chains):
                name = 'pymol_ai_' + palette + '_' + str(number % 6)
                self.cmd.set_color(name, CHAIN_COLORS[palette][number % 6])
                colors[chain] = self.cmd.get_color_index(name)
            mapping = {(model, index): colors[(model, segi, chain)] for model, segi, chain, resi, index in rows}
        else:
            # Residue order is taken from the loaded atoms; gaps are not inferred.
            residues = {}
            for model, segment, chain, resi, _index in rows:
                residues.setdefault((model, segment, chain), {}).setdefault(resi, None)
            residue_colors = {}
            color_indices = {}
            stops = [(.13, .52, .56), (.94, .91, .77), (.84, .43, .16)]
            for chain, positions in residues.items():
                for number, resi in enumerate(positions):
                    step = round(255 * number / max(1, len(positions) - 1))
                    if step not in color_indices:
                        name = 'pymol_ai_gradient_' + str(step)
                        position = step * 2 / 255
                        segment = min(1, int(position))
                        blend = position - segment
                        rgb = [a + blend * (b - a) for a, b in zip(stops[segment], stops[segment + 1])]
                        self.cmd.set_color(name, rgb)
                        color_indices[step] = self.cmd.get_color_index(name)
                    residue_colors[(chain, resi)] = color_indices[step]
            mapping = {(model, index): residue_colors[((model, segi, chain), resi)] for model, segi, chain, resi, index in rows}
        self.cmd.alter(target, 'color = colors[(model, index)]', space={'colors': mapping})
        self.cmd.recolor()
        return {'palette': palette, 'selection': selection, 'polymerAtomsColored': len(rows),
                'chainsColored': len(chains), 'note': 'Decorative coloring only. Nonpolymer atoms, coordinates, camera and representations were preserved; B-factors were not changed.'}

    def reset(self):
        result = self.apply_preset('simple')
        self.set_options({'background': 'white'})
        result['current'] = self.state()
        result['note'] = 'Reset rendering to Simple and white background. Camera, representations and atom colors were preserved.'
        return result

    def state(self):
        c = self.cmd
        specular, reflect = c.get_setting_float('specular'), c.get_setting_float('reflect')
        rgb = list(c.get_color_tuple(c.get_setting_int('bg_rgb')))
        ray_opaque = c.get_setting_int('ray_opaque_background')
        if ray_opaque < 0:
            ray_opaque = c.get_setting_boolean('opaque_background')
        if c.get_setting_text('bg_image_filename') or c.get_setting_boolean('bg_gradient'):
            background = 'custom'
        elif not ray_opaque:
            background = 'transparent'
        elif all(abs(x - 1) < .001 for x in rgb):
            background = 'white'
        elif all(abs(x) < .001 for x in rgb):
            background = 'black'
        else:
            background = 'custom'
        gain = c.get_setting_float('ray_trace_gain')
        outline_index = c.get_setting_int('ray_trace_color')
        outline_rgb = c.get_color_tuple(outline_index) if outline_index >= 0 else None
        ortho = c.get_setting_boolean('orthoscopic')
        ray_ortho = c.get_setting_int('ray_orthoscopic')
        projection = 'orthographic' if ortho else 'perspective'
        ray_projection = projection if ray_ortho < 0 else ('orthographic' if ray_ortho else 'perspective')
        return {
            'shadows': bool(c.get_setting_boolean('ray_shadows')),
            'silhouettes': c.get_setting_int('ray_trace_mode') in {1, 2, 3},
            'background': background, 'backgroundRGB': rgb,
            'material': 'matte' if abs(specular) < .001 and abs(reflect) < .001 else
                        'glossy' if specular >= .5 and reflect >= .25 else 'custom',
            'depth_cue': bool(c.get_setting_boolean('depth_cue')),
            'ambient': c.get_setting_float('ambient'), 'direct': c.get_setting_float('direct'),
            'surfaceOcclusion': c.get_setting_int('ambient_occlusion_mode') != 0,
            'surface_depth': c.get_setting_int('ambient_occlusion_mode') != 0,
            'outline_strength': next((key for key, value in OUTLINE_STRENGTH.items() if abs(gain - value) < .001), 'custom'),
            'outline_color': next((key for key, value in OUTLINE_COLORS.items() if outline_rgb is not None and all(abs(a-b) < .005 for a,b in zip(outline_rgb, c.get_color_tuple(value)))), 'custom'),
            'projection': projection if projection == ray_projection else 'custom',
            'viewportProjection': projection, 'rayProjection': ray_projection,
            'quality': {1: 'standard', 2: 'high'}.get(c.get_setting_int('antialias'), 'custom'),
        }

    def context(self):
        return {'presets': [{'id': key, 'label': value[0], 'description': value[1]}
                            for key, value in PRESETS.items()],
                'availableOptions': OPTION_VALUES, 'current': self.state(), 'renderNote': RENDER_NOTE,
                'palettes': [{'id': key, 'label': value[0], 'description': value[1]} for key, value in PALETTES.items()],
                'focusPreset': {'operation': 'graphics_focus', 'selectionRequired': True,
                                'description': '70% transparent protein cartoon with opaque selected ligand or whole-residue sticks. This changes representations, retaining colors, lighting and camera. Existing protein surface patches remain translucent.'},
                'preserves': 'Lighting presets preserve orientation, representations and atom colors. Publication sets a white background. The focus preset changes representations and transparency.'}
