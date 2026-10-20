---
name: Slate Flight Utility
colors:
  surface: '#121316'
  surface-dim: '#121316'
  surface-bright: '#38393c'
  surface-container-lowest: '#0d0e11'
  surface-container-low: '#1a1b1e'
  surface-container: '#1e2022'
  surface-container-high: '#292a2d'
  surface-container-highest: '#343538'
  on-surface: '#e3e2e6'
  on-surface-variant: '#c3c6d1'
  inverse-surface: '#e3e2e6'
  inverse-on-surface: '#2f3033'
  outline: '#8d919b'
  outline-variant: '#424750'
  surface-tint: '#a8c8ff'
  primary: '#b5cfff'
  on-primary: '#003061'
  primary-container: '#8ab4f8'
  on-primary-container: '#0d4582'
  inverse-primary: '#315f9d'
  secondary: '#adc7ff'
  on-secondary: '#002e68'
  secondary-container: '#026be0'
  on-secondary-container: '#f2f4ff'
  tertiary: '#b0d5dc'
  on-tertiary: '#10353c'
  tertiary-container: '#95b9c1'
  on-tertiary-container: '#274a51'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a8c8ff'
  on-primary-fixed: '#001b3c'
  on-primary-fixed-variant: '#114784'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc7ff'
  on-secondary-fixed: '#001a41'
  on-secondary-fixed-variant: '#004493'
  tertiary-fixed: '#c4e9f1'
  tertiary-fixed-dim: '#a8cdd4'
  on-tertiary-fixed: '#001f24'
  on-tertiary-fixed-variant: '#294c52'
  background: '#121316'
  on-background: '#e3e2e6'
  surface-variant: '#343538'
typography:
  display-lg:
    fontFamily: Roboto Flex
    fontSize: 3.5rem
    fontWeight: '400'
    lineHeight: 4.25rem
    letterSpacing: -0.02em
  headline-xl:
    fontFamily: Roboto Flex
    fontSize: 2.25rem
    fontWeight: '400'
    lineHeight: 2.75rem
    letterSpacing: -0.01em
  headline-xl-mobile:
    fontFamily: Roboto Flex
    fontSize: 1.75rem
    fontWeight: '500'
    lineHeight: 2.25rem
    letterSpacing: 0em
  headline-md:
    fontFamily: Roboto Flex
    fontSize: 1.375rem
    fontWeight: '500'
    lineHeight: 1.75rem
    letterSpacing: 0em
  title-md:
    fontFamily: Roboto Flex
    fontSize: 1.125rem
    fontWeight: '500'
    lineHeight: 1.5rem
    letterSpacing: 0.01em
  body-lg:
    fontFamily: Roboto Flex
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.5rem
    letterSpacing: 0.01em
  body-md:
    fontFamily: Roboto Flex
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.25rem
    letterSpacing: 0.015em
  body-sm:
    fontFamily: Roboto Flex
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1rem
    letterSpacing: 0.02em
  label-lg:
    fontFamily: Roboto Flex
    fontSize: 0.875rem
    fontWeight: '500'
    lineHeight: 1.25rem
    letterSpacing: 0.01em
  label-md:
    fontFamily: Roboto Flex
    fontSize: 0.75rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: 0.03em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-lg: 1.5rem
  margin: 1rem
  margin-md: 2rem
  margin-lg: 3.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
  space-2xl: 2rem
---

## Brand & Style

This design system embodies high-efficiency, data-dense utilitarian elegance. Inspired by modern productivity suites and high-utility search engines like Google Flights, it prioritizes fast cognitive scanning, high readability, and effortless navigation over decorative ornamentation. 

