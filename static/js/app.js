document.addEventListener('DOMContentLoaded', () => {
    const templatesGrid = document.getElementById('templatesGrid');
    const workspaceSection = document.getElementById('workspaceSection');
    const formContainer = document.getElementById('formContainer');
    const dynamicFields = document.getElementById('dynamicFields');
    const renderForm = document.getElementById('renderForm');
    const templateIdInput = document.getElementById('templateIdInput');
    const workspaceTitle = document.getElementById('workspaceTitle');
    const submitBtn = document.getElementById('submitBtn');
    
    const progressContainer = document.getElementById('progressContainer');
    const progressPercentage = document.getElementById('progressPercentage');
    const progressStatusMsg = document.getElementById('progressStatusMsg');
    const progressBarFill = document.getElementById('progressBarFill');
    
    const resultContainer = document.getElementById('resultContainer');
    const resultVideoPlayer = document.getElementById('resultVideoPlayer');
    const downloadBtn = document.getElementById('downloadBtn');
    const resetBtn = document.getElementById('resetBtn');

    let templates = [];
    let selectedTemplate = null;
    let pollInterval = null;
    let selectedFilesMap = {}; // Tracks selected files for drag & drop zones
    let templateFieldsMap = {}; // Tracks field objects for validation and selections
    let customScenes = [];
    let editingTemplateId = null;

    // View Tab Switching
    const navTabs = document.querySelectorAll('.nav-tab');
    const makerView = document.getElementById('makerView');
    const builderView = document.getElementById('builderView');
    const mediaView = document.getElementById('mediaView');

    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;

            // Remove active class from all tabs, add to clicked one
            navTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Switch views
            makerView.classList.remove('active');
            builderView.classList.remove('active');
            mediaView.classList.remove('active');

            if (target === 'maker') {
                makerView.classList.add('active');
            } else if (target === 'builder') {
                builderView.classList.add('active');
            } else if (target === 'media') {
                mediaView.classList.add('active');
                // Refresh library when opening media center
                loadLibrary();
            }
        });
    });

    // 1. Fetch available templates
    async function loadTemplates() {
        try {
            const res = await fetch('/api/templates');
            if (!res.ok) throw new Error('無法取得範本資料');
            templates = await res.json();
            renderTemplates();
        } catch (error) {
            templatesGrid.innerHTML = `
                <div style="text-align: center; grid-column: 1/-1; padding: 3rem; color: #f87171;">
                    載入範本失敗: ${error.message}
                </div>
            `;
        }
    }

    // 2. Render templates in grid
    function renderTemplates() {
        templatesGrid.innerHTML = '';
        templates.forEach(tpl => {
            const card = document.createElement('div');
            card.className = 'template-card';
            
            let customActionsHtml = '';
            if (tpl.id.startsWith('custom_')) {
                customActionsHtml = `
                    <div class="custom-template-actions" style="display: flex; gap: 8px; margin-top: 0.5rem; width: 100%;">
                        <button class="edit-template-btn" data-id="${tpl.id}" style="flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #cbd5e1; border-radius: 12px; padding: 0.6rem; font-size: 0.8rem; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 4px; cursor: pointer; transition: all 0.2s ease;">
                            ✏️ 編輯
                        </button>
                        <button class="delete-template-btn" data-id="${tpl.id}" style="flex: 1; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.15); color: #f87171; border-radius: 12px; padding: 0.6rem; font-size: 0.8rem; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 4px; cursor: pointer; transition: all 0.2s ease;">
                            🗑️ 刪除
                        </button>
                    </div>
                `;
            }
            
            card.innerHTML = `
                <div class="video-preview-wrapper">
                    <video src="${tpl.preview_url}" autoplay loop muted playsinline></video>
                </div>
                <div class="template-card-info">
                    <h3>${tpl.name}</h3>
                    <p>${tpl.description}</p>
                    <button class="select-template-btn" data-id="${tpl.id}">
                        使用此範本
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                    </button>
                    ${customActionsHtml}
                </div>
            `;
            
            // Add click listener
            card.querySelector('.select-template-btn').addEventListener('click', () => {
                selectTemplate(tpl.id);
            });
            
            if (tpl.id.startsWith('custom_')) {
                card.querySelector('.edit-template-btn').addEventListener('click', (e) => {
                    e.stopPropagation();
                    editCustomTemplate(tpl.id);
                });
                card.querySelector('.delete-template-btn').addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteCustomTemplate(tpl.id);
                });
            }
            
            templatesGrid.appendChild(card);
        });
    }

    // 3. Select a template and build the form
    function selectTemplate(templateId) {
        selectedTemplate = templates.find(t => t.id === templateId);
        if (!selectedTemplate) return;

        // Reset workspace state
        resetWorkspaceUI();
        
        templateIdInput.value = templateId;
        workspaceTitle.textContent = `製作「${selectedTemplate.name}」`;
        
        // Build form fields
        dynamicFields.innerHTML = '';
        selectedFilesMap = {};
        templateFieldsMap = {};

        selectedTemplate.fields.forEach(field => {
            templateFieldsMap[field.name] = field;
            const formGroup = document.createElement('div');
            formGroup.className = 'form-group';
            formGroup.id = `group_${field.name}`;
            
            // Label
            const label = document.createElement('label');
            label.textContent = field.label + (field.required ? ' *' : '');
            formGroup.appendChild(label);
            
            // Input Controls
            if (field.type === 'text') {
                const input = document.createElement('input');
                input.type = 'text';
                input.name = field.name;
                input.className = 'form-input';
                input.placeholder = field.placeholder || '';
                input.required = field.required;
                formGroup.appendChild(input);
            } 
            else if (field.type === 'select') {
                const select = document.createElement('select');
                select.name = field.name;
                select.className = 'form-select';
                select.required = field.required;
                
                field.options.forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt.value;
                    option.textContent = opt.label;
                    select.appendChild(option);
                });
                
                // Watch for changes (for conditional rendering)
                select.addEventListener('change', () => handleConditionalFields());
                formGroup.appendChild(select);
            } 
            else if (field.type === 'file') {
                const dropzone = document.createElement('div');
                dropzone.className = 'dropzone';
                dropzone.id = `dropzone_${field.name}`;
                
                // Add select from library button
                let libraryBtnHtml = '';
                if (field.accept.includes('image') || field.accept.includes('video') || field.accept.includes('audio')) {
                    libraryBtnHtml = `<button type="button" class="select-library-btn" style="position: relative; z-index: 10; margin-top: 0.5rem; background: var(--gradient-accent); border: none; color: white; padding: 0.35rem 0.8rem; border-radius: 8px; font-size: 0.8rem; cursor: pointer; transition: transform 0.2s;" onclick="openLibrarySelect('${field.name}', ${field.multiple || false}, '${field.accept}')">📂 從媒體庫選擇</button>`;
                }

                dropzone.innerHTML = `
                    <div class="dropzone-icon">↑</div>
                    <p>將檔案拖曳至此，或點擊上傳</p>
                    <span>支援格式: ${field.accept === 'image/*' ? '圖片 (PNG/JPG)' : field.accept === 'video/*' ? '影片 (MP4)' : '音訊 (MP3/WAV)'}</span>
                    ${libraryBtnHtml}
                    <input type="hidden" name="${field.name}_library" id="library_input_${field.name}">
                    <input type="file" class="file-input" name="${field.name}" accept="${field.accept}" ${field.multiple ? 'multiple' : ''} ${field.required ? 'required' : ''}>
                    <div class="file-preview-container" id="preview_${field.name}"></div>
                `;
                
                const fileInput = dropzone.querySelector('.file-input');
                const previewContainer = dropzone.querySelector('.file-preview-container');
                
                // Prevent drag/drop browser defaults
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    dropzone.addEventListener(eventName, e => e.preventDefault(), false);
                });

                // Highlight dropzone on dragover
                ['dragenter', 'dragover'].forEach(eventName => {
                    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
                });
                ['dragleave', 'drop'].forEach(eventName => {
                    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
                });

                // Handle dropped files
                dropzone.addEventListener('drop', (e) => {
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    handleFiles(files, field, fileInput, previewContainer);
                });

                // Handle clicked files
                fileInput.addEventListener('change', (e) => {
                    const files = e.target.files;
                    handleFiles(files, field, fileInput, previewContainer);
                });

                formGroup.appendChild(dropzone);
            }
            
            dynamicFields.appendChild(formGroup);
        });

        // Setup visibility logic
        handleConditionalFields();

        // Reveal workspace
        workspaceSection.style.display = 'block';
        workspaceSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Handles files selected via click or drag-and-drop
    function handleFiles(files, field, fileInput, previewContainer) {
        if (!files.length) return;
        
        previewContainer.innerHTML = '';
        const filesArray = Array.from(files);
        
        // Store reference
        selectedFilesMap[field.name] = filesArray;
        
        // Update input element files property programmatically for native validation
        const dataTransfer = new DataTransfer();
        filesArray.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;

        // Render visual preview
        filesArray.forEach((file, index) => {
            const previewCard = document.createElement('div');
            if (field.accept === 'image/*') {
                previewCard.className = 'file-preview-card image-card';
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.onload = () => URL.revokeObjectURL(img.src);
                previewCard.appendChild(img);
            } else {
                previewCard.className = 'file-preview-card';
                previewCard.innerHTML = `
                    <span>📄</span>
                    <span>${file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name}</span>
                    <span class="remove-file-btn" data-index="${index}">&times;</span>
                `;
                // Add removal logic for non-image list
                previewCard.querySelector('.remove-file-btn').addEventListener('click', (e) => {
                    e.stopPropagation();
                    removeFile(field.name, index, fileInput, previewContainer, field);
                });
            }
            previewContainer.appendChild(previewCard);
        });
    }

    function removeFile(fieldName, index, fileInput, previewContainer, field) {
        let files = selectedFilesMap[fieldName] || [];
        files.splice(index, 1);
        selectedFilesMap[fieldName] = files;
        
        // Sync input files
        const dataTransfer = new DataTransfer();
        files.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;

        // Redraw preview
        handleFiles(fileInput.files, field, fileInput, previewContainer);
    }

    // Dynamic visibility of fields depending on select controls
    function handleConditionalFields() {
        if (!selectedTemplate) return;
        
        selectedTemplate.fields.forEach(field => {
            if (field.conditional) {
                // Format of conditional: "fieldName=value"
                const [targetName, targetValue] = field.conditional.split('=');
                const targetElement = document.querySelector(`[name="${targetName}"]`);
                const groupElement = document.getElementById(`group_${field.name}`);
                const fileInputElement = groupElement.querySelector('input[type="file"]');
                
                if (targetElement && groupElement) {
                    if (targetElement.value === targetValue) {
                        groupElement.style.display = 'block';
                        if (fileInputElement) fileInputElement.required = true;
                    } else {
                        groupElement.style.display = 'none';
                        if (fileInputElement) {
                            fileInputElement.required = false;
                            fileInputElement.value = ''; // clear input
                            const preview = groupElement.querySelector('.file-preview-container');
                            if (preview) preview.innerHTML = '';
                        }
                    }
                }
            }
        });
    }

    // 4. Form Submission & API Request
    renderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(renderForm);
        
        // Append files manually from our map to ensure drag-and-drop files are fully captured
        for (const [fieldName, files] of Object.entries(selectedFilesMap)) {
            // Remove the default empty file inputs from formData first
            formData.delete(fieldName);
            
            // Re-append actual files
            files.forEach(file => {
                formData.append(fieldName, file);
            });
        }

        // Show rendering progress UI
        formContainer.style.display = 'none';
        progressContainer.style.display = 'block';
        updateProgress(0, '正在上傳素材，發送剪輯請求...');
        
        submitBtn.disabled = true;

        try {
            const response = await fetch('/api/render', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '發送渲染請求失敗');
            }

            const data = await response.json();
            const taskId = data.task_id;
            
            // Start Polling Status
            startPolling(taskId);
            
        } catch (error) {
            alert(`發生錯誤: ${error.message}`);
            // Revert back to form
            formContainer.style.display = 'block';
            progressContainer.style.display = 'none';
            submitBtn.disabled = false;
        }
    });

    // 5. Polling Task Progress
    function startPolling(taskId) {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${taskId}`);
                if (!res.ok) throw new Error('查詢任務狀態失敗');
                
                const task = await res.json();
                
                if (task.status === 'pending' || task.status === 'processing') {
                    updateProgress(task.progress, task.message);
                } 
                else if (task.status === 'completed') {
                    clearInterval(pollInterval);
                    showSuccessResult(task.output_url);
                } 
                else if (task.status === 'failed') {
                    clearInterval(pollInterval);
                    alert(`渲染失敗: ${task.message}`);
                    resetWorkspaceUI();
                }
            } catch (error) {
                console.error(error);
                progressStatusMsg.textContent = `連接異常，重試中... (${error.message})`;
            }
        }, 1000);
    }

    function updateProgress(percentage, message) {
        progressPercentage.textContent = `${percentage}%`;
        progressBarFill.style.width = `${percentage}%`;
        progressStatusMsg.textContent = message;
    }

    // 6. Show rendered output video
    function showSuccessResult(videoUrl) {
        progressContainer.style.display = 'none';
        resultContainer.style.display = 'block';
        
        resultVideoPlayer.src = videoUrl;
        resultVideoPlayer.load();
        resultVideoPlayer.play();
        
        downloadBtn.href = videoUrl;
        
        // Refresh Media Center items
        loadLibrary();
    }

    function resetWorkspaceUI() {
        if (pollInterval) clearInterval(pollInterval);
        formContainer.style.display = 'block';
        progressContainer.style.display = 'none';
        resultContainer.style.display = 'none';
        submitBtn.disabled = false;
        resultVideoPlayer.src = '';
    }

    // 7. Reset all
    resetBtn.addEventListener('click', () => {
        resetWorkspaceUI();
        renderForm.reset();
        
        // Clear all library hidden inputs
        renderForm.querySelectorAll('input[type="hidden"]').forEach(input => {
            if (input.id && input.id.startsWith('library_input_')) {
                input.value = '';
            }
        });
        // Restore required attribute to file inputs
        renderForm.querySelectorAll('.file-input').forEach(fileInput => {
            const fieldName = fileInput.name;
            const field = templateFieldsMap[fieldName];
            if (field && field.required) {
                fileInput.setAttribute('required', 'required');
            }
        });

        selectedFilesMap = {};
        const previews = renderForm.querySelectorAll('.file-preview-container');
        previews.forEach(p => p.innerHTML = '');
        workspaceSection.style.display = 'none';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Run on startup
    loadTemplates();
    loadLibrary();

    // === Media Center Feature ===
    const assetsGrid = document.getElementById('assetsGrid');
    const musicGrid = document.getElementById('musicGrid');
    const videosGrid = document.getElementById('videosGrid');
    const tabAssetsBtn = document.getElementById('tabAssetsBtn');
    const tabMusicBtn = document.getElementById('tabMusicBtn');
    const tabVideosBtn = document.getElementById('tabVideosBtn');
    
    const editModal = document.getElementById('editModal');
    const editForm = document.getElementById('editForm');
    const editCategoryInput = document.getElementById('editCategory');
    const editIdInput = document.getElementById('editId');
    const editNameInput = document.getElementById('editName');
    const editMemoInput = document.getElementById('editMemo');

    const previewModal = document.getElementById('previewModal');
    const previewTitle = document.getElementById('previewTitle');
    const previewContentArea = document.getElementById('previewContentArea');
    const previewMemo = document.getElementById('previewMemo');
    const previewDate = document.getElementById('previewDate');
    const previewDownloadBtn = document.getElementById('previewDownloadBtn');

    let currentTab = 'assets'; // 'assets' | 'videos'

    // Load items from API
    async function loadLibrary() {
        try {
            const res = await fetch('/api/library');
            if (!res.ok) throw new Error('無法取得媒體庫資料');
            const data = await res.json();
            renderLibrary(data);
        } catch (error) {
            console.error('媒體庫載入失敗:', error);
        }
    }

    // Render cards
    function renderLibrary(data) {
        const visualAssets = (data.assets || []).filter(item => item.type === 'image' || item.type === 'video');
        const audioAssets = (data.assets || []).filter(item => item.type === 'audio');

        // Render assets
        assetsGrid.innerHTML = `
            <!-- Asset Upload Card -->
            <div class="music-upload-card" id="assetUploadCard" onclick="triggerAssetUpload()">
                <div class="music-upload-icon">📁</div>
                <h4>上傳圖片/影片素材</h4>
                <p>支援圖片 (JPG/PNG) 與短片 (MP4)</p>
                <input type="file" id="assetFileInput" accept="image/*,video/*" style="display:none;" onchange="handleAssetUpload(event)">
            </div>
        `;
        
        if (visualAssets.length > 0) {
            visualAssets.forEach(item => {
                const card = document.createElement('div');
                card.className = 'media-card';
                
                let previewHtml = '';
                if (item.type === 'image') {
                    previewHtml = `<img src="${item.url}" alt="${item.name}">`;
                } else if (item.type === 'video') {
                    previewHtml = `<video src="${item.url}" muted loop playsinline onmouseover="this.play()" onmouseout="this.pause()"></video>`;
                }
                
                const memoHtml = item.memo ? item.memo : '<span style="color:rgba(255,255,255,0.15)">點擊編輯按鈕為此素材新增備註描述...</span>';
                
                card.innerHTML = `
                    <div class="media-preview" style="cursor: pointer;" title="點擊預覽此項目" onclick="openPreviewModal('assets', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, '${item.url}', '${item.type}', '${item.uploaded_at}')">
                        ${previewHtml}
                    </div>
                    <div class="media-info">
                        <div class="media-name" title="${item.name}">${item.name}</div>
                        <div class="media-memo" title="${item.memo || ''}">${memoHtml}</div>
                        <div class="media-date">${item.uploaded_at}</div>
                    </div>
                    <div class="media-actions">
                        <button type="button" class="media-actions-btn edit-btn" onclick="openEditModal('assets', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                            ✏️ 編輯
                        </button>
                        <button type="button" class="media-actions-btn delete-btn" onclick="deleteLibraryItem('assets', '${item.filename}')">
                            🗑️ 刪除
                        </button>
                    </div>
                `;
                assetsGrid.appendChild(card);
            });
        }

        // Render Music Grid (Custom Audio Files only)
        musicGrid.innerHTML = `
            <!-- Music Upload Card -->
            <div class="music-upload-card" id="musicUploadCard" onclick="triggerMusicUpload()">
                <div class="music-upload-icon">🎵</div>
                <h4>上傳自訂配樂檔案</h4>
                <p>支援 MP3 / WAV 格式</p>
                <input type="file" id="musicFileInput" accept="audio/*" style="display:none;" onchange="handleMusicUpload(event)">
            </div>
        `;
        
        audioAssets.forEach(item => {
            const card = document.createElement('div');
            card.className = 'media-card';
            
            const previewHtml = `<div class="audio-preview-icon">🎵</div>`;
            const memoHtml = item.memo ? item.memo : '<span style="color:rgba(255,255,255,0.15)">點擊編輯按鈕為此配樂新增備註描述...</span>';
            
            card.innerHTML = `
                <div class="media-preview" style="cursor: pointer;" title="點擊試聽此配樂" onclick="openPreviewModal('assets', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, '${item.url}', 'audio', '${item.uploaded_at}')">
                    ${previewHtml}
                </div>
                <div class="media-info">
                    <div class="media-name" title="${item.name}">${item.name}</div>
                    <div class="media-memo" title="${item.memo || ''}">${memoHtml}</div>
                    <div class="media-date">${item.uploaded_at}</div>
                </div>
                <div class="media-actions">
                    <button type="button" class="media-actions-btn edit-btn" onclick="openEditModal('assets', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                        ✏️ 編輯
                    </button>
                    <button type="button" class="media-actions-btn delete-btn" onclick="deleteLibraryItem('assets', '${item.filename}')">
                        🗑️ 刪除
                    </button>
                </div>
            `;
            musicGrid.appendChild(card);
        });

        // Render videos
        if (!data.videos || data.videos.length === 0) {
            videosGrid.innerHTML = '<div class="empty-state">尚未生成過任何影片</div>';
        } else {
            videosGrid.innerHTML = '';
            data.videos.forEach(item => {
                const card = document.createElement('div');
                card.className = 'media-card';
                
                const previewHtml = `<video src="${item.url}" muted loop playsinline onmouseover="this.play()" onmouseout="this.pause()"></video>`;
                const memoHtml = item.memo ? item.memo : '<span style="color:rgba(255,255,255,0.15)">沒有備註...</span>';
                
                card.innerHTML = `
                    <div class="media-preview" style="cursor: pointer;" title="點擊預覽此項目" onclick="openPreviewModal('videos', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, '${item.url}', 'video', '${item.created_at}')">
                        ${previewHtml}
                    </div>
                    <div class="media-info">
                        <div class="media-name" title="${item.name}">${item.name}</div>
                        <div class="media-memo" title="${item.memo || ''}">${memoHtml}</div>
                        <div class="media-date">${item.created_at}</div>
                    </div>
                    <div class="media-actions">
                        <button type="button" class="media-actions-btn edit-btn" onclick="openEditModal('videos', '${item.filename}', \`${item.name.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`, \`${(item.memo || '').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                            ✏️ 編輯
                        </button>
                        <button type="button" class="media-actions-btn delete-btn" onclick="deleteLibraryItem('videos', '${item.filename}')">
                            🗑️ 刪除
                        </button>
                    </div>
                `;
                videosGrid.appendChild(card);
            });
        }
    }

    // Switch Tabs
    window.switchMediaTab = function(tabCategory) {
        currentTab = tabCategory;
        
        tabAssetsBtn.classList.remove('active');
        tabMusicBtn.classList.remove('active');
        tabVideosBtn.classList.remove('active');
        
        assetsGrid.classList.remove('active');
        musicGrid.classList.remove('active');
        videosGrid.classList.remove('active');
        
        if (tabCategory === 'assets') {
            tabAssetsBtn.classList.add('active');
            assetsGrid.classList.add('active');
        } else if (tabCategory === 'music') {
            tabMusicBtn.classList.add('active');
            musicGrid.classList.add('active');
        } else {
            tabVideosBtn.classList.add('active');
            videosGrid.classList.add('active');
        }
    };

    // Modal Control
    window.openEditModal = function(category, id, name, memo) {
        editCategoryInput.value = category;
        editIdInput.value = id;
        editNameInput.value = name;
        editMemoInput.value = memo;
        editModal.classList.add('active');
    };

    window.closeEditModal = function() {
        editModal.classList.remove('active');
        editForm.reset();
    };

    window.openPreviewModal = function(category, filename, name, memo, url, type, dateStr) {
        previewTitle.textContent = type === 'image' ? '🖼️ 圖片預覽' : type === 'video' ? '📹 影片預覽' : '🎵 音訊預覽';
        previewMemo.textContent = memo || (category === 'assets' ? '此素材無備註描述' : '此影片無備註描述');
        previewDate.textContent = (category === 'assets' ? '上傳時間：' : '製作時間：') + dateStr;
        previewDownloadBtn.href = url;
        previewDownloadBtn.setAttribute('download', name);

        previewContentArea.innerHTML = '';
        if (type === 'image') {
            const img = document.createElement('img');
            img.src = url;
            img.alt = name;
            previewContentArea.appendChild(img);
        } else if (type === 'video') {
            const video = document.createElement('video');
            video.src = url;
            video.controls = true;
            video.autoplay = true;
            video.style.outline = 'none';
            previewContentArea.appendChild(video);
        } else if (type === 'audio') {
            const audioContainer = document.createElement('div');
            audioContainer.className = 'preview-audio-container';
            audioContainer.innerHTML = `
                <div class="preview-audio-icon">🎵</div>
                <div style="font-weight:600; font-size:1.1rem; color:white; word-break:break-all; text-align:center; padding: 0 1rem;">${name}</div>
                <audio src="${url}" controls autoplay style="outline:none;"></audio>
            `;
            previewContentArea.appendChild(audioContainer);
        }

        previewModal.classList.add('active');
    };

    window.closePreviewModal = function() {
        const mediaElements = previewContentArea.querySelectorAll('video, audio');
        mediaElements.forEach(el => el.pause());

        previewModal.classList.remove('active');
        previewContentArea.innerHTML = '';
    };

    // Form Update Submission
    editForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const payload = {
            category: editCategoryInput.value,
            id: editIdInput.value,
            name: editNameInput.value,
            memo: editMemoInput.value
        };

        try {
            const res = await fetch('/api/library/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error('修改項目失敗');
            
            closeEditModal();
            loadLibrary(); // Reload list
        } catch (error) {
            alert(`更新失敗: ${error.message}`);
        }
    });

    // Delete Item
    window.deleteLibraryItem = async function(category, id) {
        if (!confirm('您確定要永久刪除此項目與檔案嗎？此操作無法還原。')) return;

        try {
            const res = await fetch(`/api/library/${category}/${id}`, {
                method: 'DELETE'
            });

            if (!res.ok) throw new Error('刪除失敗');
            loadLibrary(); // Reload list
        } catch (error) {
            alert(`刪除錯誤: ${error.message}`);
        }
    };

    // === Template Builder Feature ===
    window.addBuilderScene = function() {
        customScenes.push({
            duration: 3.0,
            visual_type: 'image_zoom',
            zoom_direction: 'in',
            color: '#000000',
            texts: []
        });
        renderBuilderTimeline();
    };

    window.deleteBuilderScene = function(index) {
        customScenes.splice(index, 1);
        renderBuilderTimeline();
    };

    window.addSceneText = function(sceneIndex) {
        customScenes[sceneIndex].texts.push({
            content: '我的文字疊加',
            font_size: 40,
            color: '#ffffff',
            position: 'center',
            start_time: 0.0,
            end_time: customScenes[sceneIndex].duration
        });
        renderBuilderTimeline();
    };

    window.deleteSceneText = function(sceneIndex, textIndex) {
        customScenes[sceneIndex].texts.splice(textIndex, 1);
        renderBuilderTimeline();
    };

    window.updateSceneConfig = function(index, key, val) {
        if (key === 'duration') {
            customScenes[index].duration = parseFloat(val) || 3.0;
        } else if (key === 'visual_type') {
            customScenes[index].visual_type = val;
            renderBuilderTimeline(); // Redraw since visual type alters columns
        } else {
            customScenes[index][key] = val;
        }
    };

    window.updateTextConfig = function(sIdx, tIdx, key, val) {
        if (key === 'font_size') {
            customScenes[sIdx].texts[tIdx].font_size = parseInt(val) || 40;
        } else if (key === 'start_time') {
            customScenes[sIdx].texts[tIdx].start_time = parseFloat(val) || 0.0;
        } else if (key === 'end_time') {
            customScenes[sIdx].texts[tIdx].end_time = parseFloat(val) || 0.0;
        } else {
            customScenes[sIdx].texts[tIdx][key] = val;
        }
    };

    function renderBuilderTimeline() {
        const scenesTimeline = document.getElementById('scenesTimeline');
        if (customScenes.length === 0) {
            scenesTimeline.innerHTML = `
                <div class="empty-state" style="padding: 5rem 2rem;">
                    <h4>尚未加入任何分鏡場景</h4>
                    <p style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem; margin-bottom: 1.5rem;">
                        請點擊右上角的按鈕來建立您影片的第一個場景。
                    </p>
                    <button type="button" class="add-scene-btn" onclick="addBuilderScene()">＋ 建立第一個場景</button>
                </div>
            `;
            return;
        }
        
        scenesTimeline.innerHTML = '';
        customScenes.forEach((scene, sIdx) => {
            const card = document.createElement('div');
            card.className = 'builder-scene-card';
            
            let visualConfigHtml = '';
            if (scene.visual_type === 'image_zoom') {
                visualConfigHtml = `
                    <div class="scene-config-col">
                        <label>縮放動畫方向</label>
                        <select class="text-item-config" style="width:100%;" onchange="updateSceneConfig(${sIdx}, 'zoom_direction', this.value)">
                            <option value="in" ${scene.zoom_direction === 'in' ? 'selected' : ''}>🔍 慢速放大 (Zoom In)</option>
                            <option value="out" ${scene.zoom_direction === 'out' ? 'selected' : ''}>🔎 慢速縮小 (Zoom Out)</option>
                        </select>
                    </div>
                `;
            } else if (scene.visual_type === 'solid_color') {
                visualConfigHtml = `
                    <div class="scene-config-col">
                        <label>背景顏色</label>
                        <input type="color" class="text-item-config" style="padding:0.1rem; height: 35px; width: 100%; cursor:pointer;" value="${scene.color}" onchange="updateSceneConfig(${sIdx}, 'color', this.value)">
                    </div>
                `;
            }
            
            let textsListHtml = '';
            if (scene.texts.length === 0) {
                textsListHtml = `<div style="font-size:0.8rem; color:rgba(255,255,255,0.2); text-align:center; padding:0.5rem;">無文字疊加層</div>`;
            } else {
                scene.texts.forEach((text, tIdx) => {
                    textsListHtml += `
                        <div class="scene-text-item">
                            <input type="text" class="text-item-input" value="${text.content}" placeholder="輸入文字..." oninput="updateTextConfig(${sIdx}, ${tIdx}, 'content', this.value)">
                            
                            <select class="text-item-config" style="width:auto; flex:none;" onchange="updateTextConfig(${sIdx}, ${tIdx}, 'position', this.value)">
                                <option value="center" ${text.position === 'center' ? 'selected' : ''}>置中</option>
                                <option value="top" ${text.position === 'top' ? 'selected' : ''}>頂部</option>
                                <option value="bottom" ${text.position === 'bottom' ? 'selected' : ''}>底部</option>
                            </select>
                            
                            <input type="color" class="text-item-config" style="padding: 0.1rem; height: 32px; width: 45px; flex:none; cursor:pointer;" value="${text.color}" onchange="updateTextConfig(${sIdx}, ${tIdx}, 'color', this.value)">
                            
                            <input type="number" class="text-item-num" placeholder="字級" title="字體大小" value="${text.font_size}" oninput="updateTextConfig(${sIdx}, ${tIdx}, 'font_size', this.value)">
                            
                            <input type="number" step="0.1" class="text-item-num" placeholder="起(秒)" title="開始時間" value="${text.start_time}" oninput="updateTextConfig(${sIdx}, ${tIdx}, 'start_time', this.value)">
                            <input type="number" step="0.1" class="text-item-num" placeholder="迄(秒)" title="結束時間" value="${text.end_time}" oninput="updateTextConfig(${sIdx}, ${tIdx}, 'end_time', this.value)">
                            
                            <button type="button" class="delete-text-btn" onclick="deleteSceneText(${sIdx}, ${tIdx})">&times;</button>
                        </div>
                    `;
                });
            }
            
            card.innerHTML = `
                <div class="scene-card-header">
                    <span class="scene-number">🎬 場景 #${sIdx + 1}</span>
                    <button type="button" class="delete-scene-btn" onclick="deleteBuilderScene(${sIdx})">🗑️ 刪除場景</button>
                </div>
                
                <div class="scene-config-row">
                    <div class="scene-config-col">
                        <label>場景時長 (秒)</label>
                        <input type="number" step="0.1" min="1" max="15" class="form-input" style="padding: 0.5rem; font-size:0.85rem;" value="${scene.duration}" oninput="updateSceneConfig(${sIdx}, 'duration', this.value)">
                    </div>
                    
                    <div class="scene-config-col">
                        <label>視覺功能類型</label>
                        <select class="text-item-config" style="width:100%;" onchange="updateSceneConfig(${sIdx}, 'visual_type', this.value)">
                            <option value="image_zoom" ${scene.visual_type === 'image_zoom' ? 'selected' : ''}>🖼️ 圖片縮放動畫</option>
                            <option value="user_video" ${scene.visual_type === 'user_video' ? 'selected' : ''}>📹 影片短片剪輯</option>
                            <option value="solid_color" ${scene.visual_type === 'solid_color' ? 'selected' : ''}>🎨 單色背景影格</option>
                        </select>
                    </div>
                    
                    ${visualConfigHtml}
                </div>
                
                <div class="scene-texts-section">
                    <div class="texts-header">
                        <h4>📝 文字疊加時序</h4>
                        <button type="button" class="add-text-btn" onclick="addSceneText(${sIdx})">＋ 新增文字</button>
                    </div>
                    <div class="texts-list">
                        ${textsListHtml}
                    </div>
                </div>
            `;
            
            scenesTimeline.appendChild(card);
        });
    }

    function updateBuilderUIForEditing(templateName) {
        const titleEl = document.getElementById('builderSidebarTitle');
        const submitBtn = document.getElementById('builderSubmitBtn');
        const cancelBtn = document.getElementById('builderCancelBtn');
        
        if (titleEl) titleEl.innerText = `✏️ 編輯自訂範本`;
        if (submitBtn) submitBtn.innerText = `💾 儲存修改並更新範本`;
        if (cancelBtn) cancelBtn.style.display = 'block';
    }

    function cancelBuilderEditState() {
        editingTemplateId = null;
        
        // Reset form inputs
        document.getElementById('builderForm').reset();
        customScenes = [];
        renderBuilderTimeline();
        
        // Restore UI Title and Buttons
        const titleEl = document.getElementById('builderSidebarTitle');
        const submitBtn = document.getElementById('builderSubmitBtn');
        const cancelBtn = document.getElementById('builderCancelBtn');
        
        if (titleEl) titleEl.innerText = `🛠️ 建立自訂影片範本`;
        if (submitBtn) submitBtn.innerText = `💾 儲存並發佈範本`;
        if (cancelBtn) cancelBtn.style.display = 'none';
    }

    window.cancelBuilderEdit = function() {
        if (confirm('確定要取消編輯此範本嗎？未儲存的變更將會遺失。')) {
            cancelBuilderEditState();
            // Switch back to Maker tab
            const creatorTab = document.querySelector('.nav-tab[data-tab="maker"]');
            if (creatorTab) creatorTab.click();
        }
    };

    window.editCustomTemplate = async function(templateId) {
        try {
            const res = await fetch(`/api/templates/custom/${templateId}`);
            if (!res.ok) throw new Error('載入自訂範本失敗');
            const customTpl = await res.json();
            
            // Set state
            editingTemplateId = templateId;
            
            // Fill inputs
            document.getElementById('builderName').value = customTpl.name || '';
            document.getElementById('builderDesc').value = customTpl.description || '';
            document.getElementById('builderRatio').value = customTpl.aspect_ratio || '9:16';
            
            // Populate scenes (deep copy)
            customScenes = JSON.parse(JSON.stringify(customTpl.scenes || []));
            
            // Update UI styling
            updateBuilderUIForEditing(customTpl.name);
            
            // Render scenes timeline
            renderBuilderTimeline();
            
            // Switch to Builder tab
            const builderTab = document.querySelector('.nav-tab[data-tab="builder"]');
            if (builderTab) builderTab.click();
            
        } catch (error) {
            alert(`編輯載入失敗: ${error.message}`);
        }
    };

    window.deleteCustomTemplate = async function(templateId) {
        if (confirm('確定要刪除此自訂範本嗎？此動作無法復原。')) {
            try {
                const res = await fetch(`/api/templates/custom/${templateId}`, {
                    method: 'DELETE'
                });
                if (!res.ok) throw new Error('刪除失敗');
                alert('🎉 自訂範本已成功刪除！');
                await loadTemplates();
            } catch (error) {
                alert(`刪除失敗: ${error.message}`);
            }
        }
    };

    window.saveCustomTemplate = async function() {
        const nameInput = document.getElementById('builderName');
        const descInput = document.getElementById('builderDesc');
        const ratioInput = document.getElementById('builderRatio');
        
        const name = nameInput.value.trim();
        if (!name) {
            alert('請輸入範本名稱！');
            return;
        }
        
        if (customScenes.length === 0) {
            alert('請至少加入一個場景分鏡！');
            return;
        }
        
        const payload = {
            id: editingTemplateId,
            name: name,
            description: descInput.value.trim(),
            aspect_ratio: ratioInput.value,
            scenes: customScenes
        };
        
        try {
            const res = await fetch('/api/templates/custom', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            if (!res.ok) throw new Error('儲存範本失敗');
            
            alert(editingTemplateId ? '🎉 自訂範本修改並更新成功！' : '🎉 自訂範本儲存並發佈成功！');
            
            // Reset Builder
            cancelBuilderEditState();
            
            // Reload maker templates grid
            await loadTemplates();
            
            // Switch back to Maker tab
            const creatorTab = document.querySelector('.nav-tab[data-tab="maker"]');
            if (creatorTab) creatorTab.click();
            
        } catch (error) {
            alert(`發佈錯誤: ${error.message}`);
        }
    };

    // Initialize builder timeline empty state
    renderBuilderTimeline();

    // === Music Library Upload Handlers ===
    window.triggerMusicUpload = function() {
        document.getElementById('musicFileInput').click();
    };

    window.handleMusicUpload = async function(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Validation
        const validTypes = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/wave'];
        if (!validTypes.includes(file.type) && !file.name.endsWith('.mp3') && !file.name.endsWith('.wav')) {
            alert('不支援的檔案格式，請上傳 MP3 或 WAV 音訊檔案！');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Show loading placeholder on card
            const uploadCard = document.getElementById('musicUploadCard');
            uploadCard.style.pointerEvents = 'none';
            uploadCard.innerHTML = `
                <div class="progress-loader" style="width:40px; height:40px; border-width:3px; margin-bottom:1rem;"></div>
                <h4>正在上傳配樂...</h4>
                <p>${file.name.substring(0, 20)}</p>
            `;

            const res = await fetch('/api/library/upload', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('上傳失敗');

            // Reset file input
            event.target.value = '';
            
            // Reload templates and library so the new music immediately appears in dropdowns and the list
            await loadLibrary();
            await loadTemplates();
        } catch (error) {
            alert(`上傳錯誤: ${error.message}`);
            // Restore card content
            const uploadCard = document.getElementById('musicUploadCard');
            uploadCard.style.pointerEvents = 'auto';
            uploadCard.innerHTML = `
                <div class="music-upload-icon">🎵</div>
                <h4>上傳自訂配樂檔案</h4>
                <p>支援 MP3 / WAV 格式</p>
                <input type="file" id="musicFileInput" accept="audio/*" style="display:none;" onchange="handleMusicUpload(event)">
            `;
        }
    };

    // === Asset Library Upload Handlers ===
    window.triggerAssetUpload = function() {
        document.getElementById('assetFileInput').click();
    };

    window.handleAssetUpload = async function(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Validation
        const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/quicktime'];
        if (!validTypes.includes(file.type) && !file.name.endsWith('.jpg') && !file.name.endsWith('.png') && !file.name.endsWith('.mp4')) {
            alert('不支援的檔案格式，請上傳 JPG、PNG 圖片或 MP4 影片！');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Show loading placeholder on card
            const uploadCard = document.getElementById('assetUploadCard');
            uploadCard.style.pointerEvents = 'none';
            uploadCard.innerHTML = `
                <div class="progress-loader" style="width:40px; height:40px; border-width:3px; margin-bottom:1rem;"></div>
                <h4>正在上傳素材...</h4>
                <p>${file.name.substring(0, 20)}</p>
            `;

            const res = await fetch('/api/library/upload', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('上傳失敗');

            // Reset input
            event.target.value = '';
            
            // Reload library
            await loadLibrary();
        } catch (error) {
            alert(`上傳錯誤: ${error.message}`);
            // Restore card content
            const uploadCard = document.getElementById('assetUploadCard');
            uploadCard.style.pointerEvents = 'auto';
            uploadCard.innerHTML = `
                <div class="music-upload-icon">📁</div>
                <h4>上傳圖片/影片素材</h4>
                <p>支援圖片 (JPG/PNG) 與短片 (MP4)</p>
                <input type="file" id="assetFileInput" accept="image/*,video/*" style="display:none;" onchange="handleAssetUpload(event)">
            `;
        }
    };

    // === Library Selection Dialog and Modal logic ===
    let currentSelectField = '';
    let currentSelectMultiple = false;
    let selectedLibraryItems = []; // Array of filenames

    window.openLibrarySelect = async function(fieldName, isMultiple, acceptType) {
        currentSelectField = fieldName;
        currentSelectMultiple = isMultiple;
        selectedLibraryItems = [];
        
        const titleEl = document.getElementById('librarySelectTitle');
        const gridEl = document.getElementById('librarySelectGrid');
        
        titleEl.textContent = `📁 從媒體庫選擇素材 (${isMultiple ? '可複選' : '單選'})`;
        gridEl.innerHTML = '<div class="empty-state">正在載入媒體庫...</div>';
        
        document.getElementById('librarySelectModal').classList.add('active');
        
        try {
            const res = await fetch('/api/library');
            if (!res.ok) throw new Error('無法載入媒體庫');
            const data = await res.json();
            
            // Filter assets by accept type
            let filtered = [];
            if (acceptType.includes('image')) {
                filtered = (data.assets || []).filter(item => item.type === 'image');
            } else if (acceptType.includes('video')) {
                filtered = (data.assets || []).filter(item => item.type === 'video');
            } else if (acceptType.includes('audio')) {
                filtered = (data.assets || []).filter(item => item.type === 'audio');
            } else {
                filtered = data.assets || [];
            }
            
            if (filtered.length === 0) {
                gridEl.innerHTML = '<div class="empty-state">媒體庫中暫無符合類型的素材</div>';
                return;
            }
            
            gridEl.innerHTML = '';
            filtered.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'library-select-item';
                itemDiv.dataset.filename = item.filename;
                
                let previewHtml = '';
                if (item.type === 'image') {
                    previewHtml = `<img src="${item.url}" alt="${item.name}">`;
                } else if (item.type === 'video') {
                    previewHtml = `<video src="${item.url}" muted playsinline></video>`;
                } else {
                    previewHtml = `<div style="font-size:2rem;">🎵</div>`;
                }
                
                itemDiv.innerHTML = `
                    <div class="library-select-preview">${previewHtml}</div>
                    <div class="library-select-name" title="${item.name}">${item.name}</div>
                    <div class="select-badge">✓</div>
                `;
                
                itemDiv.addEventListener('click', () => {
                    if (isMultiple) {
                        itemDiv.classList.toggle('selected');
                        const idx = selectedLibraryItems.indexOf(item.filename);
                        if (idx > -1) {
                            selectedLibraryItems.splice(idx, 1);
                        } else {
                            selectedLibraryItems.push(item.filename);
                        }
                    } else {
                        // Clear others
                        gridEl.querySelectorAll('.library-select-item').forEach(el => el.classList.remove('selected'));
                        itemDiv.classList.add('selected');
                        selectedLibraryItems = [item.filename];
                    }
                });
                
                gridEl.appendChild(itemDiv);
            });
        } catch (error) {
            gridEl.innerHTML = `<div class="empty-state">載入失敗: ${error.message}</div>`;
        }
    };

    window.closeLibrarySelectModal = function() {
        document.getElementById('librarySelectModal').classList.remove('active');
    };
    
    // Bind Confirm Button
    document.getElementById('confirmLibrarySelectBtn').addEventListener('click', () => {
        if (selectedLibraryItems.length === 0) {
            alert('請至少選擇一個項目！');
            return;
        }
        
        const fieldName = currentSelectField;
        const hiddenInput = document.getElementById(`library_input_${fieldName}`);
        const fileInput = document.querySelector(`#group_${fieldName} .file-input`);
        const previewContainer = document.getElementById(`preview_${fieldName}`);
        
        hiddenInput.value = selectedLibraryItems.join(',');
        
        // Clear local files and remove required attribute
        fileInput.value = '';
        fileInput.removeAttribute('required');
        
        // Render selected library items preview
        previewContainer.innerHTML = '';
        selectedLibraryItems.forEach((filename, idx) => {
            const previewCard = document.createElement('div');
            previewCard.className = 'file-preview-card';
            previewCard.innerHTML = `
                <span style="font-size:1rem; margin-right:0.3rem;">📁</span>
                <span style="font-size:0.8rem; flex-grow:1; text-align:left; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${filename}">${filename}</span>
                <span class="remove-file-btn" onclick="removeLibrarySelection('${fieldName}', ${idx})">&times;</span>
            `;
            previewContainer.appendChild(previewCard);
        });
        
        closeLibrarySelectModal();
    });

    window.removeLibrarySelection = function(fieldName, idx) {
        const hiddenInput = document.getElementById(`library_input_${fieldName}`);
        const fileInput = document.querySelector(`#group_${fieldName} .file-input`);
        const previewContainer = document.getElementById(`preview_${fieldName}`);
        
        let items = hiddenInput.value.split(',');
        items.splice(idx, 1);
        
        if (items.length === 0 || items[0] === '') {
            hiddenInput.value = '';
            previewContainer.innerHTML = '';
            // Restore required attribute if needed
            const field = templateFieldsMap[fieldName];
            if (field && field.required) {
                fileInput.setAttribute('required', 'required');
            }
        } else {
            hiddenInput.value = items.join(',');
            // Re-render
            previewContainer.innerHTML = '';
            items.forEach((filename, i) => {
                const previewCard = document.createElement('div');
                previewCard.className = 'file-preview-card';
                previewCard.innerHTML = `
                    <span style="font-size:1rem; margin-right:0.3rem;">📁</span>
                    <span style="font-size:0.8rem; flex-grow:1; text-align:left; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${filename}">${filename}</span>
                    <span class="remove-file-btn" onclick="removeLibrarySelection('${fieldName}', ${i})">&times;</span>
                `;
                previewContainer.appendChild(previewCard);
            });
        }
    };
});
