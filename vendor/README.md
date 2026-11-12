# GrowKaz Stickman Studio (local plugin archive)

The Actions workflow can use the creator-provided GrowKaz renderer archive when it is present at:

`vendor/GrowKaz_Stickman.plugin`

To activate the GrowKaz renderer:
1. Upload the original `GrowKaz_Stickman.plugin` archive from the tutorial download into this folder in the repository.
2. Keep the filename exactly `GrowKaz_Stickman.plugin`.
3. Run **Actions → Free Animated 3D Explainer** with `stage=render`.

The workflow extracts only the bundled `skills/make-2d-video/kit/` runtime and invokes `scripts/render_growkaz.py`. It keeps GrowKaz attribution in the archive and does not claim the plugin is MIT/open source. The archive provided in chat did not include a separate license file, so retain the creator's attribution and any permission/terms supplied with the download.

If the archive is absent, the workflow continues using the repository's existing Remotion renderer.
