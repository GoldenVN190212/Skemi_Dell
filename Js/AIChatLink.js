// ========================================
// AI Chat Link Handler - Opens AI Chat Widget
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    // Handle AI chat link clicks
    const aiChatLinks = document.querySelectorAll('#ai-chat-link');
    
    aiChatLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Open AI chat widget if available
            if (window.aiChatWidget) {
                window.aiChatWidget.openChat();
            } else {
                // Fallback - show notification or create widget
                console.warn('AI Chat widget not loaded');
                
                // Try to load and initialize widget
                import('./AIChat.js').then(module => {
                    const AIChatWidget = module.default;
                    window.aiChatWidget = new AIChatWidget();
                    setTimeout(() => {
                        window.aiChatWidget.openChat();
                    }, 100);
                }).catch(err => {
                    console.error('Could not load AI Chat widget:', err);
                });
            }
        });
    });
});
