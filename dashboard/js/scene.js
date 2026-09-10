/**
 * The 3D scene for the AquaSync twin.
 *
 * The terrain is not modelled. It is the real Periyar valley, decoded from the
 * same Terrarium DEM the catchment analysis uses, baked to
 * `assets/terrain_idukki.png` by `scripts/build_terrain.py`. Ridge lines,
 * spurs and the gorge below the dam are all measured ground.
 *
 * What that buys is more than looks. Because the ground is real and the
 * reservoir footprint comes from the DEM, raising the modelled level walks the
 * shoreline up actual topography - the water finds the side valleys by itself.
 * Nothing about the waterline is drawn by hand.
 *
 * Two things are honestly *not* real, and the caption in the corner says so:
 *
 *   - There is no bathymetry for Idukki in any public dataset, so the bed
 *     under the reservoir is unknown. The mesh simply stops at the shoreline
 *     and the water is shaded by distance from the bank rather than by depth.
 *   - The dam and spillway are schematic. Their dimensions come from
 *     twin/constants.py, but the geometry is representative, not surveyed.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// -- scene scaling ----------------------------------------------------------
// The window is 18 km across and holds about a kilometre of relief. At true
// proportions that reads as a plate, so height is exaggerated - modestly, and
// stated, because a twin that quietly stretches its own terrain is a twin you
// cannot trust about anything else.
const SPAN_UNITS = 900;
const VERT_EXAG = 2.0;
const DATUM_M = 250;

const SKY_TOP = new THREE.Color(0x2c5a86);
const SKY_HORIZON = new THREE.Color(0xbcd0dc);

export class TwinScene {
  constructor(stage) {
    this.stage = stage;
    this.terrain = null;
    this.meta = null;
    this.clock = new THREE.Clock();

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(
      42, stage.clientWidth / stage.clientHeight, 0.5, 4000,
    );

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setSize(stage.clientWidth, stage.clientHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    stage.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.minDistance = 12;
    this.controls.maxDistance = 1400;

    this.scene.fog = new THREE.FogExp2(SKY_HORIZON.getHex(), 0.0016);

    this._buildSky();
    this._buildLights();

    addEventListener('resize', () => this.resize());
  }

  /** Metres above sea level to scene Y. */
  elevToY(m) {
    return (m - DATUM_M) * (SPAN_UNITS / this.spanM) * VERT_EXAG;
  }

  get spanM() {
    return this.meta ? this.meta.span_m : 18000;
  }

  // ------------------------------------------------------------------ sky
  _buildSky() {
    const geo = new THREE.SphereGeometry(2600, 32, 20);
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      uniforms: {
        uTop: { value: SKY_TOP },
        uHorizon: { value: SKY_HORIZON },
      },
      vertexShader: `
        varying vec3 vWorld;
        void main() {
          vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 uTop;
        uniform vec3 uHorizon;
        varying vec3 vWorld;
        void main() {
          float h = normalize(vWorld).y;
          // Compress the gradient toward the horizon so the haze band sits
          // where the terrain actually meets the sky.
          float t = pow(clamp(h * 1.6 + 0.06, 0.0, 1.0), 0.55);
          gl_FragColor = vec4(mix(uHorizon, uTop, t), 1.0);
        }`,
    });
    this.scene.add(new THREE.Mesh(geo, mat));
  }

  _buildLights() {
    // Late-morning sun from the south-east: rakes the ridges enough to read
    // relief without throwing the gorge into full shadow.
    this.sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
    this.sun.position.set(260, 340, 190);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.bias = -0.0006;
    const s = 260;
    Object.assign(this.sun.shadow.camera, {
      left: -s, right: s, top: s, bottom: -s, near: 10, far: 1400,
    });
    this.scene.add(this.sun);
    this.scene.add(this.sun.target);

    // Sky fill, and enough of it. A gorge lit by one hard light and a token
    // ambient reads as a black hole, and the drop below the dam is the part of
    // this view that has to stay legible.
    this.scene.add(new THREE.HemisphereLight(0xd6e6f2, 0x4a5340, 2.0));
    this.scene.add(new THREE.AmbientLight(0x9fb4c4, 0.55));
  }

  // -------------------------------------------------------------- terrain
  /**
   * Load the baked DEM and build the ground, the water and the structures.
   * Resolves to the metadata so the caller can caption the provenance.
   */
  async load(base = 'assets') {
    const meta = await (await fetch(`${base}/terrain_idukki.json`)).json();
    this.meta = meta;
    const n = meta.grid;

    const [height, mask] = await Promise.all([
      this._decode(`${base}/terrain_idukki.png`, n),
      this._decode(`${base}/terrain_idukki_mask.png`, n),
    ]);

    this.elev = new Float32Array(n * n);
    for (let i = 0, p = 0; i < this.elev.length; i++, p += 4) {
      this.elev[i] = height[p] * 256 + height[p + 1] + height[p + 2] / 256 - 32768;
    }
    this.mask = mask;
    this.n = n;

    // Publish the vertical stretch so the caption can state it. Read from the
    // constant the geometry actually uses rather than written out again next
    // to the caption text, because the number a viewer is shown and the number
    // the terrain is built with must not be able to drift apart.
    meta.vertical_exaggeration = VERT_EXAG;

    // Real ground cover, if it has been baked. Awaited rather than left to
    // arrive whenever, so the provenance caption can state what is actually
    // on screen instead of what was hoped for - a missing or broken asset
    // must not produce a caption claiming a photograph.
    this.imagery = await this._loadImagery(base);
    meta.imagery = this.imagery ? this.imagery.meta : null;

    this._buildGround();
    this._buildWater(base);
    this._buildStructures();
    this._frameCamera();
    return meta;
  }

  /**
   * Fetch the Sentinel-2 ground texture and its provenance, or null.
   *
   * Null is a supported outcome, not an error: a clone that has not run
   * `scripts/build_imagery.py` still renders, on the procedural shading the
   * ground had before. Both halves must arrive - a texture with no sidecar
   * cannot be captioned honestly, and a sidecar with no texture would caption
   * something that is not being drawn.
   */
  async _loadImagery(base) {
    try {
      const res = await fetch(`${base}/terrain_idukki_imagery.json`);
      if (!res.ok) return null;
      const meta = await res.json();

      const tex = await new Promise((resolve, reject) => {
        new THREE.TextureLoader().load(
          `${base}/terrain_idukki_imagery.jpg`, resolve, undefined, reject);
      });

      // Colour, so it wants the sRGB transfer function - unlike the heightmap
      // and the mask, which are packed data and must stay linear.
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
      tex.anisotropy = this.renderer?.capabilities?.getMaxAnisotropy?.() ?? 1;
      return { tex, meta };
    } catch {
      return null;
    }
  }

  async _decode(url, size) {
    const img = new Image();
    img.src = url;
    await img.decode();
    const cv = document.createElement('canvas');
    cv.width = cv.height = size;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, size, size);
    return ctx.getImageData(0, 0, size, size).data;
  }

  _buildGround() {
    const n = this.n;
    const geo = new THREE.PlaneGeometry(SPAN_UNITS, SPAN_UNITS, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2);

    const pos = geo.attributes.position;
    for (let i = 0; i < this.elev.length; i++) pos.setY(i, this.elevToY(this.elev[i]));
    pos.needsUpdate = true;

    // Drop the triangles there is genuinely no ground for, and only those.
    //
    // The mask's red channel is the full-supply footprint, not the water
    // surface: this DEM has a median 3.6 m of relief inside it and its cells
    // run from 718 m to 734 m, so half of it is bank that stands above the
    // sheet the data captured. Dropping all of it deleted that bank, which is
    // the ground the shoreline is supposed to walk up as the level moves.
    //
    // What is actually unknown is the bed under the captured sheet. So the
    // test is depth, not membership: a cell is undrawable only where the DEM
    // is reporting a water surface rather than ground.
    const sheet = this.meta.reservoir.captured_sheet_level_m;
    const submerged = (i) => this.mask[i * 4] > 127 && this.elev[i] <= sheet + 0.5;
    const idx = [];
    for (let r = 0; r < n - 1; r++) {
      for (let c = 0; c < n - 1; c++) {
        const a = r * n + c, b = a + 1, d = a + n, e = d + 1;
        if (submerged(a) && submerged(b) && submerged(d) && submerged(e)) continue;
        idx.push(a, d, b, b, d, e);
      }
    }
    geo.setIndex(idx);
    geo.computeVertexNormals();

    // Colour by height and steepness: forest on the slopes, thin scrub and
    // rock on the ridges and anywhere too steep to hold soil.
    const colours = new Float32Array(this.elev.length * 3);
    const nrm = geo.attributes.normal;
    const lo = this.meta.elevation_m.min, hi = this.meta.elevation_m.max;
    const water = new THREE.Color(0x4b5b3e);
    const forest = new THREE.Color(0x33502f);
    const upland = new THREE.Color(0x6b7a45);
    const rock = new THREE.Color(0x8d8577);
    const c = new THREE.Color();
    for (let i = 0; i < this.elev.length; i++) {
      const t = THREE.MathUtils.clamp((this.elev[i] - lo) / (hi - lo), 0, 1);
      c.copy(water).lerp(forest, THREE.MathUtils.smoothstep(t, 0.0, 0.22));
      c.lerp(upland, THREE.MathUtils.smoothstep(t, 0.35, 0.85));
      const steep = 1 - THREE.MathUtils.clamp(nrm.getY(i), 0, 1);
      c.lerp(rock, THREE.MathUtils.smoothstep(steep, 0.42, 0.78));
      // A little per-vertex variation so large faces do not read as flat paint.
      const j = 1 + (Math.sin(i * 12.9898) * 43758.5453 % 1) * 0.06 - 0.03;
      colours[i * 3] = c.r * j;
      colours[i * 3 + 1] = c.g * j;
      colours[i * 3 + 2] = c.b * j;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colours, 3));

    // With imagery the photograph carries the colour and the DEM's own normals
    // carry the relief, so the procedural palette steps aside rather than
    // multiplying into it and tinting the ground green twice over. The vertex
    // colours stay on the geometry as the fallback when no texture was baked.
    //
    // The mesh already has no triangles inside the reservoir - they are
    // dropped above - so draping this cannot paint over the water. That
    // matters: the image freezes the shoreline on 7 February 2024 and the
    // twin moves the water level, so the photograph is never allowed to state
    // where the bank is. The dynamic water surface owns that, and a dry-season
    // scene means the strip between the two reads as the bare drawdown zone it
    // actually is.
    const material = new THREE.MeshStandardMaterial({
      vertexColors: !this.imagery,
      map: this.imagery ? this.imagery.tex : null,
      roughness: 0.97,
      metalness: 0.0,
    });

    this.ground = new THREE.Mesh(geo, material);
    this.ground.receiveShadow = true;
    this.ground.castShadow = true;
    this.scene.add(this.ground);
  }

  // ---------------------------------------------------------------- water
  _buildWater(base) {
    const loader = new THREE.TextureLoader();
    const heightTex = loader.load(`${base}/terrain_idukki.png`);
    const maskTex = loader.load(`${base}/terrain_idukki_mask.png`);

    // Elevation must be sampled point-wise: the Terrarium bytes are a packed
    // number, and blending two of them averages the encoding rather than the
    // height, which puts 200 m cliffs on flat ground wherever R rolls over.
    heightTex.magFilter = heightTex.minFilter = THREE.NearestFilter;

    // The mask is a coverage field, so it does interpolate - and wants to.
    // Nearest sampling draws the shoreline as 40 m staircase treads.
    maskTex.magFilter = maskTex.minFilter = THREE.LinearFilter;

    for (const t of [heightTex, maskTex]) {
      t.generateMipmaps = false;
      t.colorSpace = THREE.NoColorSpace;
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
    }

    this.waterUniforms = {
      uHeight: { value: heightTex },
      uMask: { value: maskTex },
      uLevel: { value: this.meta.reservoir.frl_m },
      uSheet: { value: this.meta.reservoir.captured_sheet_level_m },
      uTime: { value: 0 },
      uSun: { value: this.sun.position.clone().normalize() },
      uDeep: { value: new THREE.Color(0x1b4a63) },
      uShallow: { value: new THREE.Color(0x3e93a4) },
      uSky: { value: SKY_HORIZON.clone() },
      uFogColor: { value: SKY_HORIZON.clone() },
      uFogDensity: { value: this.scene.fog.density },
    };

    const geo = new THREE.PlaneGeometry(SPAN_UNITS, SPAN_UNITS, 1, 1);
    geo.rotateX(-Math.PI / 2);

    const mat = new THREE.ShaderMaterial({
      uniforms: this.waterUniforms,
      transparent: true,
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vWorld;
        void main() {
          vUv = uv;
          vec4 w = modelMatrix * vec4(position, 1.0);
          vWorld = w.xyz;
          gl_Position = projectionMatrix * viewMatrix * w;
        }`,
      fragmentShader: `
        precision highp float;
        uniform sampler2D uHeight;
        uniform sampler2D uMask;
        uniform float uLevel;
        uniform float uSheet;
        uniform float uTime;
        uniform vec3 uSun, uDeep, uShallow, uSky, uFogColor;
        uniform float uFogDensity;
        varying vec2 vUv;
        varying vec3 vWorld;

        float elevation(vec2 uv) {
          vec3 t = texture2D(uHeight, uv).rgb * 255.0;
          return t.r * 256.0 + t.g + t.b / 256.0 - 32768.0;
        }

        // Cheap layered ripples. Three scales moving on different headings
        // reads as wind chop without needing a normal map.
        vec3 ripple(vec2 p, float t) {
          float a = sin(p.x * 0.9 + t * 1.10) * cos(p.y * 0.7 - t * 0.80);
          float b = sin(p.x * 2.3 - t * 1.70 + 1.7) * cos(p.y * 2.9 + t * 1.30);
          float c = sin((p.x + p.y) * 5.1 + t * 2.60);
          vec2 g = vec2(a * 0.05 + b * 0.022 + c * 0.008,
                        a * 0.04 - b * 0.026 + c * 0.010);
          return normalize(vec3(-g.x, 1.0, -g.y));
        }

        void main() {
          vec4 m = texture2D(uMask, vUv);
          float e = elevation(vUv);
          float core = smoothstep(0.35, 0.65, m.r);

          // Inside the footprint, wet the ground the level actually covers -
          // never the whole footprint. Painting all of it made the shoreline
          // a fixed outline that could not move, so the reservoir only ever
          // rose and fell inside its own banks like a bathtub, and at a
          // typical level about 7 km2 of dry bank was drawn as water.
          //
          // The floor is the captured sheet. Below that the DEM is reporting
          // a water surface and the bed under it is unknown, so the sheet
          // stays wet rather than the twin inventing a beach it cannot see.
          float wet = max(uLevel, uSheet);
          bool flooded = core >= 0.02 && e <= wet;
          bool fringe = m.g > 0.5 && e <= uLevel;
          if (!flooded && !fringe) discard;

          // Distance from the bank, not depth - there is no bathymetry. Inside
          // the captured sheet it comes from the baked field; on ground the
          // water has newly climbed onto, from how far the level is above it.
          float shore = mix(clamp((uLevel - e) / 6.0, 0.0, 1.0) * 0.22, m.b, core);

          vec3 nrm = ripple(vWorld.xz * 0.13, uTime);
          vec3 view = normalize(cameraPosition - vWorld);

          vec3 col = mix(uShallow, uDeep, smoothstep(0.0, 0.34, shore));

          float diff = max(dot(nrm, normalize(uSun)), 0.0);
          vec3 half3 = normalize(normalize(uSun) + view);
          float spec = pow(max(dot(nrm, half3), 0.0), 180.0);
          // Grazing reflection, held back: at this scale most of the surface is
          // seen near-edge-on, and a physical fresnel term turns the whole
          // reservoir into a sheet of sky.
          float fres = pow(1.0 - max(dot(nrm, view), 0.0), 5.0);

          col += col * diff * 0.22;
          col = mix(col, uSky, clamp(fres, 0.0, 1.0) * 0.28);
          col += vec3(1.0, 0.96, 0.86) * spec * 1.9;

          // Foam where the sheet meets the bank, and a brighter line on ground
          // the water has just taken - that edge is where the level is legible.
          float band = 1.0 - smoothstep(0.0, 0.11, shore);
          float chop = 0.55 + 0.45 * sin(vWorld.x * 2.1 + vWorld.z * 1.7 + uTime * 2.2);
          col = mix(col, vec3(0.78, 0.86, 0.90), band * chop * 0.26);

          float alpha = mix(0.80, 0.97, smoothstep(0.0, 0.20, shore));

          float d = length(cameraPosition - vWorld);
          float fog = 1.0 - exp(-uFogDensity * uFogDensity * d * d);
          gl_FragColor = vec4(mix(col, uFogColor, clamp(fog, 0.0, 1.0)), alpha);
        }`,
    });

    this.water = new THREE.Mesh(geo, mat);
    this.water.renderOrder = 2;
    this.scene.add(this.water);
  }

  // ----------------------------------------------------------- structures
  /** Grid cell -> scene XZ. */
  _cellToXZ(gx, gy) {
    const u = gx / (this.n - 1), v = gy / (this.n - 1);
    return new THREE.Vector2((u - 0.5) * SPAN_UNITS, (v - 0.5) * SPAN_UNITS);
  }

  _buildStructures() {
    const meta = this.meta;
    const at = this._cellToXZ(meta.dam.grid_x, meta.dam.grid_y);
    const flow = new THREE.Vector2(meta.dam.flow_dir_xz[0], meta.dam.flow_dir_xz[1]).normalize();

    this.dam = new THREE.Group();
    this.dam.position.set(at.x, 0, at.y);
    // Face the wall across the valley, using the drainage direction the build
    // script derived from the terrain rather than an assumed compass bearing.
    this.dam.rotation.y = -Math.atan2(flow.y, flow.x);
    this.scene.add(this.dam);

    // Idukki stands 168.9 m from foundation to a crest a little above MWL. The
    // foundation is well below the present river bed, so most of that height is
    // buried here - which is also true of the real structure.
    const crestM = meta.reservoir.mwl_m + 1.6;
    const baseM = crestM - 168.9;
    const crestY = this.elevToY(crestM);
    const baseY = this.elevToY(baseM);

    const concrete = new THREE.MeshStandardMaterial({ color: 0x8f9490, roughness: 0.88 });
    this.dam.add(this._archDam(crestY, baseY, concrete));
    this._buildSpillway(crestY, concrete);
  }

  /**
   * A double-curvature arch, which is what Idukki actually is: the wall bows
   * upstream so the load goes into the abutments as compression. Dimensions
   * are representative - the shape is the point, not the survey.
   */
  _archDam(crestY, baseY, material) {
    // 365.85 m of crest, to scene scale. Everything else is proportioned off it.
    const chord = (365.85 / this.spanM) * SPAN_UNITS;
    const rise = chord * 0.30, thickCrest = chord * 0.045, thickBase = chord * 0.30;
    const R = (rise * rise + (chord * chord) / 4) / (2 * rise);
    const half = Math.asin((chord / 2) / R);
    const NU = 48, NV = 18;

    const pos = [], idx = [];
    for (let j = 0; j <= NV; j++) {
      const v = j / NV;
      const y = baseY + (crestY - baseY) * v;
      // Thin toward the crest, and pull the arch flatter near the base where
      // it is keyed into rock.
      const th = thickBase + (thickCrest - thickBase) * Math.pow(v, 0.75);
      for (let i = 0; i <= NU; i++) {
        const a = -half + (2 * half) * (i / NU);
        const cx = Math.sin(a) * R;
        const cz = Math.cos(a) * R - (R - rise);
        const nx = Math.sin(a), nz = Math.cos(a);
        pos.push(cx - nx * th * 0.5, y, cz - nz * th * 0.5);
        pos.push(cx + nx * th * 0.5, y, cz + nz * th * 0.5);
      }
    }
    const stride = (NU + 1) * 2;
    for (let j = 0; j < NV; j++) {
      for (let i = 0; i < NU; i++) {
        const a = j * stride + i * 2, b = a + 2;
        const c = a + stride, d = c + 2;
        idx.push(a, c, b, b, c, d);             // upstream face
        idx.push(a + 1, b + 1, c + 1, b + 1, d + 1, c + 1); // downstream face
      }
    }
    // Cap the crest.
    const top = NV * stride;
    for (let i = 0; i < NU; i++) {
      const a = top + i * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();

    const group = new THREE.Group();
    const mesh = new THREE.Mesh(geo, material);
    mesh.castShadow = mesh.receiveShadow = true;
    group.add(mesh);

    // Crest roadway and parapets. Without them the arch is a blank sheet of
    // concrete and reads as scenery; the deck is what makes it a structure
    // people drive across, and it gives the eye a scale reference.
    const deckMat = new THREE.MeshStandardMaterial({ color: 0x6f736d, roughness: 0.93 });
    const railMat = new THREE.MeshStandardMaterial({ color: 0x9aa09a, roughness: 0.7 });
    const segs = 26;
    for (let i = 0; i < segs; i++) {
      const a0 = -half + (2 * half) * (i / segs);
      const a1 = -half + (2 * half) * ((i + 1) / segs);
      const p0 = new THREE.Vector3(Math.sin(a0) * R, crestY, Math.cos(a0) * R - (R - rise));
      const p1 = new THREE.Vector3(Math.sin(a1) * R, crestY, Math.cos(a1) * R - (R - rise));
      const mid = p0.clone().add(p1).multiplyScalar(0.5);
      const len = p0.distanceTo(p1) * 1.06;
      const yaw = Math.atan2(p1.x - p0.x, p1.z - p0.z);

      const slab = new THREE.Mesh(
        new THREE.BoxGeometry(thickCrest * 2.1, chord * 0.012, len), deckMat,
      );
      slab.position.copy(mid);
      slab.rotation.y = yaw;
      slab.castShadow = slab.receiveShadow = true;
      group.add(slab);

      for (const off of [-1, 1]) {
        const rail = new THREE.Mesh(
          new THREE.BoxGeometry(chord * 0.008, chord * 0.02, len), railMat,
        );
        rail.position.copy(mid);
        rail.position.y += chord * 0.016;
        rail.translateOnAxis(
          new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)), off * thickCrest * 1.0,
        );
        rail.rotation.y = yaw;
        rail.castShadow = true;
        group.add(rail);
      }
    }
    return group;
  }

  /**
   * The gated spillway, set beside the arch. At Idukki the gates are not in
   * the arch at all - they sit on the Cheruthoni dam a short way along the
   * rim - so keeping them on a separate structure is the honest arrangement
   * as well as the buildable one. Five bays, matching constants.py.
   */
  _buildSpillway(crestY, concrete) {
    const g = new THREE.Group();
    // Butt the spillway block against the arch's left abutment rather than
    // leaving it standing off in open water. The arch runs x in about
    // [-9.2, +9.2] scene units; a 15-wide deck centred at -13 overlaps that
    // end by a few units, so the two structures read as joined. Kept in the
    // dam plane (z = 0), not pushed downstream, for the same reason.
    g.position.set(-13, 0, 0);
    this.dam.add(g);

    const sillY = this.elevToY(this.meta.reservoir.frl_m - 9.2);

    // A pier of concrete from the crest down to the sill, so the deck and its
    // gates sit on something instead of floating above the water.
    const abut = new THREE.Mesh(
      new THREE.BoxGeometry(15, Math.max(2, crestY - sillY), 7.4), concrete,
    );
    abut.position.set(0, (crestY + sillY) / 2, 0);
    abut.castShadow = abut.receiveShadow = true;
    g.add(abut);

    const deck = new THREE.Mesh(new THREE.BoxGeometry(15, 1.1, 7), concrete);
    deck.position.set(0, crestY, 0);
    deck.castShadow = deck.receiveShadow = true;
    g.add(deck);

    const pierMat = new THREE.MeshStandardMaterial({ color: 0x82877f, roughness: 0.9 });
    const gateMat = new THREE.MeshStandardMaterial({
      color: 0xc2532f, roughness: 0.45, metalness: 0.55,
    });

    this.gates = [];
    for (let i = 0; i < 5; i++) {
      const x = (i - 2) * 2.9;
      const pier = new THREE.Mesh(new THREE.BoxGeometry(0.7, crestY - sillY, 7), pierMat);
      pier.position.set(x - 1.45, (crestY + sillY) / 2, 0);
      pier.castShadow = true;
      g.add(pier);

      const gate = new THREE.Mesh(new THREE.BoxGeometry(2.2, 3.4, 0.45), gateMat);
      gate.position.set(x, sillY + 1.7, 2.6);
      gate.castShadow = true;
      g.add(gate);
      this.gates.push(gate);
    }
    const endPier = new THREE.Mesh(new THREE.BoxGeometry(0.7, crestY - sillY, 7), pierMat);
    endPier.position.set(3 * 2.9 - 1.45, (crestY + sillY) / 2, 0);
    g.add(endPier);

    this.gateSillY = sillY;
    this.gateTravel = 3.6;

    // Discharge plume, scaled by spill in update(). Kept deliberately simple:
    // it says "water is leaving here, this much", and claims nothing about
    // the jet's real trajectory.
    const jetGeo = new THREE.CylinderGeometry(1.6, 3.2, 16, 16, 1, true);
    jetGeo.translate(0, -8, 0);
    this.jet = new THREE.Mesh(jetGeo, new THREE.MeshStandardMaterial({
      color: 0xdff0f5, transparent: true, opacity: 0.0,
      roughness: 0.25, side: THREE.DoubleSide,
    }));
    this.jet.position.set(0, sillY, 5.0);
    this.jet.rotation.x = 0.32;
    g.add(this.jet);
  }

  _frameCamera() {
    const at = this._cellToXZ(this.meta.dam.grid_x, this.meta.dam.grid_y);
    const y = this.elevToY(this.meta.reservoir.frl_m);
    this.controls.target.set(at.x, y, at.y);
    this.sun.target.position.set(at.x, y, at.y);
    this.sun.target.updateMatrixWorld();
    this.sun.position.set(at.x + 210, y + 300, at.y + 250);

    this.setView(new URLSearchParams(location.search).get('view') || 'site');
  }

  /**
   * Named viewpoints. `site` is the working view - close enough to read the
   * gate and the waterline against the wall. `basin` pulls back to where the
   * reservoir's shape and the ridges that contain it are the subject.
   */
  setView(name) {
    if (!this.meta) return;
    const at = this._cellToXZ(this.meta.dam.grid_x, this.meta.dam.grid_y);
    const y = this.elevToY(this.meta.reservoir.frl_m);
    const flow = new THREE.Vector2(...this.meta.dam.flow_dir_xz).normalize();

    const views = {
      // The default deliberately stands well back. Up close the render starts
      // claiming detail the data does not have: at a 40 m posting the DEM
      // cannot resolve a gorge only a couple of hundred metres wide, so the
      // wall ends up looking planted on a smooth hillside. At this distance
      // the terrain is doing honest work and the dam reads in its valley.
      site: { back: 95, side: 58, up: 46, look: -22 },
      gate: { back: 38, side: 22, up: 15, look: -5 },
      basin: { back: 210, side: 130, up: 130, look: -60 },
    };
    const v = views[name] || views.site;

    this.camera.position.set(
      at.x + flow.x * v.back - flow.y * v.side,
      y + v.up,
      at.y + flow.y * v.back + flow.x * v.side,
    );
    this.controls.target.set(at.x + flow.x * v.look, y - 1.5, at.y + flow.y * v.look);
    this.controls.update();
    this.view = name;
  }

  // --------------------------------------------------------------- update
  /**
   * @param {object} s  level (m MSL), gate (0-100), spill (cumecs)
   */
  update(s) {
    const dt = this.clock.getDelta();
    const t = this.clock.elapsedTime;

    if (this.waterUniforms) {
      this.waterUniforms.uTime.value = t;
      this.waterUniforms.uLevel.value = s.level;
      this.water.position.y = this.elevToY(s.level);
    }

    if (this.gates) {
      const lift = (s.gate / 100) * this.gateTravel;
      for (const g of this.gates) g.position.y = this.gateSillY + 1.7 + lift;
    }

    if (this.jet) {
      const q = Math.min(1, s.spill / 900);
      this.jet.material.opacity = q * 0.75;
      this.jet.scale.set(0.35 + q * 0.9, 0.4 + q * 0.85, 0.35 + q * 0.9);
      this.jet.visible = q > 0.005;
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    return dt;
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.stage;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }
}
