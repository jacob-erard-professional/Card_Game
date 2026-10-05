// The poker room in 3D: your seat looking down at the felt, the RL robot across from you,
// and a casino full of robots behind it. app.js drives it; this file only draws.
import * as THREE from "three";

// Casino colours, largest first: [value, chip colour, edge stripe colour].
export const DENOMINATIONS = [
  [1000, "#d9a92e", "#5a3d05"],
  [500, "#6d3fb5", "#f4efe4"],
  [100, "#22232a", "#f4efe4"],
  [25, "#2f8f4e", "#f4efe4"],
  [5, "#c8372d", "#f4efe4"],
  [1, "#f2efe6", "#2d4f9e"],
];
const MAX_CHIPS_PER_COLUMN = 10;
const MAX_COLUMNS = 6;
// Stacks use the biggest chip that still makes at least this many, so $1,000 is ten $100s, not one $1,000.
const MIN_CHIPS_OF_TOP_DENOMINATION = 6;

export function chipBreakdown(amount) {
  const chips = [];
  let remaining = Math.max(0, Math.round(amount));
  const top = DENOMINATIONS.find(([value]) => remaining >= value * MIN_CHIPS_OF_TOP_DENOMINATION)?.[0] ?? 1;
  DENOMINATIONS.filter(([value]) => value <= top).forEach(([value, color, stripe]) => {
    const count = Math.floor(remaining / value);
    remaining -= count * value;
    if (count) chips.push({ value, color, stripe, count });
  });
  return chips;
}

export function chipLabel(value) {
  return value >= 1000 ? `${value / 1000}K` : String(value);
}

// ---------- Layout (metres; the felt is y = 0, you sit at +z, the robot at -z) ----------

const TABLE_A = 1.25;
const TABLE_B = 0.74;
const FLOOR_Y = -0.76;
const CARD_W = 0.09;
const CARD_H = 0.126;
const CHIP_R = 0.024;
const CHIP_H = 0.0072;
const HUMAN_TILT = 0.5;

const v3 = (x, y, z) => new THREE.Vector3(x, y, z);
const SPOTS = {
  hand: [v3(0, 0, 0.5), v3(0, 0, -0.5)],
  pile: [v3(0.33, 0, 0.5), v3(-0.33, 0, -0.5)],
  // Bets go out on the same side as the stack they come from, so a hand never reaches across a body.
  bet: [v3(0.2, 0, 0.3), v3(-0.2, 0, -0.3)],
  dealer: [v3(-0.24, 0, 0.36), v3(0.24, 0, -0.36)],
  pot: v3(0, 0, 0.14),
  deck: v3(-0.62, 0, -0.02),
  muck: v3(0.1, 0, 0.02),
};
const boardSpot = (i) => v3((i - 2) * 0.105, 0, -0.08);

// Where the HTML overlays (names, stacks, speech bubbles) sit in the room.
const ANCHORS = {
  "plate-0": v3(-0.36, 0, 0.56),
  "plate-1": v3(-0.5, 0.62, -1.0),
  "speech-0": v3(0.13, 0.03, 0.5),
  "speech-1": v3(0.27, 0.66, -1.0),
  "label-1": v3(0, 0, -0.4),
  "bet-0": v3(0.2, 0, 0.36),
  "bet-1": v3(-0.2, 0, -0.235),
  pot: v3(0, 0, 0.215),
  phase: v3(-0.5, 0, 0.14),
};

// Looking straight down, the robot is off the top of the frame, so its name and speech sit at its edge of the felt.
const TOP_ANCHORS = {
  "plate-1": v3(-0.14, 0, -0.66),
  "speech-1": v3(0.02, 0, -0.66),
};

const Q_FACE_UP = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));
const Q_FACE_DOWN = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));

const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const rand = (low, high) => low + Math.random() * (high - low);
const damp = (current, target, rate, dt) => current + (target - current) * (1 - Math.exp(-rate * dt));

// ---------- Canvas textures ----------

const SUITS = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };
let maxAnisotropy = 1;

function canvasTexture(width, height, draw, { repeat } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext("2d"), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = maxAnisotropy;
  if (repeat) {
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(...repeat);
  }
  return texture;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

const faceTextures = new Map();
function cardFaceTexture(card) {
  const key = `${card.rank}${card.suit}`;
  if (faceTextures.has(key)) return faceTextures.get(key);
  const red = card.suit === "hearts" || card.suit === "diamonds";
  const suit = `${SUITS[card.suit]}︎`;
  const texture = canvasTexture(256, 358, (ctx, w, h) => {
    roundRect(ctx, 2, 2, w - 4, h - 4, 24);
    ctx.fillStyle = "#f7f2e7";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(0,0,0,0.18)";
    ctx.stroke();
    ctx.fillStyle = red ? "#c0342c" : "#1b1b1f";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const corner = (flip) => {
      ctx.save();
      if (flip) {
        ctx.translate(w, h);
        ctx.rotate(Math.PI);
      }
      ctx.font = "900 74px Inter, system-ui, sans-serif";
      ctx.fillText(card.rank, 48, 56);
      ctx.font = "56px system-ui, sans-serif";
      ctx.fillText(suit, 48, 116);
      ctx.restore();
    };
    corner(false);
    corner(true);
    ctx.font = "170px system-ui, sans-serif";
    ctx.fillText(suit, w / 2, h / 2 + 8);
  });
  faceTextures.set(key, texture);
  return texture;
}

let backTexture;
function cardBackTexture() {
  backTexture ??= canvasTexture(256, 358, (ctx, w, h) => {
    roundRect(ctx, 2, 2, w - 4, h - 4, 24);
    ctx.fillStyle = "#f2ede0";
    ctx.fill();
    roundRect(ctx, 16, 16, w - 32, h - 32, 14);
    ctx.fillStyle = "#1f2d5c";
    ctx.fill();
    ctx.save();
    ctx.clip();
    ctx.strokeStyle = "rgba(244, 239, 228, 0.16)";
    ctx.lineWidth = 3;
    for (let d = -h; d < w + h; d += 22) {
      ctx.beginPath();
      ctx.moveTo(d, 0);
      ctx.lineTo(d + h, h);
      ctx.moveTo(d + h, 0);
      ctx.lineTo(d, h);
      ctx.stroke();
    }
    ctx.restore();
    ctx.fillStyle = "#d7b66d";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "900 78px Inter, system-ui, sans-serif";
    ctx.fillText("RL", w / 2, h / 2);
  });
  return backTexture;
}

const chipMaterialCache = new Map();
function chipMaterials(value) {
  if (chipMaterialCache.has(value)) return chipMaterialCache.get(value);
  const [, color, stripe] = DENOMINATIONS.find(([v]) => v === value);
  const side = canvasTexture(256, 16, (ctx, w, h) => {
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = stripe;
    for (let i = 0; i < 8; i += 1) ctx.fillRect((i / 8) * w, 0, w / 24, h);
  });
  const top = canvasTexture(128, 128, (ctx, w) => {
    const c = w / 2;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(c, c, c, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = stripe;
    for (let i = 0; i < 8; i += 1) {
      const a = (i / 8) * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(c, c, c, a, a + 0.28);
      ctx.arc(c, c, c * 0.8, a + 0.28, a, true);
      ctx.fill();
    }
    ctx.strokeStyle = stripe;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(c, c, c * 0.6, 0, Math.PI * 2);
    ctx.stroke();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `900 ${value >= 100 ? 34 : 42}px Inter, system-ui, sans-serif`;
    ctx.fillText(chipLabel(value), c, c + 2);
  });
  const material = (map) => new THREE.MeshStandardMaterial({ map, roughness: 0.45, metalness: 0.05 });
  const materials = [material(side), material(top), material(top)];
  chipMaterialCache.set(value, materials);
  return materials;
}

// ---------- Geometry helpers ----------

function roundedBox(w, h, d, r) {
  const shape = new THREE.Shape();
  const x = -w / 2 + r;
  const y = -h / 2 + r;
  const iw = w - 2 * r;
  const ih = h - 2 * r;
  shape.moveTo(x, y);
  shape.lineTo(x + iw, y);
  shape.lineTo(x + iw, y + ih);
  shape.lineTo(x, y + ih);
  shape.lineTo(x, y);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: d - 2 * r, bevelEnabled: true, bevelSize: r, bevelThickness: r, bevelSegments: 3, curveSegments: 4,
  });
  geometry.translate(0, 0, -(d - 2 * r) / 2);
  return geometry;
}

function ellipseShape(a, b) {
  const shape = new THREE.Shape();
  shape.absellipse(0, 0, a, b, 0, Math.PI * 2, false, 0);
  return shape;
}

