# Handoff: SIXER AI glow GPU support column

You are picking up a 3D-printing job. Read this whole file before acting. The owner prefers that you **ask clarifying questions whenever something is ambiguous** rather than guess, and confirms answers back to them (Socratic style).

## Goal

Design and print a decorative **GPU support column** that holds up one end of the owner's graphics card and shows off their "SIXER AI" logo (a neon circuit-brain with an "S" in the middle, cyan-to-magenta). The card is not sagging now. The support is preventive, but it must still carry the card safely, long term.

## Confirmed requirements (from the owner)

| Item | Value |
|---|---|
| GPU | ZOTAC Gaming GeForce RTX 4070 (white), ~1.1–1.5 kg |
| Mounting | Card installed horizontally in a white case, sitting above a perforated PSU shroud |
| Support position | **One end only** of the card (the free end, away from the PCIe bracket) |
| Total height | **83.3 mm** (measured with a tape from the shroud/floor to the underside of the card) |
| Top section | **One section at the top must be 15 mm or less** (see open question 1) |
| Printers | Two FDM printers (brand/model **unknown**, see open question 3) |
| Material | **No PLA.** Use **glow-in-the-dark PETG** |
| Glow | **Fully glowing** column. Passive phosphorescent glow only. **No RGB/ARGB, no electronics** |
| Reinforcement | A **hard metal rod** inside for strength. **5 mm steel** agreed; bigger or smaller is fine if needed. Owner can cut it to any length |
| Hollow | Owner wants the **middle hollow** if possible. If hollow isn't workable, **fill the gaps with black PETG** |
| Testing | Owner wants to go straight to a **full print, if we are confident** |

## Current state

- `gpu_support/gpu_support.scad` is a parametric OpenSCAD model. It is **not rendered or checked yet**, because OpenSCAD couldn't be installed in the previous environment. First job: render it (F6) and fix any errors.
- The model is on branch `ccr-a9b56885-pa6772`, in draft pull request sixerrexis/HoloVision#2.
- Nothing has been printed. The previous AI could not reach the printers: it ran in a cloud container, and the owner's computer did not offer its folder to cloud sessions over Remote Control.

### What the model does

- 40 × 40 × 5 mm rounded base foot.
- Hollow round tube, 24 mm across, with 2.4 mm walls (6 perimeters at a 0.4 mm nozzle).
- Internal ribs (1.6 mm floors) every 12 mm keep the walls round and the rod centered.
- A 9 mm solid sleeve surrounds a 5.3 mm bore for the 5 mm rod.
- The bore is **open at the bottom** so the rod slides in after printing, with epoxy. It stops under a 3 mm solid top cap, so **no metal touches the card**.
- A neck at the top narrows to `top_w` = 15 mm and is `top_h` = 15 mm tall.
- Optional embossed logo: set `use_logo = true` and put `logo.svg` next to the file.
- `echo` prints the rod cut length, about 79.8 mm.

## Open questions: ask the owner before printing

1. **What does "one section at the top must be 15 mm or less" mean?** The model treats it as a neck both 15 mm wide and 15 mm tall. It may mean only width (a clearance gap near a cable or fan) or only height. Ask, and if possible get a photo or measurement of what sits next to the card at that point.
2. **Logo file.** The owner has only a PNG (1254 × 1254). Ask for an SVG, or trace the PNG (Inkscape → Trace Bitmap). Keep every line at least 1 mm wide at final size, or FDM will lose it. Decide with the owner how the logo appears on a round 24 mm tube: an embossed plaque, a flat front face, or a wider logo-shaped body.
3. **Printer brand/model, bed size, nozzle, slicer**, and how the printers are reached: they are on a Wi‑Fi hotspot hosted by the owner's computer. You need to run on that computer, or have a working remote link to it, to send jobs.
4. **Does the owner already have glow PETG** on hand, and which brand? Glow filament is abrasive. A brass nozzle wears out fast, so a hardened steel nozzle is recommended. Confirm what their printers have.
5. **Exact contact point** under the card: shroud, backplate, or PCB edge? The top pad must rest on a rigid, non-conductive spot. Never let it press on exposed components.

## Recommended print settings (glow PETG, adjust per printer)

- **Orientation: upright** (rod vertical). The hollow tube needs no supports this way, and the card's weight presses down through the layers (compression), which is the strong direction. An earlier message told the owner to print flat. Upright replaces that advice for this design.
- Nozzle 0.4 mm (hardened steel preferred), 0.2 mm layers.
- 6 perimeters. Solid base and top cap. Ribs print as bridges, so tune bridging if they sag.
- PETG temperatures: about 235–250 °C nozzle, 70–85 °C bed, low cooling. Slow down on bridges.
- Dry the filament first. PETG absorbs moisture.

## Assembly

1. Cut the 5 mm steel rod to the length the model echoes, and deburr it.
2. Rough up and degrease the rod, then bond it into the bore with slow-cure epoxy. Insert from the bottom.
3. Let it cure fully (24 h).
4. Stick a thin silicone or rubber pad on the top cap.
5. Fit it under the free end of the card. It should touch lightly and carry load, not lift the card. Lifting stresses the PCIe slot.

## Verification before calling it done

- [ ] Model renders in OpenSCAD with no errors, and exports a manifold STL.
- [ ] Height measures 83.3 mm, and the top section meets the confirmed 15 mm rule.
- [ ] Slicer preview shows the hollow walls, ribs, and rod bore as intended, with no unsupported overhangs.
- [ ] **Load test** before trusting it in the PC. The owner wants a full print only "if we are confident", and confidence has to come from a test, not from the design alone. Either print a short 20 mm section with the same walls and bore, or test the full part. With the rod epoxied in, load it gradually to about 3 kg (about 2× the card) and leave it for a few hours. Check for cracks, creep, or the rod shifting.
- [ ] Glow check: charge it under light and confirm it glows across the whole column.
- [ ] Rod fully enclosed, with no exposed metal near the card.

## Don'ts

- Don't use PLA (owner's rule; it also creeps under load and heat).
- Don't add RGB or electronics.
- Don't send a print job without the owner's go-ahead. Starting a physical print is their call.
- Don't claim the part is strong enough without a load test.
