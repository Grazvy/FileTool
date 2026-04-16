document.addEventListener('DOMContentLoaded', function() {
    const fileStrip = document.getElementById('file-strip');
    const fileItems = document.getElementById('file-items');
    const filePicker = document.getElementById('file-picker');
    const removeSelectedBtn = document.getElementById('remove-selected-btn');

    const state = {
        files: [],
        selectedIds: new Set(),
        dragActive: false,
    };

    const allowedExtensions = FileConfig.getAllowedExtensions();
    filePicker.setAttribute('accept', allowedExtensions.join(','));

    fileStrip.addEventListener('dragenter', onDragEnter);
    fileStrip.addEventListener('dragover', onDragOver);
    fileStrip.addEventListener('dragleave', onDragLeave);
    fileStrip.addEventListener('drop', onDrop);
    filePicker.addEventListener('change', onFilePickerChange);
    removeSelectedBtn.addEventListener('click', removeSelectedFiles);

    render();

    function onDragEnter(event) {
        event.preventDefault();
        state.dragActive = true;
        updateDragState();
    }

    function onDragOver(event) {
        event.preventDefault();
        if (!state.dragActive) {
            state.dragActive = true;
            updateDragState();
        }
    }

    function onDragLeave(event) {
        if (!fileStrip.contains(event.relatedTarget)) {
            state.dragActive = false;
            updateDragState();
        }
    }

    function onDrop(event) {
        event.preventDefault();
        state.dragActive = false;
        updateDragState();

        const droppedFiles = Array.from(event.dataTransfer.files || []);
        addFiles(droppedFiles);
    }

    function onFilePickerChange(event) {
        const pickedFiles = Array.from(event.target.files || []);
        addFiles(pickedFiles);
        filePicker.value = '';
    }

    function addFiles(candidates) {
        if (candidates.length === 0) {
            return;
        }

        const existingKeys = new Set(state.files.map(toFileKey));
        for (const file of candidates) {
            if (state.files.length >= FileConfig.MAX_FILES) {
                break;
            }

            const extension = getFileExtension(file.name);
            if (!FileConfig.isExtensionAllowed(extension)) {
                continue;
            }
            if (file.size > FileConfig.MAX_FILE_SIZE) {
                continue;
            }

            const key = toFileKey(file);
            if (existingKeys.has(key)) {
                continue;
            }

            existingKeys.add(key);
            state.files.push({
                id: key,
                file,
            });
        }

        render();
    }

    function removeSelectedFiles() {
        if (state.selectedIds.size === 0) {
            return;
        }

        state.files = state.files.filter((item) => !state.selectedIds.has(item.id));
        state.selectedIds.clear();
        render();
    }

    function toggleSelection(id) {
        if (state.selectedIds.has(id)) {
            state.selectedIds.delete(id);
        } else {
            state.selectedIds.add(id);
        }
        render();
    }

    function render() {
        fileItems.innerHTML = '';

        for (const item of state.files) {
            const tile = document.createElement('button');
            tile.type = 'button';
            tile.className = 'file-tile';
            tile.setAttribute('role', 'listitem');
            tile.setAttribute('aria-label', item.file.name);

            if (state.selectedIds.has(item.id)) {
                tile.classList.add('is-selected');
            }

            const extension = getFileExtension(item.file.name);
            const categoryData = FileConfig.getCategoryForExtension(extension);
            const icon = categoryData ? categoryData.icon : 'FILE';

            tile.innerHTML = [
                `<span class="file-tile-icon" aria-hidden="true">${icon}</span>`,
                `<span class="file-tile-name">${item.file.name}</span>`,
                '<span class="file-tile-check" aria-hidden="true"></span>',
            ].join('');

            tile.addEventListener('click', () => toggleSelection(item.id));
            fileItems.appendChild(tile);
        }

        const plusTile = document.createElement('button');
        plusTile.type = 'button';
        plusTile.className = 'file-tile file-tile-plus';
        plusTile.setAttribute('role', 'listitem');
        plusTile.setAttribute('aria-label', 'Add files');
        plusTile.innerHTML = [
            '<span class="file-tile-icon" aria-hidden="true">+</span>',
            '<span class="file-tile-name">Add files</span>',
        ].join('');
        plusTile.addEventListener('click', () => filePicker.click());
        fileItems.appendChild(plusTile);

        removeSelectedBtn.disabled = state.selectedIds.size === 0;
    }

    function updateDragState() {
        fileStrip.classList.toggle('is-drag-active', state.dragActive);
    }

    function getFileExtension(name) {
        const lastDot = name.lastIndexOf('.');
        if (lastDot === -1) {
            return '';
        }
        return name.slice(lastDot).toLowerCase();
    }

    function toFileKey(input) {
        const file = input.file || input;
        return `${file.name}::${file.size}::${file.lastModified}`;
    }
});
