/**
 * FileInput Component
 * Horizontal drag-drop file input with file selection, removal, and validation
 */

class FileInput {
  constructor(containerSelector, options = {}) {
    this.container = document.querySelector(containerSelector);
    if (!this.container) {
      throw new Error(`Container not found: ${containerSelector}`);
    }

    // Configuration
    this.maxFiles = options.maxFiles || FileConfig.MAX_FILES;
    this.maxFileSize = options.maxFileSize || FileConfig.MAX_FILE_SIZE;
    this.onFilesChanged = options.onFilesChanged || (() => {});

    // State
    this.files = []; // Array of { id, file, name, extension, category, icon, selected }
    this.selectedFiles = new Set();
    this.nextFileId = 0;

    // Hidden file input for file explorer
    this.hiddenFileInput = null;

    // Initialize
    this.initializeUI();
    this.setupEventListeners();
  }

  /**
   * Initialize the component UI structure
   */
  initializeUI() {
    this.container.className = 'file-input-wrapper';

    // Create remove button (hidden by default)
    this.removeButton = document.createElement('button');
    this.removeButton.id = 'file-input-remove-btn';
    this.removeButton.className = 'file-input-remove-btn';
    this.removeButton.textContent = 'Remove Selected';
    this.removeButton.style.display = 'none';
    this.removeButton.addEventListener('click', () => this.removeSelectedFiles());

    // Create main file input container
    this.fileInputContainer = document.createElement('div');
    this.fileInputContainer.className = 'file-input-container';

    // Create hidden file input element for file explorer
    this.hiddenFileInput = document.createElement('input');
    this.hiddenFileInput.type = 'file';
    this.hiddenFileInput.multiple = true;
    this.hiddenFileInput.accept = FileConfig.getAllowedExtensions().join(',');
    this.hiddenFileInput.style.display = 'none';
    this.hiddenFileInput.addEventListener('change', (e) => this.handleFileExplorerSelect(e));

    // Append to container
    this.container.appendChild(this.removeButton);
    this.container.appendChild(this.fileInputContainer);
    this.container.appendChild(this.hiddenFileInput);

    // Initial render
    this.render();
  }

  /**
   * Setup drag-drop and other event listeners
   */
  setupEventListeners() {
    this.fileInputContainer.addEventListener('dragover', (e) => this.handleDragOver(e));
    this.fileInputContainer.addEventListener('dragleave', (e) => this.handleDragLeave(e));
    this.fileInputContainer.addEventListener('drop', (e) => this.handleDrop(e));
  }

