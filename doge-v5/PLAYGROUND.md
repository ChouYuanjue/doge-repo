# Doge scientific playground

`/lab` is intentionally limited to visual, parameterized scientific experiments that are easy to understand in a group chat. Engineering production tools and real crystal calculations are separate domains.

## `/lab`

Representative experiments include Mandelbrot/Julia, domain coloring, Newton fractals, logistic bifurcation, Lorenz/Rössler/Clifford attractors, Wolfram CA, Conway Life, Langton ant, Abelian sandpile, Ising, percolation, Gray–Scott, Ulam spiral, modular multiplication, Penrose/L-system, Voronoi, random matrices, double pendulum, three-body figure-eight, interference/electric fields, Bloch sphere, relativity diagrams, diffraction, beats/FFT, orbitals, lattice/XRD teaching models, Brownian motion, DLA, SIR/Lotka–Volterra/replicator dynamics, Chladni patterns, phyllotaxis, Galton board and Lissajous curves.

The design criterion is not feature count: an experiment should be visually immediate, parameter-sensitive and cheap enough for repeated group use. Presets are shortcuts to parameterized numerical models, not the only possible inputs. General functions, ODEs, discrete maps, vector fields, matrix transformations, atomic orbitals, and crystallographic bases are supported. See `docs/SCIENCE_LAB_GENERALIZATION.md` for exact algorithms and scientific limitations.

## Related formal domains

- `/eng circuit ...` — Schemdraw circuits.
- `/eng control ...` — Bode, Nyquist, root locus, step and impulse response via python-control.
- `/mat crystal info|powder + CIF` — real CIF parsing and powder XRD through Dans_Diffraction.
- `/diagram vegalite ...` — modern structured data visualization replacing the old raw Chart.js/QuickChart surface.

`/lab xrd` now computes reciprocal vectors, Bragg peak positions and an ideal kinematical structure factor from arbitrary lattice vectors and fractional atomic bases. This uses constant point-scattering weights and approximate instrument broadening; it is not an experimentally accurate CIF powder pattern. For actual CIF-based material diffraction, use `/mat crystal powder`.

## Implementation principles

1. small algorithms use bounded NumPy/Pillow local renderers;
2. mature scientific packages are wrapped instead of reimplemented when that is clearer and more reliable;
3. CPU-heavy work leaves the AstrBot event loop via `asyncio.to_thread()`;
4. every simulation has explicit size/iteration limits;
5. output is designed for a phone chat thumbnail rather than a notebook canvas.
