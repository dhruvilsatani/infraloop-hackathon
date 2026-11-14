import { AfterViewInit, Component, ElementRef, OnDestroy, signal, viewChild } from '@angular/core';
import * as THREE from 'three';

@Component({
  selector: 'app-background',
  templateUrl: './background.html',
})
export class BackgroundComponent implements AfterViewInit, OnDestroy {
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  protected readonly videoReady = signal(false);
  protected readonly stillMissing = signal(false);
  private stop: (() => void) | null = null;

  ngAfterViewInit(): void {
    this.stop = this.startParticles();
  }

  ngOnDestroy(): void {
    this.stop?.();
  }

  // Cyan particle field with slow rotation and mouse parallax. Decorative only: no WebGL means no effect.
  private startParticles(): (() => void) | null {
    try {
      const canvas = this.canvas().nativeElement;
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
      const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
      renderer.setSize(window.innerWidth, window.innerHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

      const geo = new THREE.BufferGeometry();
      const count = 300;
      const positions = new Float32Array(count * 3);
      for (let i = 0; i < count * 3; i++) positions[i] = (Math.random() - 0.5) * 100;
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const particles = new THREE.Points(
        geo,
        new THREE.PointsMaterial({ size: 0.5, color: 0x22d3ee, transparent: true, opacity: 0.3 }),
      );
      scene.add(particles);
      camera.position.z = 30;

      let mouseX = 0;
      let mouseY = 0;
      let running = true;
      let frame = 0;

      const animate = (): void => {
        if (!running) return;
        frame = requestAnimationFrame(animate);
        particles.rotation.y -= 0.0005;
        camera.position.x += (mouseX * 8 - camera.position.x) * 0.05;
        camera.position.y += (-mouseY * 8 - camera.position.y) * 0.05;
        camera.lookAt(scene.position);
        renderer.render(scene, camera);
      };

      const onMove = (e: MouseEvent): void => {
        mouseX = (e.clientX / window.innerWidth - 0.5) * 0.3;
        mouseY = (e.clientY / window.innerHeight - 0.5) * 0.3;
      };
      const onVisibility = (): void => {
        const was = running;
        running = !document.hidden;
        if (running && !was && !reduce) animate();
      };
      const onResize = (): void => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        if (reduce) renderer.render(scene, camera);
      };

      window.addEventListener('mousemove', onMove);
      document.addEventListener('visibilitychange', onVisibility);
      window.addEventListener('resize', onResize);
      if (reduce) renderer.render(scene, camera);
      else animate();

      return () => {
        running = false;
        cancelAnimationFrame(frame);
        window.removeEventListener('mousemove', onMove);
        document.removeEventListener('visibilitychange', onVisibility);
        window.removeEventListener('resize', onResize);
        geo.dispose();
        renderer.dispose();
      };
    } catch {
      return null;
    }
  }
}
