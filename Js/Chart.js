

// Chart.js - Analytics Page Chart Configuration
// Creates beautiful charts using Chart.js library

document.addEventListener('DOMContentLoaded', function() {
    onAuthStateChanged(auth, (user) => {
        const ctx = document.getElementById('myChart');
        if (!ctx) return;

        if (!user) {
            document.querySelectorAll('.stat-value').forEach(el => el.textContent = '0');
            
            document.querySelectorAll('.chart-body').forEach(chartBody => {
                let existingOverlay = chartBody.querySelector('.login-overlay');
                if (existingOverlay) existingOverlay.remove();
                
                const overlay = document.createElement('div');
                overlay.className = 'login-overlay';
                overlay.style.position = 'absolute';
                overlay.style.top = '0'; overlay.style.left = '0'; overlay.style.right = '0'; overlay.style.bottom = '0';
                overlay.style.display = 'flex'; overlay.style.flexDirection = 'column';
                overlay.style.alignItems = 'center'; overlay.style.justifyContent = 'center';
                overlay.style.background = 'var(--bg-glass)';
                overlay.style.zIndex = '10'; overlay.style.borderRadius = '16px';
                overlay.style.backdropFilter = 'blur(6px)';
                
                overlay.innerHTML = `
                    <div style="font-size: 32px; color:var(--text-secondary); margin-bottom: 8px;">&#128274;</div>
                    <h3 style="margin:0; color:var(--text-primary); font-size:16px;">Vui lòng đăng nhập</h3>
                    <p style="color:var(--text-secondary); font-size:13px; margin-top:4px;">Đăng nhập để xem thống kê</p>
                    <button onclick="window.location.href='Login.html'" class="btn btn-primary" style="margin-top:12px; font-size:13px; padding:6px 16px;">Đăng nhập ngay</button>
                `;
                chartBody.appendChild(overlay);
                
                const canvas = chartBody.querySelector('canvas');
                if(canvas) {
                    canvas.style.opacity = '0.05';
                    canvas.style.pointerEvents = 'none';
                }
            });
        } else {
            document.querySelectorAll('.chart-body').forEach(chartBody => {
                let existingOverlay = chartBody.querySelector('.login-overlay');
                if (existingOverlay) existingOverlay.remove();
                const canvas = chartBody.querySelector('canvas');
                if(canvas) {
                    canvas.style.opacity = '1';
                    canvas.style.pointerEvents = 'auto';
                }
            });

            // Sample data for demonstration
            const labelsLine = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
            const dataLine = {
                labels: labelsLine,
                datasets: [
                    {
                        label: 'Mindmap',
                        data: [2, 1, 3, 2, 0, 4, 2],
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 5,
                        pointBackgroundColor: '#6366f1',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                    },
                    {
                        label: 'AI Chat',
                        data: [42, 35, 68, 45, 52, 70, 48],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 5,
                        pointBackgroundColor: '#10b981',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                    }
                ]
            };

            const commonOptions = {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                animation: { duration: 1000, easing: 'easeOutQuart' }
            };

            const configLine = {
                type: 'line',
                data: dataLine,
                options: { ...commonOptions, interaction: { mode: 'index', intersect: false },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: '#94a3b8' }, border: { display: false } },
                        y: { beginAtZero: true, grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#94a3b8' }, border: { display: false } }
                    }
                }
            };
            new Chart(ctx, configLine);

            const ctxRadar = document.getElementById('radarChart');
            if (ctxRadar) {
                new Chart(ctxRadar, {
                    type: 'radar',
                    data: {
                        labels: ['Chat AI', 'Sổ tay', 'Trình dựng', 'Tra cứu', 'Quiz'],
                        datasets: [{
                            label: 'Tần suất',
                            data: [65, 59, 90, 81, 56],
                            backgroundColor: 'rgba(244, 63, 94, 0.2)',
                            borderColor: '#f43f5e',
                            pointBackgroundColor: '#f43f5e',
                            borderWidth: 2,
                        }]
                    },
                    options: { ...commonOptions, scales: { r: { ticks: { display: false }, grid: { color: 'rgba(148, 163, 184, 0.1)' }, angleLines: { color: 'rgba(148, 163, 184, 0.1)' }, pointLabels: { color: '#94a3b8', font: { size: 11 } } } } }
                });
            }

            const ctxDoughnut = document.getElementById('doughnutChart');
            if (ctxDoughnut) {
                new Chart(ctxDoughnut, {
                    type: 'doughnut',
                    data: {
                        labels: ['Mindmap', 'Báo cáo', 'Thuyết trình', 'Khác'],
                        datasets: [{
                            data: [300, 50, 100, 40],
                            backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#94a3b8'],
                            borderWidth: 0,
                        }]
                    },
                    options: { ...commonOptions, cutout: '75%', plugins: { tooltip: { enabled: true } } }
                });
            }
        }
    
    (function(){})('📊 Analytics chart initialized successfully');
    });
});
