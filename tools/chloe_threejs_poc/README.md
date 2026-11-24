# Chloe Three.js proof of concept

This page is isolated from the JARVIS UI. It loads the original root-level
`chloe_detroit_become_human.glb` through Three.js `GLTFLoader`, reports meshes,
skinned meshes, skeleton bones and animation clips, and plays the preferred
`idle` clip when one exists. Orbit and zoom controls are enabled for visual
inspection.

Three.js r187.0 is imported from jsDelivr. The PoC does not add npm packages or
change JARVIS runtime dependencies; an internet connection is required for the
library modules while this isolated page is open.

From the repository root, serve the page over HTTP (opening the HTML directly
as a `file://` URL does not allow GLTFLoader to fetch the GLB):

```powershell
python -m http.server 8765
```

Then open `http://127.0.0.1:8765/tools/chloe_threejs_poc/`.

The browser-rendered result is saved as [`preview.png`](preview.png).