class EllipseCurve3 extends THREE.Curve {
  constructor(a, b, y) {
    super();
    this.a = a;
    this.b = b;
    this.y = y;
  }

  getPoint(t, target = new THREE.Vector3()) {
    const angle = t * Math.PI * 2;
    return target.set(Math.cos(angle) * this.a, this.y, Math.sin(angle) * this.b);
  }
}

const standard = (color, options = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.1, ...options });
const glow = (color, intensity = 2) => new THREE.MeshStandardMaterial({ color: 0x111111, emissive: color, emissiveIntensity: intensity });

function shadowed(mesh, receive = false) {
  mesh.castShadow = true;
  mesh.receiveShadow = receive;
  return mesh;
}

// ---------- Furniture ----------

function feltTexture(base, edge) {
  return canvasTexture(1024, 620, (ctx, w, h) => {
    const gradient = ctx.createRadialGradient(w / 2, h / 2, 40, w / 2, h / 2, w * 0.55);
    gradient.addColorStop(0, base);
    gradient.addColorStop(1, edge);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 9000; i += 1) {
      ctx.fillStyle = `rgba(${Math.random() < 0.5 ? "255,255,255" : "0,0,0"},0.035)`;
      ctx.fillRect(Math.random() * w, Math.random() * h, 2, 2);
    }
    ctx.strokeStyle = "rgba(215, 182, 109, 0.4)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(w / 2, h / 2, w * 0.4, h * 0.38, 0, 0, Math.PI * 2);
    ctx.stroke();
  });
}

function buildPokerTable(a, b, felt) {
  const table = new THREE.Group();
  const flat = (geometry) => geometry.rotateX(-Math.PI / 2);

  const feltGeometry = flat(new THREE.ShapeGeometry(ellipseShape(a, b), 64));
  // ShapeGeometry's UVs are raw shape coordinates; stretch them over the texture.
  const uv = feltGeometry.attributes.uv;
  for (let i = 0; i < uv.count; i += 1) {
    uv.setXY(i, (uv.getX(i) + a) / (2 * a), (uv.getY(i) + b) / (2 * b));
  }
  const feltMesh = new THREE.Mesh(feltGeometry, new THREE.MeshStandardMaterial({ map: felt, roughness: 0.95 }));
  feltMesh.receiveShadow = true;
  table.add(feltMesh);

  const rail = new THREE.Mesh(
    new THREE.TubeGeometry(new EllipseCurve3(a + 0.04, b + 0.04, 0.025), 160, 0.07, 18, true),
    standard(0x3b2216, { roughness: 0.42, metalness: 0.05 }),
  );
  table.add(shadowed(rail, true));

  const apron = new THREE.Mesh(
    flat(new THREE.ExtrudeGeometry(ellipseShape(a + 0.08, b + 0.08), { depth: 0.12, bevelEnabled: false, curveSegments: 48 })),
    standard(0x5b3520, { roughness: 0.5 }),
  );
  apron.position.y = -0.125;
  table.add(shadowed(apron, true));

  const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.34, -FLOOR_Y - 0.12, 24), standard(0x2a1a12));
  pedestal.position.y = (FLOOR_Y - 0.12) / 2;
  table.add(shadowed(pedestal));
  return table;
}

function pendantLamp(color = 0xffd9a0) {
  const lamp = new THREE.Group();
  const shade = new THREE.Mesh(
    new THREE.CylinderGeometry(0.16, 0.42, 0.24, 32, 1, true),
    standard(0x1b3b2f, { side: THREE.DoubleSide, metalness: 0.4, roughness: 0.4 }),
  );
  lamp.add(shade);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 12), glow(color, 3));
  bulb.position.y = -0.06;
  lamp.add(bulb);
  const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 2), standard(0x111111));
  cord.position.y = 1.1;
  lamp.add(cord);
  return lamp;
}

// ---------- Robots ----------

const ROBOT_PALETTE = [
  { body: 0xa9b3bc, trim: 0xd7b66d, eye: 0x62f3ff },
  { body: 0xc77d4a, trim: 0x2b2f36, eye: 0xffd35c },
  { body: 0xe8e4da, trim: 0x2f6fd6, eye: 0x7dff9b },
  { body: 0x4f7f8e, trim: 0xe0c27a, eye: 0xff6b6b },
  { body: 0x8e5bbf, trim: 0xd9d9d9, eye: 0x9cf6ff },
  { body: 0x9a9d3a, trim: 0x2b2f36, eye: 0xff9cf0 },
];

// The classic tin robot: box head, antenna with a blinking bulb, glowing eyes, grille mouth, claw hands.
function buildRobot({ body, trim, eye }, { chair = true, hover = false } = {}) {
  const root = new THREE.Group();
  const metal = standard(body, { metalness: 0.75, roughness: 0.32 });
  const dark = standard(0x24282d, { metalness: 0.5, roughness: 0.5 });
  const trimMat = standard(trim, { metalness: 0.85, roughness: 0.28 });
  const eyeMat = glow(eye, 2.4);
  const bulbMat = glow(0xff3b3b, 2);
  const add = (geometry, material, parent, x = 0, y = 0, z = 0) => {
    const mesh = shadowed(new THREE.Mesh(geometry, material));
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  };

  const torso = new THREE.Group();
  torso.position.y = 0.04;
  root.add(torso);
  add(roundedBox(0.44, 0.46, 0.3, 0.05), metal, torso);
  add(new THREE.BoxGeometry(0.26, 0.15, 0.012), dark, torso, 0, 0.03, 0.15);
  const chestLights = [0xff4d4d, 0xffc94d, 0x4dff88].map((color, i) => {
    const material = glow(color, 1.5);
    add(new THREE.CylinderGeometry(0.018, 0.018, 0.01, 16).rotateX(Math.PI / 2), material, torso, (i - 1) * 0.07, 0.03, 0.158);
    return material;
  });
  for (let i = 0; i < 4; i += 1) add(new THREE.BoxGeometry(0.2, 0.008, 0.006), trimMat, torso, 0, -0.08 - i * 0.022, 0.152);
  add(new THREE.BoxGeometry(0.46, 0.035, 0.32), trimMat, torso, 0, -0.21, 0);
  add(new THREE.CylinderGeometry(0.05, 0.06, 0.08, 16), dark, torso, 0, 0.26, 0);

  const head = new THREE.Group();
  head.position.y = 0.3;
  torso.add(head);
  add(roundedBox(0.34, 0.27, 0.28, 0.05), metal, head, 0, 0.14, 0);
  add(roundedBox(0.27, 0.12, 0.03, 0.012), standard(0x0a0d10, { roughness: 0.15, metalness: 0.3 }), head, 0, 0.165, 0.13);
  const eyes = new THREE.Group();
  eyes.position.set(0, 0.165, 0.148);
  head.add(eyes);
  add(new THREE.BoxGeometry(0.056, 0.042, 0.01), eyeMat, eyes, -0.06);
  add(new THREE.BoxGeometry(0.056, 0.042, 0.01), eyeMat, eyes, 0.06);
  for (let i = -2; i <= 2; i += 1) add(new THREE.BoxGeometry(0.012, 0.034, 0.012), trimMat, head, i * 0.026, 0.06, 0.142);
  add(new THREE.CylinderGeometry(0.042, 0.042, 0.05, 20).rotateZ(Math.PI / 2), trimMat, head, -0.185, 0.14, 0);
  add(new THREE.CylinderGeometry(0.042, 0.042, 0.05, 20).rotateZ(Math.PI / 2), trimMat, head, 0.185, 0.14, 0);
  add(new THREE.CylinderGeometry(0.008, 0.008, 0.13), dark, head, 0, 0.34, 0);
  add(new THREE.SphereGeometry(0.026, 16, 12), bulbMat, head, 0, 0.42, 0);

  const arms = [-1, 1].map((side) => {
    const shoulder = new THREE.Group();
    shoulder.position.set(side * 0.275, 0.16, 0);
    torso.add(shoulder);
    add(new THREE.SphereGeometry(0.055, 16, 12), trimMat, shoulder);
    add(new THREE.CylinderGeometry(0.034, 0.034, 0.2, 14), metal, shoulder, 0, -0.1, 0);
    const elbow = new THREE.Group();
    elbow.position.y = -0.2;
    shoulder.add(elbow);
    add(new THREE.SphereGeometry(0.042, 14, 10), dark, elbow);
    add(new THREE.CylinderGeometry(0.031, 0.031, 0.21, 14), metal, elbow, 0, -0.105, 0);
    // The forearm telescopes out of itself when the robot reaches across the felt.
    const extension = add(new THREE.CylinderGeometry(0.022, 0.022, 1, 12), trimMat, elbow, 0, -0.21, 0);
    extension.scale.y = 1e-4;
    const hand = new THREE.Group();
    hand.position.y = -0.22;
    elbow.add(hand);
    add(new THREE.BoxGeometry(0.07, 0.035, 0.06), dark, hand);
    add(new THREE.BoxGeometry(0.014, 0.05, 0.04), trimMat, hand, -0.025, -0.035, 0);
    add(new THREE.BoxGeometry(0.014, 0.05, 0.04), trimMat, hand, 0.025, -0.035, 0);
    const tip = new THREE.Object3D();
    tip.position.y = -0.06;
    hand.add(tip);
    return { shoulder, elbow, hand, extension, tip, side };
  });

  if (chair) {
    const leather = standard(0x5a1820, { roughness: 0.55 });
    add(roundedBox(0.52, 0.78, 0.08, 0.03), leather, root, 0, -0.05, -0.22);
    add(roundedBox(0.52, 0.08, 0.5, 0.03), leather, root, 0, -0.3, 0);
  }
  if (hover) {
    add(new THREE.CylinderGeometry(0.16, 0.06, 0.32, 20), dark, root, 0, -0.34, 0);
    add(new THREE.TorusGeometry(0.11, 0.015, 8, 32).rotateX(Math.PI / 2), glow(eye, 2.5), root, 0, -0.5, 0);
  }

  return {
    root, torso, head, eyes, eyeMat, bulbMat, chestLights, arms,
    eyeColor: new THREE.Color(eye),
    seed: Math.random() * 100,
    mood: "idle",
    reach: 0,
    tap: 0,
    // Set while an arm is reaching for a point on the table: { side, target (world), weight 0..1 }.
    grab: null,
    blinkAt: rand(1, 4),
    rest: { shoulder: -0.68, elbow: -0.4 },
  };
}

