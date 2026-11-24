import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const MODEL_URL = '../../chloe_detroit_become_human.glb';
const host = document.querySelector('#scene');
const status = document.querySelector('#status');
const details = document.querySelector('#details');
const animateToggle = document.querySelector('#animate');
const frameButton = document.querySelector('#frame');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x101820);

const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 1000);
camera.up.set(0, 1, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.setClearColor(0x101820, 1);
host.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xe7f4ff, 0x425263, 2.1));
const key = new THREE.DirectionalLight(0xfff1df, 3.3);
key.position.set(3, 5, 6);
scene.add(key);
const fill = new THREE.DirectionalLight(0x8dbfe8, 1.7);
fill.position.set(-4, 2, -3);
scene.add(fill);
const rim = new THREE.DirectionalLight(0x74d8f2, 2.2);
rim.position.set(0, 3, -5);
scene.add(rim);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.target.set(0, 1, 0);
controls.minDistance = 0.25;
controls.maxDistance = 40;

let modelRoot = null;
let mixer = null;
let bounds = null;
let activeAction = null;
let previousFrameAt = performance.now();

function frameModel() {
  if (!bounds) return;
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z);
  const verticalHalfFov = THREE.MathUtils.degToRad(camera.fov * 0.5);
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * camera.aspect);
  const distance = 1.28 * Math.max(
    size.y * 0.5 / Math.tan(verticalHalfFov),
    size.x * 0.5 / Math.tan(horizontalHalfFov),
    size.z * 0.5 / Math.tan(horizontalHalfFov),
    maxDimension * 0.65,
  );
  controls.target.copy(center);
  camera.position.set(center.x, center.y + size.y * 0.025, center.z + distance);
  camera.near = Math.max(distance / 1000, 0.005);
  camera.far = Math.max(distance * 20, 100);
  camera.updateProjectionMatrix();
  controls.update();
}

function updateSize() {
  const width = Math.max(host.clientWidth, 1);
  const height = Math.max(host.clientHeight, 1);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  if (bounds) frameModel();
}
window.addEventListener('resize', updateSize);
updateSize();

animateToggle.addEventListener('change', () => {
  if (!activeAction) return;
  if (animateToggle.checked) activeAction.play();
  else activeAction.stop();
});
frameButton.addEventListener('click', frameModel);

const loader = new GLTFLoader();
loader.load(MODEL_URL, (gltf) => {
  modelRoot = gltf.scene;
  scene.add(modelRoot);
  modelRoot.updateMatrixWorld(true);

  const skinnedMeshes = [];
  const meshNames = new Set();
  const materials = new Set();
  const textures = new Set();
  modelRoot.traverse((object) => {
    if (object.isMesh) meshNames.add(object.name || '(sem nome)');
    if (object.isMesh) {
      for (const material of (Array.isArray(object.material) ? object.material : [object.material])) {
        if (!material) continue;
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value?.isTexture) textures.add(value);
        }
      }
    }
    if (object.isSkinnedMesh) {
      skinnedMeshes.push(object);
      object.frustumCulled = false;
    }
  });

  for (const object of skinnedMeshes) object.computeBoundingBox();
  bounds = new THREE.Box3().setFromObject(modelRoot, true);
  if (bounds.isEmpty()) throw new Error('A cena carregou, mas não contém geometria com limites válidos.');
  frameModel();

  const skeletons = new Set(skinnedMeshes.map((mesh) => mesh.skeleton));
  const bones = new Set([...skeletons].flatMap((skeleton) => skeleton.bones));
  const clips = gltf.animations || [];
  const clipSummary = clips.length
    ? clips.map((clip) => `${clip.name || '(sem nome)'} · ${clip.duration.toFixed(2)}s · ${clip.tracks.length} tracks`).join(', ')
    : 'nenhuma';
  details.textContent = [
    `Malhas: ${meshNames.size} · SkinnedMesh: ${skinnedMeshes.length} · Ossos: ${bones.size}`,
    `Materiais: ${materials.size} · mapas de textura: ${textures.size}`,
    `Animações: ${clipSummary}`,
    `Dimensões enquadradas: ${sizeText(bounds.getSize(new THREE.Vector3()))}`,
  ].join('\n');

  if (clips.length && skinnedMeshes.length) {
    mixer = new THREE.AnimationMixer(modelRoot);
    const preferredClip = clips.find((clip) => /idle/i.test(clip.name)) || clips[0];
    activeAction = mixer.clipAction(preferredClip);
    activeAction.play();
    window.__chloeSamplePose = (seconds) => {
      mixer.setTime(seconds);
      modelRoot.updateMatrixWorld(true);
      renderer.render(scene, camera);
      return [...bones].map((bone) => [
        bone.position.x, bone.position.y, bone.position.z,
        bone.quaternion.x, bone.quaternion.y, bone.quaternion.z, bone.quaternion.w,
      ]);
    };
  } else {
    animateToggle.checked = false;
    animateToggle.disabled = true;
  }
  animateToggle.disabled = !activeAction;
  frameButton.disabled = false;
  status.textContent = `GLB renderizado · ${gltf.scene.name || 'cena original'}`;
  window.__chloeStatus = {
    loaded: true,
    meshes: meshNames.size,
    skinnedMeshes: skinnedMeshes.length,
    bones: bones.size,
    materials: materials.size,
    textures: textures.size,
    clips: clips.map((clip) => ({ name: clip.name, duration: clip.duration })),
    animationTracks: clips.reduce((count, clip) => count + clip.tracks.length, 0),
    bounds: bounds.getSize(new THREE.Vector3()).toArray(),
  };
}, undefined, (error) => {
  console.error('Falha ao carregar o GLB:', error);
  status.textContent = `Falha ao carregar: ${error.message || error}`;
  status.classList.add('error');
  window.__chloeStatus = { loaded: false, error: String(error) };
});

function sizeText(size) {
  return size.toArray().map((value) => value.toFixed(2)).join(' × ');
}

renderer.setAnimationLoop(() => {
  const now = performance.now();
  const delta = Math.min((now - previousFrameAt) / 1000, 0.05);
  previousFrameAt = now;
  if (mixer && activeAction?.isRunning()) mixer.update(delta);
  if (window.__chloeStatus && mixer) window.__chloeStatus.animationTime = mixer.time;
  controls.update();
  renderer.render(scene, camera);
});