The aesthetic is built upon modern digital minimalism:
- **Clean Structural Utility:** Strict layout bounds, restrained elevation, and purposeful line-work.
- **Deep Slate Comfort:** A dark theme engineered for extended screen time without eye fatigue, utilizing layered charcoal tones rather than harsh absolute blacks.
- **Focus & Restraint:** Interactive states and focus targets use controlled slate-blue accents that direct attention cleanly without neon vibrance or sci-fi glow effects.
- **Tactile Clarity:** Pill-shaped chips, segmented controls, and understated micro-borders define interactive boundaries while keeping the visual field quiet and calm.

## Colors

The palette is engineered around dark charcoal neutrals and precision cool-blue accents, delivering high contrast ratios compliant with WCAG AAA standards for legibility.

### Surface Tiers
- **Canvas Base (`#202124`):** The primary backdrop across views and master viewports.
- **Surface Elevation 1 (`#303134`):** Main content cards, primary search bars, segmented module wrappers.
- **Surface Elevation 2 (`#3c4043`):** Hover states, nested input backgrounds, and secondary interactive wells.
- **Surface Active / Pill Fill (`#282a2d`):** Unselected chip background and recessed badge surfaces.

### Line & Border Structure
- **Border Default (`#3c4043`):** Card frames, chip outlines, input containers, and structural dividers.
- **Border Subtle (`#5f6368`):** Hover outlines and inactive icon strokes.
- **Border Focus (`#8ab4f8`):** Keyboard and active selection boundaries.

### Accents & Typography Fills
- **Primary Accent (`#8ab4f8`):** Muted slate blue for text links, selected pills, highlighted dates, and primary CTA icon badges.
- **Interactive Action Blue (`#1a73e8`):** Solid button fills and selected segmented-switch backgrounds.
- **Text Primary (`#e8eaed`):** 87% effective luminance for headlines, critical data points, and active labels.
- **Text Secondary (`#9aa0a6`):** Secondary meta-information, flight departure codes, and unselected control labels.
- **Text Disabled (`#5f6368`):** Placeholder text and inactive indicators.

## Typography

The type scale uses **Roboto Flex** for its clean neo-grotesque neutrality, disciplined horizontal proportions, and exceptional legibility across dense data interfaces.

- **Headlines:** Display and XL titles use lighter regular weights (`400`) to evoke a clean, modern, and uncluttered presence.
- **Section Titles & Module Names:** Scaled at `1.125rem` to `1.375rem` with medium weights (`500`) for swift structural parsing.
- **Numerical & Tabular Data:** Flight prices, flight durations, airport codes (e.g., "BOM", "SFO"), and calendar figures leverage standard body sizes with tabular spacing alignment to prevent jitter during updates.
- **Uppercase Restraint:** Keep uppercase formatting strictly limited to airport codes and abbreviated currency symbols. Labels and action triggers remain in standard title or sentence casing.

## Layout & Spacing

The layout model is anchored by a centered, fixed-width utility container (maximum content width: 1024px for compact search modules; 1280px for expansive data grids) situated within a fluid canvas.

### Form Factors & Breakpoints
- **Mobile (<640px):** Single-column layout. Search modules stack departure/destination inputs vertically. Exterior margin: `margin` (`1rem`). Gutter: `gutter` (`1rem`).
- **Tablet (640px - 1024px):** Split two-column modules. Search bar joins origin and destination side-by-side with interactive swap anchors. Exterior margin: `margin-md` (`2rem`).
- **Desktop (>1024px):** Clustered input docks where origin, destination, departure date, and return date sit within one cohesive unified surface block. Exterior margin: `margin-lg` (`3.5rem`).

### Grid & Density
Component internal spacing follows an 8px grid cadence (`space-sm` = 8px, `space-lg` = 16px, `space-2xl` = 32px), with 4px micro-offsets (`space-xs`) reserved for compact pill badges, trailing chevron offsets, and inline icons.

## Elevation & Depth

Visual hierarchy is communicated through **tonal layering** and **low-contrast outlines**, completely avoiding artificial box-shadow glows or skeuomorphic drops.

