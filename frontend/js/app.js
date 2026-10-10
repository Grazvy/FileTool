// Main application logic

let fileInputComponent = null;

document.addEventListener('DOMContentLoaded', function() {
    const statusDiv = document.getElementById('status');
    const appContent = document.getElementById('app-content');

    // Check backend connection on load
    checkBackendConnection();

    async function checkBackendConnection() {
        try {
            const response = await api.healthCheck();
            statusDiv.innerHTML = '<p style="color: green;">✓ Connected to backend</p>';
            appContent.style.display = 'block';
            
            // Initialize FileInput component
            initializeFileInput();
        } catch (error) {
            statusDiv.innerHTML = '<p style="color: red;">✗ Cannot connect to backend. Please start the server.</p>';
            console.error('Backend connection failed:', error);
        }
    }

    function initializeFileInput() {
        fileInputComponent = new FileInput('#file-input-component', {
            maxFiles: FileConfig.MAX_FILES,
            maxFileSize: FileConfig.MAX_FILE_SIZE,
            onFilesChanged: function(files) {
                console.log('Files changed:', files);
                // Handle files changed event here
            }
        });
    }
});