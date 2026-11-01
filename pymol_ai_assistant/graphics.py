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
}
HELP = {
    'shadows': 'Cast directional shadows to separate overlapping molecular parts. This effect appears in Ray renders, not the ordinary interactive view. Choose Ray in Draw/Ray, or Render preview (Ray) after changing it.',
    'silhouettes': 'Add dark outlines to clarify molecular boundaries, especially with Flat lighting. Outlines appear in Ray renders, not the ordinary interactive view. Choose Ray in Draw/Ray, or Render preview (Ray) to see them.',
    'depth_cue': 'Gently fade distant parts toward the background to distinguish front from back. Affects the interactive view and Ray renders. Disable it if important distant features become too faint.',
    'background': 'Choose a white, black or transparent background. Transparent PNG exports contain an alpha channel; the interactive view remains white, and Ray previews may show a checkerboard.',
    'background_white': 'Use an opaque white background, useful for papers, reports and light slides. Applies to the interactive view and rendered images; PNG exports are opaque.',
    'background_black': 'Use an opaque black background, useful for dark slides and emphasizing bright molecular colors. Applies to the interactive view and rendered images; PNG exports are opaque.',
    'background_transparent': 'Export a transparent PNG for placement over another background in slides or figures. The interactive view remains white; a Ray preview may show a checkerboard. Choose Ray in Draw/Ray and use the normal PNG export controls.',
    'material': 'Adjust shiny highlights independently of the lighting preset. Matte removes reflections; Glossy strengthens them. Choose a preset first, then adjust the material.',
    'material_matte': 'Remove shiny highlights and reflections while retaining the chosen lighting. Useful for readable molecular surfaces and illustrations. Choose Ray in Draw/Ray to inspect the final appearance.',
    'material_glossy': 'Strengthen shiny highlights and reflections to emphasize curvature. Useful for a polished 3D appearance; strong highlights can distract in dense figures. Choose Ray in Draw/Ray to inspect the final appearance.',
    'render_preview': 'Ray-render the current view up to 900 pixels wide to see shadows and silhouettes. Rotating returns to the interactive view. Use the normal Draw/Ray and export controls for the final image at your chosen resolution.',
    'reset': 'Return to Simple lighting and a white background. Keeps the camera, representations and current molecular colors; it does not undo other scene edits. Choose Ray in Draw/Ray to refresh a previously rendered image.',
    'button': 'Choose a graphics preset and independent options. Hover over each entry for an explanation. Select a preset first, then adjust options. Shadows and silhouettes require Ray in Draw/Ray or Render preview (Ray).',
}
OPTION_VALUES = {
    'shadows': [False, True], 'silhouettes': [False, True],
    'background': ['white', 'black', 'transparent'],
    'material': ['matte', 'glossy'], 'depth_cue': [False, True],
}
RENDER_NOTE = 'Shadows and silhouettes appear in Ray renders. Transparent backgrounds apply to PNG exports; the interactive view uses white.'


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
            if key in {'shadows', 'silhouettes', 'depth_cue'}:
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
                self.cmd.bg_color('white' if value == 'transparent' else value)
                self.cmd.set('ray_opaque_background', 0 if value == 'transparent' else 1)
            elif key == 'material':
                for setting, number in ({'specular': 0, 'reflect': 0, 'shininess': 20} if value == 'matte'
                                        else {'specular': .7, 'reflect': .35, 'shininess': 55}).items():
                    self.cmd.set(setting, number)
            elif key == 'depth_cue':
                self.cmd.set('depth_cue', int(value))
                self.cmd.set('ray_trace_fog', 1 if value else 0)
                self.cmd.set('fog_start', .6)
        return {'optionsApplied': dict(options), 'current': self.state(), 'renderNote': RENDER_NOTE}

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
        transparent = not c.get_setting_boolean('ray_opaque_background')
        background = 'transparent' if transparent else ('white' if all(abs(x - 1) < .001 for x in rgb)
                     else 'black' if all(abs(x) < .001 for x in rgb) else 'custom')
        return {
            'shadows': bool(c.get_setting_boolean('ray_shadows')),
            'silhouettes': c.get_setting_int('ray_trace_mode') in {1, 2, 3},
            'background': background, 'backgroundRGB': rgb,
            'material': 'matte' if abs(specular) < .001 and abs(reflect) < .001 else
                        'glossy' if specular >= .5 and reflect >= .25 else 'custom',
            'depth_cue': bool(c.get_setting_boolean('depth_cue')),
            'ambient': c.get_setting_float('ambient'), 'direct': c.get_setting_float('direct'),
            'surfaceOcclusion': c.get_setting_int('ambient_occlusion_mode') != 0,
        }

    def context(self):
        return {'presets': [{'id': key, 'label': value[0], 'description': value[1]}
                            for key, value in PRESETS.items()],
                'availableOptions': OPTION_VALUES, 'current': self.state(), 'renderNote': RENDER_NOTE,
                'preserves': 'Presets preserve orientation and representations. All presets preserve molecular colors. Publication sets a white background; other presets retain the background.'}