- **Base Layer (Elevation 0):** Background screen `#202124`. Completely flat.
- **Container Layer (Elevation 1):** Main search panels, tool cards, and map containers set to `#303134` with a crisp 1px solid border of `#3c4043`.
- **Nested Controls:** Inputs and nested pill buttons sit slightly darker or flush with the container (`#202124` or `#303134`), framed by a 1px border (`#3c4043`).
- **Active Focus & Selection:** Instead of outer shadow rings, active states trigger a clean 1.5px or 2px `#8ab4f8` outline directly bordering the element perimeter.
- **Floating Modals & Dropdown Popovers:** Use `#303134` with an ambient diffused shadow: `0 4px 16px rgba(0, 0, 0, 0.45)` coupled with a perimeter outline of `#5f6368` for precise definition against dark grounds.

## Shapes

The design system maintains a balanced hybrid shape grammar:
- **Pill Geometry (Full Radius / 9999px):** Applied to top navigation categories (Flights, Hotels, Explore), floating filter chips, selection dropdown triggers, and the primary "Explore / Search" floating action buttons.
- **Card & Shell Modules (`roundedness: 2` / 8px):** Applied to master search consoles, feature insight cards, data list panels, and itinerary preview rows.
- **Input Connectors (Segmented 8px / 4px):** Adjacent input fields (such as Origin and Destination) share merged middle radiuses, with outer corners rounded to 8px and inner connected edges remaining flat or slightly radiused (4px) to signal cohesive field pairing.

## Components

### Buttons
- **Primary Action (High Emphasis):** Oval pill shape (`rounded-full`), height `40px` or `44px`. Background `#8ab4f8` with dark slate text `#202124` for immediate call-to-action distinction, or solid blue `#1a73e8` with white `#ffffff` text for confirmed tasks.
- **Secondary / Flat Buttons:** Transparent background with `#8ab4f8` text and a subtle `#3c4043` border. Hover changes background to `rgba(138, 180, 248, 0.08)`.

### Chips & Filter Pills
- **Inactive State:** Pill shape with `#202124` or `#303134` surface, 1px border `#3c4043`, text `#9aa0a6`. Left-aligned mini-icon (18px) tinted `#9aa0a6`.
- **Selected State:** Background tinted with deep blue wash (`rgba(138, 180, 248, 0.15)`), border color shifts to `#8ab4f8`, text and icon illuminate to `#8ab4f8`.

### Input Fields & Search Bars
- **Container Structure:** 56px height, rounded corners (8px). Background `#202124` nested within the `#303134` master container.
- **Borders:** Resting state 1px border `#3c4043`. Active / Focus state 2px solid `#8ab4f8`.
- **Content Layout:** Fixed 20px leading icon (`#9aa0a6`), user value rendered in `#e8eaed`, trailing airport abbreviation code (e.g., "BOM") rendered in `#9aa0a6`.
- **Swap Destination Trigger:** Circular 32px badge floating between inputs with `#303134` background and `#3c4043` border; transitions on hover to `#3c4043`.

### Cards & Feature Panels
- **Insight / Tool Cards:** Background `#303134`, border 1px solid `#3c4043`, radius 8px, internal padding `1.5rem`.
- **Active / Selected Tool Item:** 1.5px border `#8ab4f8` accompanied by primary blue accent icons.

### Lists & Flight Rows
- **Layout:** Horizontal strip rows, separated by 1px dividers (`#3c4043`).
- **Row Hover:** Background transitions subtly to `#35373a`.
- **Data Points:** Clear 3-column split: Airline logo & flight times (Left), duration & layover stops (Center), total price in prominent green or `#8ab4f8` with expandable flight detail chevron (Right).

### Checkboxes & Segmented Controls
- **Checkboxes:** 18px rounded square (2px radius). Border `#5f6368`. Checked state fills `#8ab4f8` with `#202124` check icon.
- **Segmented Radio Tabs:** Embedded pill container with 4px inner padding. Active option renders with `#3c4043` background and `#e8eaed` label.