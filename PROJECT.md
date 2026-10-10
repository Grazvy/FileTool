
## Key Architectural Principles

1. **Separation of Concerns**
   - Frontend: User interface and input collection only
   - Backend: All file processing, format conversions, and business logic
   - Launcher: Single entry point to start server and open browser

2. **Local-First Privacy**
   - Server listens only on `localhost:PORT` (not exposed to network by default)
   - All files processed entirely on user's machine
   - No external API calls or data transmission

3. **Stateless Communication**
   - Frontend sends file data and parameters via HTTP POST requests
   - Backend processes and returns results
   - Each request is independent (easier to scale, debug, and restart)

4. **Single Application Runtime**
   - One Python process runs the server
   - Browser connects to that single instance
   - User doesn't think about "client" vs "server" — just opens the app

5. **Packaging**
   - PyInstaller bundles Python runtime + code → distributable executable
   - Launcher script extracts any needed resources, starts server, opens browser
   - User clicks once, app is ready

## Data Flow

User interacts with UI → Frontend sends HTTP request → Backend processes file(s) → Returns result → Frontend displays/downloads

## Use Case

**File Tool** is a local file manipulation application designed for users who need to perform batch file operations while maintaining complete control and privacy over their data.

### Primary Purpose

The application enables users to process, transform, and manage files of various formats through a simple, accessible web interface—all executed locally on their machine without sending data to external services or websites.

### Core Value Propositions

- **Privacy-First**: All file processing occurs locally. No data is transmitted to third-party services.
- **Format Flexibility**: Handles conversion and manipulation across multiple file types (documents, images, PDFs, etc.).
- **Ease of Use**: Single-click startup with a familiar browser interface—no installation complexity.
- **Batch Operations**: Process multiple files and perform complex operations in one workflow.
- **Accessibility**: Available anytime without internet dependency; accessible from any device on the local network.

### Target Workflow

Users can upload files, specify transformation parameters (cropping, resizing, merging, etc.), and receive processed results instantly—all within a single application instance running on their local machine.

### Design Philosophy

The application prioritizes simplicity and privacy over feature abundance. It's built as a self-contained, locally-run tool that replaces the need for multiple online conversion websites or cloud-based file manipulation services.