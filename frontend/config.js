/**
 * Frontend Configuration
 * Defines allowed file types, categories, and UI icons for the file input component
 */

const FileConfig = {
  // Maximum number of files allowed in the component
  MAX_FILES: 10,

  // Maximum file size per file in bytes (100MB)
  MAX_FILE_SIZE: 100 * 1024 * 1024,

  // Allowed file types grouped by category
  ALLOWED_TYPES: {
    document: {
      extensions: ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.xls', '.csv', '.ppt', '.pptx'],
      icon: '📄',
      label: 'Document',
    },
    image: {
      extensions: ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff'],
      icon: '🖼️',
      label: 'Image',
    },
    archive: {
      extensions: ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
      icon: '📦',
      label: 'Archive',
    },
    video: {
      extensions: ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'],
      icon: '🎬',
      label: 'Video',
    },
    audio: {
      extensions: ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'],
      icon: '🎵',
      label: 'Audio',
    },
    code: {
      extensions: ['.js', '.ts', '.py', '.java', '.cpp', '.c', '.html', '.css', '.json', '.xml', '.yaml', '.yml'],
      icon: '💻',
      label: 'Code',
    },
  },

  /**
   * Get all allowed file extensions as a flat array
   * @returns {string[]} Array of allowed extensions (e.g., ['.pdf', '.doc', ...])
   */
  getAllowedExtensions() {
    return Object.values(this.ALLOWED_TYPES).flatMap(category => category.extensions);
  },

  /**
   * Get the category and icon for a given file extension
   * @param {string} extension - File extension (e.g., '.pdf')
   * @returns {object|null} Object with { category, icon, label } or null if not found
   */
  getCategoryForExtension(extension) {
    const lowerExt = extension.toLowerCase();
    for (const [category, data] of Object.entries(this.ALLOWED_TYPES)) {
      if (data.extensions.includes(lowerExt)) {
        return { category, icon: data.icon, label: data.label };
      }
    }
    return null;
  },

  /**
   * Check if a file extension is allowed
   * @param {string} extension - File extension (e.g., '.pdf')
   * @returns {boolean} True if extension is allowed
   */
  isExtensionAllowed(extension) {
    return this.getAllowedExtensions().includes(extension.toLowerCase());
  },
};
