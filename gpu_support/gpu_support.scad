// SIXER AI - GPU support column (RTX 4070, one-end support)
// Open in OpenSCAD (free), press F6, then File > Export > STL.
// Material: glow-in-the-dark PETG. Print UPRIGHT (rod vertical), no supports.
// All units mm. Change the parameters below to fit.

/* [Overall] */
total_h   = 83.3;  // floor of case to underside of GPU
// Top section limit (you said <= 15 mm). Used as both width and height of the neck.
top_w     = 15;
top_h     = 15;

/* [Base] */
base_w    = 40;
base_d    = 40;
base_h    = 5;

/* [Hollow column] */
col_od    = 24;    // outer diameter of the glowing tube
wall      = 2.4;   // 6 perimeters with a 0.4 nozzle
rib_t     = 1.6;   // internal rib (floor) thickness
rib_pitch = 12;    // a rib every 12 mm

/* [Steel rod] */
rod_d     = 5;     // 5 mm steel rod
rod_clear = 0.3;   // epoxy gap
rod_boss  = 9;     // solid sleeve around the rod

/* [Top pad] */
pad_t     = 3;     // solid cap that touches the card (add silicone pad on top)

/* [Logo] */
// Export your logo outline as logo.svg next to this file, set use_logo = true.
use_logo  = false;
logo_w    = 18;    // logo width on the tube face
logo_depth= 0.8;   // how far the logo is embossed

$fn = 96;
col_h = total_h - base_h - top_h;
bore  = rod_d + rod_clear;

module tube() {
  difference() {
    cylinder(d = col_od, h = col_h);
    translate([0, 0, -1]) cylinder(d = col_od - 2*wall, h = col_h + 2);
  }
  // rod sleeve
  cylinder(d = rod_boss, h = col_h);
  // internal ribs keep the walls round and the rod centred
  for (z = [rib_pitch : rib_pitch : col_h - rib_pitch/2])
    translate([0, 0, z]) cylinder(d = col_od - 0.01, h = rib_t);
}

module neck() {
  // square neck, top_w wide, rounded into the pad
  hull() {
    translate([0, 0, 0]) cylinder(d = col_od, h = 0.01);
    translate([-top_w/2, -top_w/2, top_h - pad_t]) cube([top_w, top_w, pad_t]);
  }
}

module logo() {
  if (use_logo)
    translate([0, -col_od/2 + 0.01, base_h + col_h/2])
      rotate([90, 0, 0])
        linear_extrude(logo_depth)
          resize([logo_w, 0], auto = true)
            import("logo.svg", center = true);
}

difference() {
  union() {
    // base foot with rounded corners
    translate([0, 0, 0])
      linear_extrude(base_h)
        offset(r = 4) square([base_w - 8, base_d - 8], center = true);
    translate([0, 0, base_h]) tube();
    translate([0, 0, base_h + col_h]) neck();
    logo();
  }
  // rod bore: open at the bottom so the rod slides in after printing,
  // stops under the top pad so no metal touches the card.
  translate([0, 0, -1]) cylinder(d = bore, h = total_h - pad_t + 1);
}

// Rod length to cut (sits flush with the bottom of the base):
echo(str("Cut rod to ", total_h - pad_t - 0.5, " mm"));
