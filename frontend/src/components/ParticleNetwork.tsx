import { useEffect, useRef } from 'react';

export function ParticleNetwork() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];
    let pulses: Pulse[] = [];
    let width = 0;
    let height = 0;
    let lastTime = performance.now();

    const accentRaw = getComputedStyle(document.documentElement).getPropertyValue('--accent-primary').trim() || '#06B6D4';
    const hexToRgb = (hex: string) => {
      if (hex.startsWith('#')) hex = hex.slice(1);
      if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
      const r = parseInt(hex.slice(0, 2), 16) || 6;
      const g = parseInt(hex.slice(2, 4), 16) || 182;
      const b = parseInt(hex.slice(4, 6), 16) || 212;
      return { r, g, b };
    };
    
    const accentColor = hexToRgb(accentRaw);
    const rgbString = `${accentColor.r}, ${accentColor.g}, ${accentColor.b}`;

    class Particle {
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;

      constructor(x: number, y: number) {
        this.x = x;
        this.y = y;
        this.vx = (Math.random() - 0.5) * 0.6;
        this.vy = (Math.random() - 0.5) * 0.6;
        this.radius = Math.random() * 1.5 + 0.5;
      }

      update(width: number, height: number) {
        this.x += this.vx;
        this.y += this.vy;
        
        if (this.x < 0) this.x = width;
        if (this.x > width) this.x = 0;
        if (this.y < 0) this.y = height;
        if (this.y > height) this.y = 0;
      }

      draw(ctx: CanvasRenderingContext2D) {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${rgbString}, 0.8)`;
        ctx.shadowBlur = 4;
        ctx.shadowColor = `rgba(${rgbString}, 1)`;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    class Pulse {
      startX: number;
      startY: number;
      endX: number;
      endY: number;
      progress: number;
      speed: number;

      constructor(p1: Particle, p2: Particle) {
        this.startX = p1.x;
        this.startY = p1.y;
        this.endX = p2.x;
        this.endY = p2.y;
        this.progress = 0;
        // Roughly 0.5s at 60fps
        this.speed = 0.02 + Math.random() * 0.02; 
      }

      update() {
        this.progress += this.speed;
        return this.progress >= 1;
      }

      draw(ctx: CanvasRenderingContext2D) {
        const x = this.startX + (this.endX - this.startX) * this.progress;
        const y = this.startY + (this.endY - this.startY) * this.progress;
        
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${rgbString}, 1)`;
        ctx.shadowBlur = 8;
        ctx.shadowColor = `rgba(${rgbString}, 1)`;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    const init = () => {
      width = canvas.offsetWidth;
      height = canvas.offsetHeight;
      canvas.width = width;
      canvas.height = height;

      particles = [];
      const particleCount = 80;
      for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle(Math.random() * width, Math.random() * height));
      }
    };

    let pulseTimer = 0;

    const animate = (time: number) => {
      const dt = time - lastTime;
      lastTime = time;

      ctx.clearRect(0, 0, width, height);

      // 1. Horizontal scan line
      const scanPeriod = 6000;
      const scanY = (time % scanPeriod) / scanPeriod * height;
      
      const scanGradient = ctx.createLinearGradient(0, scanY - 50, 0, scanY + 50);
      scanGradient.addColorStop(0, `rgba(${rgbString}, 0)`);
      scanGradient.addColorStop(0.5, `rgba(${rgbString}, 0.1)`);
      scanGradient.addColorStop(1, `rgba(${rgbString}, 0)`);
      
      ctx.fillStyle = scanGradient;
      ctx.fillRect(0, scanY - 50, width, 100);
      
      ctx.beginPath();
      ctx.moveTo(0, scanY);
      ctx.lineTo(width, scanY);
      ctx.strokeStyle = `rgba(${rgbString}, 0.2)`;
      ctx.lineWidth = 1;
      ctx.stroke();

      // 2. Radar sweep
      const radarRadius = Math.min(width, height) * 0.3;
      const radarCenter = { x: width / 2, y: height / 2 };
      
      ctx.beginPath();
      ctx.arc(radarCenter.x, radarCenter.y, radarRadius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(${rgbString}, 0.05)`;
      ctx.lineWidth = 1;
      ctx.stroke();

      const sweepPeriod = 8000;
      const sweepAngle = (time % sweepPeriod) / sweepPeriod * Math.PI * 2;
      
      ctx.save();
      ctx.translate(radarCenter.x, radarCenter.y);
      ctx.rotate(sweepAngle);
      
      // Sweep line
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(radarRadius, 0);
      ctx.strokeStyle = `rgba(${rgbString}, 0.4)`;
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Fading trail behind the sweep line (counter-clockwise from 0 to -Math.PI/4)
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, radarRadius, -Math.PI / 4, 0, false);
      ctx.lineTo(0, 0);
      
      // Some environments might not support createConicGradient, try/catch gracefully
      try {
        const gradient = ctx.createConicGradient(0, 0, 0);
        gradient.addColorStop(0, `rgba(${rgbString}, 0.15)`);
        gradient.addColorStop(0.875, `rgba(${rgbString}, 0)`);
        gradient.addColorStop(1, `rgba(${rgbString}, 0.15)`);
        ctx.fillStyle = gradient;
      } catch (e) {
        ctx.fillStyle = `rgba(${rgbString}, 0.05)`;
      }
      ctx.fill();
      ctx.restore();

      // 3. Update and draw particles & connections
      particles.forEach(p => p.update(width, height));

      const connectionDistance = 150;
      let possibleConnections: { p1: Particle, p2: Particle }[] = [];
      
      ctx.lineWidth = 1;
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const distSq = dx * dx + dy * dy;
          
          if (distSq < connectionDistance * connectionDistance) {
            possibleConnections.push({ p1: particles[i], p2: particles[j] });
            const opacity = 1 - Math.sqrt(distSq) / connectionDistance;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(${rgbString}, ${opacity * 0.3})`;
            ctx.stroke();
          }
        }
      }

      particles.forEach(p => p.draw(ctx));

      // 4. Update and draw pulses
      pulseTimer += dt;
      if (pulseTimer > 2000 && possibleConnections.length > 0) {
        pulseTimer = 0;
        const randomConn = possibleConnections[Math.floor(Math.random() * possibleConnections.length)];
        pulses.push(new Pulse(randomConn.p1, randomConn.p2));
      }

      pulses = pulses.filter(pulse => {
        const done = pulse.update();
        pulse.draw(ctx);
        return !done;
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    init();
    // Use an initial time offset for consistency
    animationFrameId = requestAnimationFrame((time) => {
      lastTime = time;
      animate(time);
    });

    const handleResize = () => {
      init();
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
    />
  );
}