const BULB = { idle: 0xff3b3b, thinking: 0xffc94d, happy: 0x4dff88, sad: 0x3a6bff, folded: 0x8a8a8a };

function animateRobot(robot, t, dt) {
  const { mood } = robot;
  const s = robot.seed;
  const thinking = mood === "thinking";

  const yaw = thinking ? Math.sin(t * 2.4) * 0.32 : Math.sin(t * 0.5 + s) * 0.12;
  const pitch = mood === "sad" ? 0.38 : mood === "folded" ? 0.12 : thinking ? -0.06 : Math.sin(t * 0.37 + s) * 0.04;
  const roll = thinking ? 0.16 : mood === "happy" ? Math.sin(t * 9) * 0.12 : 0;
  robot.head.rotation.y = damp(robot.head.rotation.y, yaw, 6, dt);
  robot.head.rotation.x = damp(robot.head.rotation.x, pitch, 6, dt);
  robot.head.rotation.z = damp(robot.head.rotation.z, roll, 6, dt);
  robot.torso.position.y = 0.04 + (mood === "happy" ? Math.abs(Math.sin(t * 9)) * 0.025 : Math.sin(t * 1.6 + s) * 0.004);
  robot.torso.rotation.x = damp(robot.torso.rotation.x, mood === "folded" ? -0.1 : 0, 4, dt);

  // Blink every few seconds; happy eyes squint into ^ ^.
  if (t > robot.blinkAt) robot.blinkAt = t + rand(2.2, 5.5);
  const blink = robot.blinkAt - t > 0.12 ? 1 : 0.12;
  const squint = mood === "happy" ? 0.35 : 1;
  robot.eyes.scale.y = Math.min(blink, squint);
  robot.eyes.position.x = thinking ? Math.sin(t * 7) * 0.014 : damp(robot.eyes.position.x, 0, 8, dt);
  robot.eyeMat.emissiveIntensity = mood === "sad" || mood === "folded" ? 0.7 : 2.4;

  robot.bulbMat.emissive.setHex(BULB[mood] ?? BULB.idle);
  robot.bulbMat.emissiveIntensity = thinking ? (Math.sin(t * 20) > 0 ? 4 : 0.4) : 1.4 + Math.sin(t * 2 + s) * 0.8;
  robot.chestLights.forEach((light, i) => {
    light.emissiveIntensity = thinking
      ? (Math.floor(t * 9) % 3 === i ? 3 : 0.3)
      : 0.9 + Math.sin(t * 1.3 + i * 2 + s) * 0.6;
  });

  robot.arms.forEach(({ shoulder, elbow, side }) => {
    const reach = side === 1 ? robot.reach : robot.reach * 0.25;
    const tap = side === 1 ? Math.sin(robot.tap * Math.PI * 4) * 0.18 * (robot.tap > 0 && robot.tap < 1 ? 1 : 0) : 0;
    shoulder.rotation.x = robot.rest.shoulder - reach * 0.75 - Math.max(0, tap);
    elbow.rotation.x = robot.rest.elbow + reach * 0.55 - (thinking && side === -1 ? 0.5 : 0);
    shoulder.rotation.z = side * (thinking && side === -1 ? -0.35 : 0.08);
  });
  aimArm(robot);
}

// Shoulder to claw tip with the elbow straight and the forearm retracted.
const ROBOT_ARM_LENGTH = 0.48;
const DOWN = v3(0, -1, 0);
const scratch = { a: new THREE.Vector3(), b: new THREE.Vector3(), q: new THREE.Quaternion(), aim: new THREE.Quaternion() };

// Blends the grabbing arm from its idle pose to pointing straight at the target, telescoping to reach it.
function aimArm(robot) {
  robot.arms.forEach((arm) => {
    const grab = robot.grab;
    let extend = 0;
    if (grab && grab.side === arm.side && grab.weight > 0) {
      const shoulderAt = arm.shoulder.getWorldPosition(scratch.a);
      const toTarget = scratch.b.copy(grab.target).sub(shoulderAt);
      const length = toTarget.length();
      const parentRotation = arm.shoulder.parent.getWorldQuaternion(scratch.q).invert();
      scratch.aim.setFromUnitVectors(DOWN, toTarget.applyQuaternion(parentRotation).normalize());
      arm.shoulder.quaternion.slerp(scratch.aim, grab.weight);
      arm.elbow.rotation.x *= 1 - grab.weight;
      extend = Math.max(0, length - ROBOT_ARM_LENGTH) * grab.weight;
    }
    arm.extension.scale.y = Math.max(1e-4, extend);
    arm.extension.position.y = -0.21 - extend / 2;
    arm.hand.position.y = -0.22 - extend;
  });
}

// ---------- Your hands (the first-person view model) ----------

const SKIN = 0xd9a07a;
const UP = v3(0, 1, 0);

// One of your hands: a jacket sleeve running back off-screen to your shoulder, a shirt cuff, and a hand.
function buildHumanHand(side) {
  const skin = standard(SKIN, { roughness: 0.65 });
  const group = new THREE.Group();
  // A domed back of the hand rather than a box.
  const palm = shadowed(new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), skin));
  palm.scale.set(0.042, 0.017, 0.05);
  group.add(palm);
  // Fingers held together and curled down onto the felt, like a hand at rest.
  [-0.0275, -0.0092, 0.0092, 0.0275].forEach((x, i) => {
    const finger = shadowed(new THREE.Mesh(new THREE.CapsuleGeometry(0.0094, 0.036 - Math.abs(i - 1.5) * 0.005, 4, 8), skin));
    finger.rotation.x = Math.PI / 2 + 0.85;
    finger.position.set(x, -0.012, -0.052);
    group.add(finger);
  });
  // The thumb: a fleshy base off the side of the palm near the wrist, then a jointed tip with a nail,
  // angled forward and in toward the other hand and resting low against the felt.
  const segment = (radius, length) => {
    const mesh = shadowed(new THREE.Mesh(new THREE.CapsuleGeometry(radius, length, 4, 10).rotateX(-Math.PI / 2), skin));
    mesh.position.z = -length / 2;
    return mesh;
  };
  const thumb = new THREE.Group();
  thumb.position.set(-side * 0.036, -0.006, -0.012);
  thumb.rotation.set(-0.3, side * 0.05, 0, "YXZ");
  thumb.add(segment(0.0112, 0.014));
  const tip = new THREE.Group();
  tip.position.z = -0.02;
  tip.rotation.set(-0.3, 0, 0, "YXZ");
  tip.add(segment(0.0092, 0.012));
  const nail = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), standard(0xf0cdbd, { roughness: 0.3 }));
  nail.scale.set(0.0062, 0.0016, 0.0075);
  nail.position.set(0, 0.0082, -0.015);
  tip.add(nail);
  thumb.add(tip);
  group.add(thumb);

  const sleeve = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 1, 18), standard(0x1d2433, { roughness: 0.8 })));
  const cuff = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.037, 0.03, 18), standard(0xf1ede4, { roughness: 0.7 })));
  return { group, sleeve, cuff, side };
}

