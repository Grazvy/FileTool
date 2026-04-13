// Main application logic

document.addEventListener('DOMContentLoaded', function() {
    const statusDiv = document.getElementById('status');
    const appContent = document.getElementById('app-content');
    const testApiBtn = document.getElementById('test-api');
    const apiResponse = document.getElementById('api-response');

    // Check backend connection on load
    checkBackendConnection();

    // Test API button
    testApiBtn.addEventListener('click', testApiConnection);

    async function checkBackendConnection() {
        try {
            const response = await api.healthCheck();
            statusDiv.innerHTML = '<p style="color: green;">✓ Connected to backend</p>';
            appContent.style.display = 'block';
        } catch (error) {
            statusDiv.innerHTML = '<p style="color: red;">✗ Cannot connect to backend. Please start the server.</p>';
            console.error('Backend connection failed:', error);
        }
    }

    async function testApiConnection() {
        try {
            apiResponse.textContent = 'Testing API...';
            const response = await api.healthCheck();
            apiResponse.textContent = JSON.stringify(response, null, 2);
        } catch (error) {
            apiResponse.textContent = `Error: ${error.message}`;
        }
    }
});