  /**
   * Handle drag over event
   */
  handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    this.fileInputContainer.classList.add('drag-over');
  }

  /**
   * Handle drag leave event
   */
  handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    this.fileInputContainer.classList.remove('drag-over');
  }

  /**
   * Handle drop event
   */
  handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    this.fileInputContainer.classList.remove('drag-over');

    const droppedFiles = e.dataTransfer.files;
    this.processFiles(droppedFiles);
  }

  /**
   * Handle file explorer selection
   */
  handleFileExplorerSelect(e) {
    this.processFiles(e.target.files);
    // Reset the input so the same file can be selected again
    this.hiddenFileInput.value = '';
  }

  /**
   * Process dropped or selected files
   */
  processFiles(fileList) {
    for (const file of fileList) {
      this.addFile(file);
    }
  }

  /**
   * Add a single file with validation
   */
  addFile(file) {
    // Check max files limit
    if (this.files.length >= this.maxFiles) {
      this.showNotification(`Maximum ${this.maxFiles} files allowed`, 'error');
      return;
    }

    // Get file extension
    const ext = '.' + file.name.split('.').pop().toLowerCase();

    // Validate file type
    if (!FileConfig.isExtensionAllowed(ext)) {
      this.showNotification(`File type not allowed: ${file.name}`, 'error');
      return;
    }

    // Validate file size
    if (file.size > this.maxFileSize) {
      this.showNotification(`File too large: ${file.name} (max 100MB)`, 'error');
      return;
    }

    // Check for duplicates by file name
    if (this.files.some(f => f.file.name === file.name)) {
      this.showNotification(`File already selected: ${file.name}`, 'warning');
      return;
    }

    // Get category info
    const categoryInfo = FileConfig.getCategoryForExtension(ext);

    // Add file to state
    const fileObj = {
      id: this.nextFileId++,
      file,
      name: file.name,
      extension: ext,
      category: categoryInfo?.category || 'unknown',
      icon: categoryInfo?.icon || '📄',
      selected: false,
    };

    this.files.push(fileObj);
    this.render();
    this.onFilesChanged(this.getFiles());
  }

  /**
   * Remove a file by ID
   */
  removeFile(fileId) {
    this.files = this.files.filter(f => f.id !== fileId);
    this.selectedFiles.delete(fileId);
    this.render();
    this.onFilesChanged(this.getFiles());
  }

  /**
   * Remove all selected files
   */
  removeSelectedFiles() {
    for (const fileId of this.selectedFiles) {
      this.files = this.files.filter(f => f.id !== fileId);
    }
    this.selectedFiles.clear();
    this.render();
    this.onFilesChanged(this.getFiles());
  }

  /**
   * Toggle file selection
   */
  toggleFileSelection(fileId) {
    if (this.selectedFiles.has(fileId)) {
      this.selectedFiles.delete(fileId);
    } else {
      this.selectedFiles.add(fileId);
    }
    this.render();
  }

  /**
   * Get all files (not just file objects, but with metadata)
   */
  getFiles() {
    return this.files.map(f => ({
      id: f.id,
      file: f.file,
      name: f.name,
      extension: f.extension,
      category: f.category,
    }));
  }

  /**
   * Get only selected files
   */
  getSelectedFiles() {
    return this.files
      .filter(f => this.selectedFiles.has(f.id))
      .map(f => ({
        id: f.id,
        file: f.file,
        name: f.name,
        extension: f.extension,
        category: f.category,
      }));
  }

  /**
   * Clear all files
   */
  clear() {
    this.files = [];
    this.selectedFiles.clear();
    this.render();
    this.onFilesChanged(this.getFiles());
  }

  /**
   * Render the component UI
   */
  render() {
    // Clear the container
    this.fileInputContainer.innerHTML = '';

    // Create file items
    for (const fileObj of this.files) {
      const fileItem = this.createFileItem(fileObj);
      this.fileInputContainer.appendChild(fileItem);
    }

    // Add plus button if under max files
    if (this.files.length < this.maxFiles) {
      const plusButton = this.createPlusButton();
      this.fileInputContainer.appendChild(plusButton);
    }

    // Update remove button visibility
    this.removeButton.style.display = this.selectedFiles.size > 0 ? 'block' : 'none';
  }

  /**
   * Create a file item element
   */
  createFileItem(fileObj) {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.dataset.fileId = fileObj.id;

    // Checkbox for selection
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'file-item-checkbox';
    checkbox.checked = this.selectedFiles.has(fileObj.id);
    checkbox.addEventListener('change', () => this.toggleFileSelection(fileObj.id));

    // Icon and name wrapper
    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'file-item-content';

    // Icon
    const icon = document.createElement('div');
    icon.className = 'file-item-icon';
    icon.textContent = fileObj.icon;

    // Name
    const name = document.createElement('div');
    name.className = 'file-item-name';
    name.textContent = fileObj.name;
    name.title = fileObj.name; // Full name on hover

    contentWrapper.appendChild(icon);
    contentWrapper.appendChild(name);

    // Selection box overlay (positioned at bottom-right corner)
    const selectionBox = document.createElement('div');
    selectionBox.className = 'file-item-selection-box';
    selectionBox.appendChild(checkbox);

    item.appendChild(contentWrapper);
    item.appendChild(selectionBox);

    // Click to toggle selection
    contentWrapper.addEventListener('click', () => this.toggleFileSelection(fileObj.id));

    return item;
  }

  /**
   * Create the plus button for adding files
   */
  createPlusButton() {
    const button = document.createElement('button');
    button.className = 'file-item-plus-btn';
    button.type = 'button';
    button.innerHTML = '➕';
    button.title = 'Add files';
    button.addEventListener('click', () => this.hiddenFileInput.click());
    return button;
  }

  /**
   * Show a temporary notification message
   */
  showNotification(message, type = 'info') {
    // Create a simple notification element
    const notification = document.createElement('div');
    notification.className = `file-input-notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
      notification.classList.add('fade-out');
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
}