// ---------- The room ----------

function carpetTexture() {
  return canvasTexture(256, 256, (ctx, w, h) => {
    ctx.fillStyle = "#3a0f18";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(215, 160, 80, 0.35)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(w / 2, 0);
    ctx.lineTo(w, h / 2);
    ctx.lineTo(w / 2, h);
    ctx.lineTo(0, h / 2);
    ctx.closePath();
    ctx.stroke();
    ctx.fillStyle = "rgba(215, 160, 80, 0.5)";
    [[w / 2, h / 2], [0, 0], [w, 0], [0, h], [w, h]].forEach(([x, y]) => {
      ctx.beginPath();
      ctx.arc(x, y, 12, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.fillStyle = "rgba(20, 90, 70, 0.6)";
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 6, 0, Math.PI * 2);
    ctx.fill();
  }, { repeat: [14, 12] });
}

function panelTexture() {
  return canvasTexture(256, 256, (ctx, w, h) => {
    ctx.fillStyle = "#2b1a14";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#3a241b";
    ctx.fillRect(18, 18, w - 36, h - 36);
    ctx.strokeStyle = "rgba(215, 182, 109, 0.25)";
    ctx.lineWidth = 3;
    ctx.strokeRect(30, 30, w - 60, h - 60);
  }, { repeat: [10, 1] });
}

function neonSign(text, color, width = 1024, height = 220, font = 150) {
  const texture = canvasTexture(width, height, (ctx, w, h) => {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `900 ${font}px Inter, system-ui, sans-serif`;
    ctx.shadowColor = color;
    for (const blur of [40, 20, 8]) {
      ctx.shadowBlur = blur;
      ctx.fillStyle = color;
      ctx.fillText(text, w / 2, h / 2);
    }
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#fff6fb";
    ctx.fillText(text, w / 2, h / 2);
  });
  return new THREE.Mesh(
    new THREE.PlaneGeometry(width / 300, height / 300),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, toneMapped: false, depthWrite: false }),
  );
}

function slotScreenTexture() {
  return canvasTexture(256, 160, (ctx, w, h) => {
    ctx.fillStyle = "#08131a";
    ctx.fillRect(0, 0, w, h);
    const symbols = ["7", "★", "◆", "7", "♣", "★"];
    for (let i = 0; i < 3; i += 1) {
      ctx.fillStyle = "#f4efe4";
      ctx.fillRect(16 + i * 78, 28, 68, 104);
      ctx.fillStyle = i === 1 ? "#d7b66d" : "#c8372d";
      ctx.font = "900 64px Inter, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(symbols[Math.floor(Math.random() * symbols.length)], 50 + i * 78, 82);
    }
  });
}

function buildRoom(scene, robots, ambient) {
  const carpet = new THREE.Mesh(
    new THREE.PlaneGeometry(16, 14).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ map: carpetTexture(), roughness: 1 }),
  );
  carpet.position.set(0, FLOOR_Y, -2);
  carpet.receiveShadow = true;
  scene.add(carpet);

  const panels = panelTexture();
  const upper = standard(0x1c1416, { roughness: 0.9 });
  const wall = (width, x, z, rotation) => {
    const group = new THREE.Group();
    const lower = new THREE.Mesh(new THREE.PlaneGeometry(width, 1.1), new THREE.MeshStandardMaterial({ map: panels, roughness: 0.7 }));
    lower.position.y = FLOOR_Y + 0.55;
    const top = new THREE.Mesh(new THREE.PlaneGeometry(width, 3), upper);
    top.position.y = FLOOR_Y + 2.6;
    const rail = new THREE.Mesh(new THREE.BoxGeometry(width, 0.06, 0.04), standard(0xb8934a, { metalness: 0.8, roughness: 0.3 }));
    rail.position.y = FLOOR_Y + 1.12;
    group.add(lower, top, rail);
    group.position.set(x, 0, z);
    group.rotation.y = rotation;
    scene.add(group);
  };
  wall(16, 0, -8.5, 0);
  wall(14, -7.5, -2, Math.PI / 2);
  wall(14, 7.5, -2, -Math.PI / 2);
  wall(16, 0, 4.5, Math.PI);

  const sign = neonSign("RL CASINO", "#ff4fb4");
  sign.position.set(0, 2.3, -8.45);
  scene.add(sign);
  const tagline = neonSign("HUMANS WELCOME*", "#4fe0ff", 1024, 160, 90);
  tagline.position.set(0, 1.7, -8.44);
  tagline.scale.setScalar(0.6);
  scene.add(tagline);
  const fineprint = neonSign("*for now", "#4fe0ff", 512, 120, 60);
  fineprint.position.set(1.55, 1.5, -8.43);
  fineprint.scale.setScalar(0.45);
  scene.add(fineprint);
  const pink = new THREE.PointLight(0xff4fb4, 6, 7, 1.6);
  pink.position.set(0, 2.2, -7.6);
  scene.add(pink);

  // Two more tables of robots grinding their own game.
  const backTables = [
    { x: -3.6, z: -3.6, felt: feltTexture("#1d5d8f", "#0e2f4d"), seats: 4 },
    { x: 3.7, z: -4.3, felt: feltTexture("#8f2a2a", "#4a1111"), seats: 5 },
  ];
  backTables.forEach(({ x, z, felt, seats }, tableIndex) => {
    const table = buildPokerTable(1.1, 0.66, felt);
    table.position.set(x, 0, z);
    scene.add(table);
    const lamp = pendantLamp();
    lamp.position.set(x, 1.5, z);
    scene.add(lamp);
    const light = new THREE.PointLight(0xffd9a0, 14, 7, 1.4);
    light.position.set(x, 1.2, z);
    scene.add(light);

    for (let i = 0; i < seats; i += 1) {
      const angle = (i / seats) * Math.PI * 2 + tableIndex;
      const robot = buildRobot(ROBOT_PALETTE[(i + tableIndex * 2 + 1) % ROBOT_PALETTE.length]);
      robot.root.position.set(x + Math.cos(angle) * 1.45, 0, z + Math.sin(angle) * 0.98);
      robot.root.rotation.y = Math.atan2(x - robot.root.position.x, z - robot.root.position.z);
      robot.ambient = true;
      scene.add(robot.root);
      robots.push(robot);

      const cards = new THREE.Group();
      [-1, 1].forEach((side) => {
        const card = cardMesh(null);
        card.quaternion.copy(Q_FACE_DOWN);
        card.position.set(side * 0.05, 0.002, 0);
        cards.add(card);
      });
      cards.position.set(x + Math.cos(angle) * 0.75, 0, z + Math.sin(angle) * 0.45);
      cards.rotation.y = robot.root.rotation.y;
      scene.add(cards);
      const pile = new THREE.Group();
      pile.position.set(x + Math.cos(angle + 0.3) * 0.8, 0, z + Math.sin(angle + 0.3) * 0.5);
      layoutStack(pile, Math.round(rand(300, 2500)));
      scene.add(pile);
    }
    const pot = new THREE.Group();
    pot.position.set(x, 0, z);
    layoutStack(pot, Math.round(rand(200, 900)));
    scene.add(pot);
  });

  // The bar, with a robot bartender polishing glasses.
  const bar = new THREE.Group();
  bar.position.set(-6.1, 0, -3.5);
  const wood = standard(0x4a2b1b, { roughness: 0.45 });
  const counter = shadowed(new THREE.Mesh(new THREE.BoxGeometry(0.7, 1.1, 4.4), wood), true);
  counter.position.y = FLOOR_Y + 0.55;
  const top = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.06, 4.5), standard(0x1a1a1a, { metalness: 0.6, roughness: 0.2 }));
  top.position.y = FLOOR_Y + 1.13;
  const shelfGlow = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 4.2), glow(0xffb35c, 3));
  shelfGlow.position.set(-1.33, 0.95, 0);
  bar.add(counter, top, shelfGlow);
  for (let i = 0; i < 18; i += 1) {
    const bottle = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.04, rand(0.22, 0.32), 10),
      new THREE.MeshStandardMaterial({ color: [0x2f8f4e, 0x8f5a2a, 0x2a4f8f, 0xa83232][i % 4], roughness: 0.1, metalness: 0.2, emissive: 0x221100, transparent: true, opacity: 0.85 }),
    );
    bottle.position.set(-1.33, 1.1, -2 + i * 0.235);
    bar.add(bottle);
  }
  scene.add(bar);
  const barLight = new THREE.PointLight(0xffb35c, 4, 5, 1.6);
  barLight.position.set(-6.4, 1.4, -3.5);
  scene.add(barLight);
  const barSign = neonSign("BAR", "#ffb35c", 512, 200, 140);
  barSign.position.set(-7.45, 1.9, -3.5);
  barSign.rotation.y = Math.PI / 2;
  scene.add(barSign);
  const bartender = buildRobot(ROBOT_PALETTE[2], { chair: false, hover: true });
  bartender.root.position.set(-6.85, 0.36, -3.2);
  bartender.root.rotation.y = Math.PI / 2;
  bartender.ambient = true;
  bartender.polish = true;
  scene.add(bartender.root);
  robots.push(bartender);

  // Slot machines along the right wall.
  for (let i = 0; i < 4; i += 1) {
    const slot = new THREE.Group();
    slot.position.set(7.0, FLOOR_Y, -6 + i * 1.1);
    slot.rotation.y = -Math.PI / 2;
    const cabinet = shadowed(new THREE.Mesh(roundedBox(0.8, 1.7, 0.7, 0.06), standard(0x6d1f2d, { metalness: 0.5, roughness: 0.35 })));
    cabinet.position.y = 0.85;
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.56, 0.36), new THREE.MeshBasicMaterial({ map: slotScreenTexture(), toneMapped: false }));
    screen.position.set(0, 1.15, 0.356);
    const crown = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.12, 0.72), glow(0xffd35c, 2));
    crown.position.y = 1.76;
    slot.add(cabinet, screen, crown);
    scene.add(slot);
    ambient.push((t) => {
      crown.material.emissiveIntensity = 1 + (Math.sin(t * 5 + i * 1.7) > 0.6 ? 3 : 0.5);
      if (Math.random() < 0.004) screen.material.map = slotScreenTexture();
    });
  }
  const slotLight = new THREE.PointLight(0xffd35c, 3, 5, 1.6);
  slotLight.position.set(6.2, 1.2, -4.4);
  scene.add(slotLight);

  // A waiter bot gliding laps around the floor.
  const waiter = buildRobot(ROBOT_PALETTE[1], { chair: false, hover: true });
  waiter.ambient = true;
  const tray = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.015, 24), standard(0xc0c0c0, { metalness: 0.9, roughness: 0.2 }));
  tray.position.set(0.28, 0.12, 0.25);
  waiter.torso.add(tray);
  [0x8f2a2a, 0xd7b66d].forEach((color, i) => {
    const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.018, 0.09, 10), new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.8 }));
    glass.position.set(0.24 + i * 0.07, 0.17, 0.25);
    waiter.torso.add(glass);
  });
  scene.add(waiter.root);
  robots.push(waiter);
  ambient.push((t) => {
    const angle = t * 0.16;
    const x = Math.cos(angle) * 2.6;
    const z = -5.6 + Math.sin(angle) * 1.0;
    waiter.root.position.set(x, 0.36 + Math.sin(t * 2.4) * 0.02, z);
    waiter.root.rotation.y = Math.atan2(-Math.sin(angle) * 2.6, Math.cos(angle) * 1.0);
  });
}

