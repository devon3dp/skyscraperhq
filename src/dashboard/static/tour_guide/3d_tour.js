// 3D Tour Guide
// Initialize Three.js scene and camera
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.z = 5;

// Renderer
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('container').appendChild(renderer.domElement);

// Floor geometry and materials
function createFloor(floorNumber) {
    const floorGeometry = new THREE.PlaneBufferGeometry(10, 10);
    const floorMaterial = new THREE.MeshBasicMaterial({ color: 'lightgray' });
    return new THREE.Mesh(floorGeometry, floorMaterial);
}

// Create floors
for (let i = 0; i < 171; i++) {
    const floor = createFloor(i + 1);
    floor.position.y = -5 * i;
    scene.add(floor);
}

// Render loop
function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
}

animate();