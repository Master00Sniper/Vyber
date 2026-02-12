// Mobile hamburger toggle
const navToggle = document.querySelector('.nav-toggle');
const navLinks = document.querySelector('.nav-links');
if (navToggle && navLinks) {
    navToggle.addEventListener('click', () => {
        navToggle.classList.toggle('active');
        navLinks.classList.toggle('open');
    });
    // Close menu when a link is clicked
    navLinks.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            navToggle.classList.remove('active');
            navLinks.classList.remove('open');
        });
    });
}

// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Screenshot lightbox
const screenshot = document.querySelector('.app-screenshot');
if (screenshot) {
    screenshot.addEventListener('click', function () {
        const overlay = document.createElement('div');
        overlay.className = 'screenshot-overlay';
        const img = document.createElement('img');
        img.src = this.src;
        img.alt = this.alt;
        overlay.appendChild(img);
        document.body.appendChild(overlay);
        // Trigger transition
        requestAnimationFrame(() => overlay.classList.add('active'));
        overlay.addEventListener('click', () => {
            overlay.classList.remove('active');
            overlay.addEventListener('transitionend', () => overlay.remove());
        });
    });
}