// ---------- Cards and chips on the main table ----------

const cardGeometry = new THREE.PlaneGeometry(CARD_W, CARD_H);
const chipGeometry = new THREE.CylinderGeometry(CHIP_R, CHIP_R, CHIP_H, 28);

function cardMesh(card) {
  const group = new THREE.Group();
  const front = new THREE.Mesh(cardGeometry, new THREE.MeshStandardMaterial({
    map: card ? cardFaceTexture(card) : cardBackTexture(), roughness: 0.55, alphaTest: 0.5,
  }));
  front.position.z = 0.0006;
  const back = new THREE.Mesh(cardGeometry, new THREE.MeshStandardMaterial({ map: cardBackTexture(), roughness: 0.55, alphaTest: 0.5 }));
  back.rotation.y = Math.PI;
  back.position.z = -0.0006;
  front.castShadow = true;
  back.castShadow = true;
  group.add(front, back);
  group.userData.front = front;
  return group;
}

function chipMesh(value, seed = Math.random()) {
  const mesh = new THREE.Mesh(chipGeometry, chipMaterials(value));
  mesh.rotation.y = seed * Math.PI * 2;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

// Lays a stack out as columns of up to ten chips, three columns to a row. Every chip of one value in a
// stack is a single instanced draw, since chips are most of what the scene draws.
const chipPlacement = { matrix: new THREE.Matrix4(), position: new THREE.Vector3(), rotation: new THREE.Quaternion(), scale: new THREE.Vector3(1, 1, 1) };
function layoutStack(group, amount) {
  group.children.forEach((child) => child.dispose?.());
  group.clear();
  const columns = chipBreakdown(amount).flatMap(({ value, count }) => {
    const out = [];
    for (let left = count; left > 0; left -= MAX_CHIPS_PER_COLUMN) out.push({ value, shown: Math.min(left, MAX_CHIPS_PER_COLUMN) });
    return out;
  }).slice(0, MAX_COLUMNS);
  const perRow = 3;
  const gap = CHIP_R * 2.15;
  const byValue = new Map();
  columns.forEach(({ value, shown }, index) => {
    const row = Math.floor(index / perRow);
    const inRow = Math.min(perRow, columns.length - row * perRow);
    const x = ((index % perRow) - (inRow - 1) / 2) * gap;
    const z = row * gap;
    if (!byValue.has(value)) byValue.set(value, []);
    for (let i = 0; i < shown; i += 1) {
      const seed = Math.sin((index + 1) * 12.9898 + i * 78.233) * 43758.5453;
      const spin = seed - Math.floor(seed);
      const jitter = (spin - 0.5) * 0.003;
      const { matrix, position, rotation, scale } = chipPlacement;
      position.set(x + jitter, CHIP_H / 2 + i * CHIP_H, z - jitter);
      rotation.setFromAxisAngle(UP, spin * Math.PI * 2);
      byValue.get(value).push(matrix.compose(position, rotation, scale).clone());
    }
  });
  byValue.forEach((matrices, value) => {
    const chips = new THREE.InstancedMesh(chipGeometry, chipMaterials(value), matrices.length);
    matrices.forEach((matrix, i) => chips.setMatrixAt(i, matrix));
    chips.castShadow = true;
    chips.receiveShadow = true;
    group.add(chips);
  });
  group.userData.height = Math.max(0, ...columns.map((c) => c.shown)) * CHIP_H;
}

// ---------- Public API ----------

export function createTable(container) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch (error) {
    container.innerHTML = `<p class="no-webgl">This table needs WebGL, and your browser didn't give us any.</p>`;
    throw error;
  }
  maxAnisotropy = renderer.capabilities.getMaxAnisotropy();
  // Full Retina resolution is four times the pixels for text you mostly read in the HTML overlays anyway.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.shadowMap.enabled = true;
  // Shadows only get recomputed on frames where something on the table is moving (see frame()).
  renderer.shadowMap.autoUpdate = false;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0809);
  scene.fog = new THREE.Fog(0x0b0809, 6, 15);

  const camera = new THREE.PerspectiveCamera(54, 1, 0.05, 40);
  const lookTarget = v3(0, 0.05, -0.3);
  const pointer = { x: 0, y: 0 };

  scene.add(new THREE.HemisphereLight(0xa596b0, 0x2a1510, 1.1));
  const spot = new THREE.SpotLight(0xffe2b0, 38, 6, 0.75, 0.55, 1.6);
  spot.position.set(0, 2.2, 0);
  spot.target.position.set(0, 0, 0);
  spot.castShadow = true;
  spot.shadow.mapSize.set(2048, 2048);
  spot.shadow.bias = -0.0004;
  spot.shadow.radius = 4;
  scene.add(spot, spot.target);
  const lamp = pendantLamp();
  lamp.position.set(0, 1.72, -0.05);
  lamp.traverse((mesh) => { mesh.castShadow = false; });
  scene.add(lamp);

  const mainTable = buildPokerTable(TABLE_A, TABLE_B, feltTexture("#1c7a5f", "#0d3d31"));
  scene.add(mainTable);

  const robots = [];
  const ambient = [];
  buildRoom(scene, robots, ambient);

  const opponent = buildRobot(ROBOT_PALETTE[0]);
  opponent.root.position.set(0, 0.1, -1.0);
  scene.add(opponent.root);
  robots.push(opponent);

  // Deck, dealer button, and a ring that marks whose turn it is.
  const deck = new THREE.Group();
  for (let i = 0; i < 12; i += 1) {
    const card = cardMesh(null);
    card.quaternion.copy(Q_FACE_DOWN);
    card.position.y = 0.001 + i * 0.0012;
    card.rotation.z = rand(-0.03, 0.03);
    deck.add(card);
  }
  deck.position.copy(SPOTS.deck);
  deck.rotation.y = 0.35;
  scene.add(deck);
  const deckTop = SPOTS.deck.clone().setY(0.02);

  const button = new THREE.Mesh(
    new THREE.CylinderGeometry(0.032, 0.032, 0.01, 32),
    [
      standard(0xe8e4da),
      new THREE.MeshStandardMaterial({ map: canvasTexture(128, 128, (ctx, w) => {
        ctx.fillStyle = "#f4f1e8";
        ctx.fillRect(0, 0, w, w);
        ctx.fillStyle = "#191714";
        ctx.font = "900 72px Inter, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        // Cylinder caps map the canvas a quarter turn round; turn the letter back so it faces you.
        ctx.translate(w / 2, w / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText("D", 0, 4);
      }), roughness: 0.4 }),
      standard(0xe8e4da),
    ],
  );
  button.castShadow = true;
  button.position.copy(SPOTS.dealer[0]).setY(0.005);
  scene.add(button);

  const turnRing = new THREE.Mesh(
    new THREE.RingGeometry(0.13, 0.15, 64).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0xe3c47e, transparent: true, opacity: 0, toneMapped: false, depthWrite: false }),
  );
  turnRing.scale.set(1.25, 1, 0.85);
  turnRing.position.y = 0.002;
  scene.add(turnRing);
  let turnSeat = null;

  const stacks = {
    pile: SPOTS.pile.map((spot) => stackGroup(spot)),
    bet: SPOTS.bet.map((spot) => stackGroup(spot)),
    pot: stackGroup(SPOTS.pot),
  };
  function stackGroup(spot) {
    const group = new THREE.Group();
    group.position.copy(spot);
    group.userData.amount = 0;
    group.userData.height = 0;
    scene.add(group);
    return group;
  }
  function setStackGroup(group, amount) {
    if (group.userData.amount === amount) return;
    group.userData.amount = amount;
    layoutStack(group, amount);
  }
  const stackFor = (where) => (where === "pot" ? stacks.pot : stacks[where.pile !== undefined ? "pile" : "bet"][where.pile ?? where.bet]);

  // ---------- Tweens ----------

  const tweens = new Set();
  function tween(duration, update, { delay = 0, ease = easeOutCubic } = {}) {
    return new Promise((resolve) => {
      tweens.add({ start: performance.now() + delay, duration, update, ease, resolve });
    });
  }
  function runTweens(now) {
    tweens.forEach((item) => {
      if (now < item.start) return;
      const t = Math.min(1, (now - item.start) / item.duration);
      item.update(item.ease(t));
      if (t >= 1) {
        tweens.delete(item);
        item.resolve();
      }
    });
  }

  // ---------- Chips ----------

  function flyChips(from, to, amount, { arc = 0.12, count = 8, spread = 0.02 } = {}) {
    const source = stackFor(from);
    const target = stackFor(to);
    const values = chipBreakdown(amount).flatMap(({ value, count: n }) => Array(Math.min(n, 4)).fill(value));
    const total = Math.max(1, Math.min(count, values.length || 1));
    const flights = [];
    for (let i = 0; i < total; i += 1) {
      const chip = chipMesh(values[i % values.length] ?? 5);
      const start = source.position.clone().add(v3(rand(-spread, spread), source.userData.height + CHIP_H, rand(-spread, spread)));
      const end = target.position.clone().add(v3(rand(-spread, spread), target.userData.height + CHIP_H * (i + 1), rand(-spread, spread)));
      const mid = start.clone().lerp(end, 0.5).setY(Math.max(start.y, end.y) + arc);
      const spin = rand(-6, 6);
      chip.visible = false;
      scene.add(chip);
      flights.push(tween(520, (t) => {
        chip.visible = true;
        const a = start.clone().lerp(mid, t);
        const b = mid.clone().lerp(end, t);
        chip.position.copy(a.lerp(b, t));
        chip.rotation.set(Math.sin(t * Math.PI) * 0.6, spin * t, 0);
      }, { delay: i * 55, ease: (t) => 1 - (1 - t) ** 2 }).then(() => scene.remove(chip)));
    }
    return Promise.all(flights);
  }

  // ---------- Cards ----------

  const hands = [[], []];
  let board = [];
  const handState = [{ keys: [], folded: false, round: null }, { keys: [], folded: false, round: null }];

  function handSlot(seat, index) {
    const base = SPOTS.hand[seat];
    const side = index === 0 ? -1 : 1;
    if (seat === 0) {
      // Your cards lean back toward you, like you're peeking at them.
      const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2 + HUMAN_TILT, side * -0.08, 0, "YXZ"));
      return { position: v3(base.x + side * 0.052, Math.sin(HUMAN_TILT) * CARD_H / 2 + 0.004, base.z + Math.abs(side) * 0.004), quaternion };
    }
    const quaternion = Q_FACE_DOWN.clone().premultiply(new THREE.Quaternion().setFromAxisAngle(v3(0, 1, 0), side * 0.06));
    return { position: v3(base.x + side * 0.052, 0.002 + index * 0.001, base.z), quaternion };
  }

  function dealTo(mesh, slot, delay) {
    mesh.position.copy(deckTop);
    mesh.quaternion.copy(Q_FACE_DOWN);
    mesh.visible = false;
    scene.add(mesh);
    const startQ = Q_FACE_DOWN.clone().premultiply(new THREE.Quaternion().setFromAxisAngle(v3(0, 1, 0), 0.35));
    mesh.userData.base = slot;
    return tween(420, (t) => {
      mesh.visible = true;
      mesh.position.lerpVectors(deckTop, slot.position, t);
      mesh.position.y += Math.sin(t * Math.PI) * 0.09;
      mesh.quaternion.slerpQuaternions(startQ, slot.quaternion, t);
    }, { delay, ease: easeInOut });
  }

  function removeCards(meshes) {
    meshes.forEach((mesh) => scene.remove(mesh));
  }

  function muck(meshes, remove) {
    return Promise.all(meshes.map((mesh, i) => {
      const from = mesh.position.clone();
      const fromQ = mesh.quaternion.clone();
      const to = SPOTS.muck.clone().add(v3(i * 0.015 - 0.008, 0.003 + i * 0.001, (from.z > 0 ? 1 : -1) * 0.04));
      const toQ = Q_FACE_DOWN.clone().premultiply(new THREE.Quaternion().setFromAxisAngle(v3(0, 1, 0), rand(-0.6, 0.6)));
      mesh.userData.base = { position: to, quaternion: toQ };
      return tween(380, (t) => {
        mesh.position.lerpVectors(from, to, t);
        mesh.position.y += Math.sin(t * Math.PI) * 0.03;
        mesh.quaternion.slerpQuaternions(fromQ, toQ, t);
      }, { delay: i * 60 });
    })).then(() => remove && removeCards(meshes));
  }

  function flip(mesh, card, slot) {
    mesh.userData.front.material.map = cardFaceTexture(card);
    mesh.userData.front.material.needsUpdate = true;
    const from = mesh.position.clone();
    const fromQ = mesh.quaternion.clone();
    const faceUp = Q_FACE_UP.clone().premultiply(new THREE.Quaternion().setFromAxisAngle(v3(0, 1, 0), 0));
    mesh.userData.base = { position: slot.position, quaternion: faceUp };
    return tween(420, (t) => {
      mesh.position.copy(from);
      mesh.position.y += Math.sin(t * Math.PI) * 0.06;
      mesh.quaternion.slerpQuaternions(fromQ, faceUp, t);
    }, { ease: easeInOut });
  }

  const keyOf = (card) => `${card.rank}-${card.suit}-${card.value}`;

  // cards: what the server shows for this seat; hidden: draw face-down backs when the cards aren't shown.
  // round: the hand number, so two face-down hands in a row still get dealt fresh.
  function setHand(seat, cards, { hidden = false, folded = false, round = null, delay = 0, stagger = 170 } = {}) {
    const keys = cards.length ? cards.map(keyOf) : hidden ? ["back", "back"] : [];
    const state = handState[seat];
    const current = hands[seat];
    const same = round === state.round && keys.length === state.keys.length && keys.every((key, i) => key === state.keys[i]);

    if (!same) {
      const revealing = round === state.round && state.keys.length === 2 && state.keys.every((key) => key === "back") && cards.length === 2;
      if (revealing && !state.folded) {
        cards.forEach((card, i) => {
          current[i].userData.key = keys[i];
          flip(current[i], card, handSlot(seat, i));
        });
      } else if (!keys.length && (state.folded || round !== state.round)) {
        // Already in the muck; clear it when the hand is over.
        removeCards(current);
        hands[seat] = [];
      } else if (!keys.length && state.keys.length) {
        foldCards(seat, current, true);
        hands[seat] = [];
      } else {
        removeCards(current);
        hands[seat] = keys.map((key, i) => {
          const mesh = cardMesh(cards[i] ?? null);
          mesh.userData.key = key;
          dealTo(mesh, handSlot(seat, i), delay + i * stagger * 2);
          return mesh;
        });
      }
      handState[seat] = { keys, folded: false, round };
    }
    if (folded && !handState[seat].folded && hands[seat].length) {
      handState[seat].folded = true;
      foldCards(seat, hands[seat], false);
    }
  }

  function setBoard(cards, { stagger = 170 } = {}) {
    const keys = cards.map(keyOf);
    if (keys.length < board.length || board.some((mesh, i) => mesh.userData.key !== keys[i])) {
      removeCards(board);
      board = [];
    }
    let dealt = 0;
    for (let i = board.length; i < cards.length; i += 1) {
      const mesh = cardMesh(cards[i]);
      mesh.userData.key = keys[i];
      dealTo(mesh, { position: boardSpot(i).setY(0.002), quaternion: Q_FACE_UP.clone() }, dealt * stagger);
      board.push(mesh);
      dealt += 1;
    }
  }

  // Winning cards lift and glow; everything else on the table dims.
  function highlight(winningKeys) {
    const all = [...hands[0], ...hands[1], ...board];
    const any = winningKeys && winningKeys.size > 0;
    all.forEach((mesh) => {
      const material = mesh.userData.front.material;
      const wins = any && winningKeys.has(mesh.userData.key);
      material.color.setScalar(any && !wins ? 0.42 : 1);
      material.emissive.setHex(wins ? 0x6b5320 : 0x000000);
      material.emissiveIntensity = wins ? 0.6 : 0;
      const base = mesh.userData.base;
      if (!base) return;
      const lift = wins ? 0.018 : 0;
      if (mesh.userData.lift === lift) return;
      mesh.userData.lift = lift;
      const from = mesh.position.y;
      tween(240, (t) => { mesh.position.y = from + (base.position.y + lift - from) * t; });
    });
  }

  function setActive(seat) {
    turnSeat = seat === 0 || seat === 1 ? seat : null;
    if (turnSeat !== null) turnRing.position.set(SPOTS.hand[turnSeat].x, 0.002, SPOTS.hand[turnSeat].z);
  }

  function setDealer(seat) {
    const from = button.position.clone();
    const to = SPOTS.dealer[seat].clone().setY(0.005);
    if (from.distanceTo(to) < 0.001) return;
    tween(600, (t) => {
      button.position.lerpVectors(from, to, t);
      button.position.y += Math.sin(t * Math.PI) * 0.04;
    }, { ease: easeInOut });
  }

  // ---------- Hands: yours and the robot's, both actually moving chips and cards ----------

  const HAND_REST = [v3(-0.2, 0.034, 0.58), v3(0.23, 0.034, 0.6)];
  const SHOULDERS = [v3(-0.4, 0.18, 1.2), v3(0.4, 0.18, 1.2)];
  const yourHands = [0, 1].map((i) => {
    const hand = buildHumanHand(i === 0 ? -1 : 1);
    scene.add(hand.group, hand.sleeve, hand.cuff);
    return { kind: "human", hand, shoulder: SHOULDERS[i], restAt: HAND_REST[i], wrist: HAND_REST[i].clone(), token: 0, held: null, grip: 0.02 };
  });
  const robotHand = { kind: "robot", side: -1, token: 0, held: null, grip: 0.006 };
  // Seat 0 is you, working with your right hand; seat 1 is the robot, using the arm on its stack's side.
  const actors = [yourHands[1], robotHand];
  const robotArm = () => opponent.arms.find((arm) => arm.side === robotHand.side);

  function handPoint(actor) {
    return actor.kind === "robot" ? robotArm().tip.getWorldPosition(new THREE.Vector3()) : actor.wrist.clone();
  }

  // Moves a hand to a point on the table along a small arc. A newer move on the same hand takes over.
  function reach(actor, target, ms) {
    const token = ++actor.token;
    const from = handPoint(actor);
    if (actor.kind === "robot") {
      const weight = opponent.grab?.weight ?? 0;
      opponent.grab = { side: actor.side, target: from.clone(), weight };
      return tween(ms, (t) => {
        if (actor.token !== token) return;
        opponent.grab.target.lerpVectors(from, target, t);
        opponent.grab.target.y += Math.sin(t * Math.PI) * 0.05;
        opponent.grab.weight = weight + (1 - weight) * Math.min(1, t * 2);
      }, { ease: easeInOut });
    }
    return tween(ms, (t) => {
      if (actor.token !== token) return;
      actor.wrist.lerpVectors(from, target, t);
      actor.wrist.y += Math.sin(t * Math.PI) * 0.04;
    }, { ease: easeInOut });
  }

  function rest(actor, ms = 420) {
    const token = ++actor.token;
    if (actor.kind === "robot") {
      const weight = opponent.grab?.weight ?? 0;
      if (!weight) return Promise.resolve();
      return tween(ms, (t) => {
        if (actor.token === token) opponent.grab.weight = weight * (1 - t);
      }, { ease: easeInOut });
    }
    return reach(actor, actor.restAt, ms);
  }

  function heldStack(amount) {
    const group = new THREE.Group();
    const values = chipBreakdown(amount).flatMap(({ value, count }) => Array(Math.min(count, 3)).fill(value)).slice(0, 6);
    values.forEach((value, i) => {
      const chip = chipMesh(value);
      chip.position.y = CHIP_H / 2 + i * CHIP_H;
      group.add(chip);
    });
    group.userData.height = values.length * CHIP_H;
    return group;
  }

  // Picks chips up off one stack and sets them down on another. onGrab fires as they leave the source.
  async function carry(seat, from, to, amount, { onGrab } = {}) {
    const actor = actors[seat];
    const source = stackFor(from);
    const target = stackFor(to);
    await reach(actor, source.position.clone().setY(source.userData.height + actor.grip), 360);
    onGrab?.();
    const held = heldStack(amount);
    scene.add(held);
    actor.held = held;
    await reach(actor, target.position.clone().setY(target.userData.height + held.userData.height + actor.grip), 440);
    scene.remove(held);
    actor.held = null;
    rest(actor);
  }

  // A hand slides the cards forward into the muck.
  async function foldCards(seat, meshes, remove) {
    const actor = actors[seat];
    await reach(actor, SPOTS.hand[seat].clone().setY(actor.grip + 0.012), 260);
    reach(actor, SPOTS.muck.clone().setY(actor.grip + 0.012), 380);
    await muck(meshes, remove);
    rest(actor);
  }

  // Two knuckle taps on the felt for a check.
  function tap(seat) {
    if (seat === 1) {
      return tween(520, (t) => { opponent.tap = t; }, { ease: (t) => t }).then(() => { opponent.tap = 0; });
    }
    const actor = actors[0];
    const token = ++actor.token;
    const base = actor.restAt.clone().add(v3(-0.06, 0, -0.06));
    return tween(560, (t) => {
      if (actor.token !== token) return;
      actor.wrist.copy(base);
      actor.wrist.y += Math.abs(Math.sin(t * Math.PI * 2)) * 0.035;
    }, { ease: (t) => t }).then(() => rest(actor, 260));
  }

  // Lays the sleeve from your shoulder to the cuff and points the hand along it; carried chips ride under the hand.
  const sleeveDir = new THREE.Vector3();
  function poseHands(t) {
    yourHands.forEach((actor, i) => {
      const { group, sleeve, cuff, side } = actor.hand;
      const at = actor.wrist.clone();
      at.y += Math.sin(t * 1.3 + i * 2) * 0.0015;
      group.position.copy(at);
      sleeveDir.copy(at).sub(actor.shoulder);
      group.rotation.set(-0.22, Math.atan2(-sleeveDir.x, -sleeveDir.z), side * 0.08, "YXZ");
      sleeveDir.normalize();
      const cuffAt = at.clone().addScaledVector(sleeveDir, -0.06);
      const length = cuffAt.distanceTo(actor.shoulder);
      sleeve.position.copy(actor.shoulder).lerp(cuffAt, 0.5).addScaledVector(sleeveDir, -0.015);
      sleeve.quaternion.setFromUnitVectors(UP, sleeveDir);
      sleeve.scale.set(1, length, 1);
      cuff.position.copy(cuffAt);
      cuff.quaternion.copy(sleeve.quaternion);
    });
    actors.forEach((actor) => {
      if (!actor.held) return;
      const point = handPoint(actor);
      actor.held.position.copy(point).setY(point.y - actor.held.userData.height - (actor.kind === "human" ? 0.012 : 0));
    });
  }

  const robot = {
    mood(name) {
      opponent.mood = name;
    },
  };

  // ---------- Bird's-eye view ----------

  // What each top-down framing has to fit: your hand plus the board, or the robot's hand plus the board.
  const TOP_FRAMES = { mine: [-0.2, 0.62], theirs: [-0.62, 0.04] };
  // Screen space the top bar and the action dock cover, so framed cards don't hide under them.
  const RESERVED = { top: 76, bottom: 120 };
  const view = { top: false, blend: 0, frame: "mine", zoom: 1 };
  const viewListeners = [];
  const topPos = new THREE.Vector3();
  const topLook = new THREE.Vector3();

  function updateTopCamera() {
    const height = container.clientHeight;
    const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const [z0, z1] = TOP_FRAMES[view.frame];
    const usable = Math.max(0.4, (height - RESERVED.top - RESERVED.bottom) / height);
    const lift = Math.max((z1 - z0) / 2 / (tan * usable), 0.42 / (tan * camera.aspect)) * view.zoom;
    const metresPerPixel = (2 * lift * tan) / height;
    const z = (z0 + z1) / 2 + ((RESERVED.bottom - RESERVED.top) / 2) * metresPerPixel;
    topPos.set(0, lift, z);
    topLook.set(0, 0, z);
  }

  function setView(top, frame = "mine") {
    if (top === view.top && (!top || frame === view.frame)) return;
    view.top = top;
    if (top) {
      view.frame = frame;
      view.zoom = 1;
    }
    const from = view.blend;
    tween(700, (t) => { view.blend = from + ((top ? 1 : 0) - from) * t; }, { ease: easeInOut });
    viewListeners.forEach((listener) => listener(top));
  }

  // Invisible click targets over each hand and the board, a bit bigger than the cards so they're easy to hit.
  const hitPads = [
    { frame: "mine", at: SPOTS.hand[0], size: [0.3, 0.22], has: () => hands[0].length },
    { frame: "theirs", at: SPOTS.hand[1], size: [0.3, 0.2], has: () => hands[1].length },
    { frame: "mine", at: boardSpot(2), size: [0.6, 0.2], has: () => board.length },
  ].map((pad) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(...pad.size).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ visible: false }));
    mesh.position.copy(pad.at).setY(0.03);
    mesh.userData.pad = pad;
    scene.add(mesh);
    return mesh;
  });

  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  function cardUnder(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const pad = raycaster.intersectObjects(hitPads, false)[0]?.object.userData.pad;
    return pad?.has() ? pad : null;
  }
  renderer.domElement.addEventListener("click", (event) => {
    if (view.top) {
      setView(false);
      return;
    }
    const pad = cardUnder(event);
    if (pad) setView(true, pad.frame);
  });
  renderer.domElement.addEventListener("pointermove", (event) => {
    renderer.domElement.style.cursor = view.top ? "zoom-out" : cardUnder(event) ? "zoom-in" : "";
  });
  renderer.domElement.addEventListener("wheel", (event) => {
    if (view.top) view.zoom = THREE.MathUtils.clamp(view.zoom * (event.deltaY > 0 ? 1.08 : 0.93), 0.55, 1.9);
  }, { passive: true });

  // ---------- Overlays, camera, loop ----------

  const overlays = [...document.querySelectorAll("[data-anchor]")].map((el) => ({
    el,
    anchor: ANCHORS[el.dataset.anchor],
    topAnchor: TOP_ANCHORS[el.dataset.anchor] ?? ANCHORS[el.dataset.anchor],
    start: el.classList.contains("start"),
    pinned: el.hasAttribute("data-pin"),
  }));
  const projected = new THREE.Vector3();
  const EDGE = 8;
  // Projects each overlay onto its spot, nudged back on screen when the spot is near an edge.
  // Pinned overlays (the robot's name and speech) also stay on screen when the camera looks away from it.
  function placeOverlays(width, height) {
    const sizes = overlays.map(({ el }) => [el.firstElementChild?.offsetWidth ?? 0, el.firstElementChild?.offsetHeight ?? 0]);
    overlays.forEach(({ el, anchor, topAnchor, start, pinned }, i) => {
      projected.lerpVectors(anchor, topAnchor, view.blend).project(camera);
      let x = (projected.x * 0.5 + 0.5) * width;
      let y = (-projected.y * 0.5 + 0.5) * height;
      const [w, h] = sizes[i];
      const low = start ? EDGE : EDGE + w / 2;
      const high = start ? width - EDGE - w : width - EDGE - w / 2;
      if (w && high > low) x = Math.min(high, Math.max(low, x));
      if (pinned && h) y = Math.min(height - RESERVED.bottom - h / 2, Math.max(RESERVED.top + h / 2, y));
      el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
    });
  }

  const cameraHome = v3(0, 0.8, 1.55);
  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height, false);
    const aspect = width / height;
    camera.aspect = aspect;
    // Narrow screens back the seat up and look down more steeply, so the whole felt still fits.
    const narrow = Math.max(0, Math.min(1, (1.25 - aspect) / 0.8));
    camera.fov = 54 + narrow * 14;
    cameraHome.set(0, 0.8 + narrow * 0.85, 1.55 - narrow * 0.2);
    lookTarget.set(0, 0.05 - narrow * 0.25, -0.3);
    camera.updateProjectionMatrix();
  }
  // Full frame rate only while something is actually moving; otherwise the room ticks over slowly.
  const IDLE_FPS = 10;
  const ACTIVE_GRACE_MS = 600;
  let activeUntil = 0;
  let lastFrame = 0;
  const wake = () => { activeUntil = performance.now() + ACTIVE_GRACE_MS; };

  window.addEventListener("resize", () => {
    resize();
    wake();
  });
  window.addEventListener("pointermove", (event) => {
    pointer.x = event.clientX / window.innerWidth - 0.5;
    pointer.y = event.clientY / window.innerHeight - 0.5;
    wake();
  });
  renderer.domElement.addEventListener("wheel", wake, { passive: true });
  resize();

  const clock = new THREE.Clock();
  const look = new THREE.Vector3();
  function frame(now) {
    requestAnimationFrame(frame);
    const busy = tweens.size > 0 || ["thinking", "happy"].includes(opponent.mood);
    const active = busy || now < activeUntil;
    if (!active && now - lastFrame < 1000 / IDLE_FPS) return;
    if (busy) wake();
    lastFrame = now;
    renderer.shadowMap.needsUpdate = active;

    const dt = Math.min(0.12, clock.getDelta());
    const t = clock.elapsedTime;
    runTweens(now);
    robots.forEach((r) => {
      if (r.ambient) {
        // Background bots fidget: reach for chips now and then, look around, the bartender polishes.
        if (Math.random() < dt * 0.25) r.mood = Math.random() < 0.25 ? "thinking" : "idle";
        r.reach = r.polish ? 0.5 + Math.sin(t * 3) * 0.3 : Math.max(0, Math.sin(t * 0.7 + r.seed * 3) - 0.85) * 6;
      }
      animateRobot(r, t, dt);
    });
    ambient.forEach((update) => update(t));

    const pulse = 0.35 + Math.sin(t * 3) * 0.2;
    turnRing.material.opacity = damp(turnRing.material.opacity, turnSeat === null ? 0 : pulse, 6, dt);

    poseHands(t);

    // Breathing, plus a little parallax from the mouse so the room feels like it's around you,
    // blended into the straight-down camera when you're looking at the cards from above.
    const b = view.blend;
    const sway = 1 - b;
    updateTopCamera();
    camera.position.set(
      cameraHome.x + pointer.x * 0.08 * sway,
      cameraHome.y + (Math.sin(t * 0.8) * 0.004 - pointer.y * 0.03) * sway,
      cameraHome.z,
    ).lerp(topPos, b);
    camera.position.y += Math.sin(b * Math.PI) * 0.2;
    look.copy(lookTarget).add(v3(pointer.x * 0.12 * sway, -pointer.y * 0.05 * sway, 0)).lerp(topLook, b);
    camera.up.set(0, 1 - b, -b).normalize();
    // The camera rises past the lamp over the table when it goes overhead.
    lamp.visible = b < 0.3;
    camera.lookAt(look);
    renderer.render(scene, camera);
    placeOverlays(container.clientWidth, container.clientHeight);
  }
  requestAnimationFrame(frame);
  wake();

  return {
    setStack: (seat, amount) => setStackGroup(stacks.pile[seat], amount),
    setBet: (seat, amount) => setStackGroup(stacks.bet[seat], amount),
    setPot: (amount) => setStackGroup(stacks.pot, amount),
    flyChips,
    carry,
    tap,
    setHand,
    setBoard,
    highlight,
    setActive,
    setDealer,
    robot,
    toggleView: () => setView(!view.top),
    leaveTopView: () => setView(false),
    inTopView: () => view.top,
    onViewChange: (listener) => viewListeners.push(listener),
  };
}
